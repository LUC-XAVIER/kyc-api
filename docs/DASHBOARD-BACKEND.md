# Dashboard Backend (Phase 4a)

This document describes everything added to the API **after** the ML pipeline
work, to support the management dashboard (the Streamlit UI is Phase 4b). It
covers the data-model change, the security primitives, the authentication and
authorization model, every new endpoint, the compliance-PDF renderer, the
statistics aggregation, staff/API-key management, the packaging changes, and
the security-hardening notes.

Companion doc: [`ML-PIPELINE.md`](ML-PIPELINE.md) covers the verification
pipeline itself (OCR → liveness → face match → duplicate → decision).

---

## 0. Prerequisite fix — `app/models` was untracked

Before any Phase-4a work, a latent bug surfaced: `.gitignore` had a bare
`models/` rule (meant for ML weight artifacts) that also matched the
`app/models/` ORM package, so **the entire ORM layer had never been
committed** — it existed only on local disks, and `main`/deploys were missing
it. Fixed by anchoring the rule to `ml/models/` and adding the package
(PR #8). Any clone/CI/deploy of `main` now has the models.

---

## 1. Data model change — `Agent` becomes a login

`Agent` gained three columns and a role enum so a person can sign in to the
dashboard:

| Column | Type | Notes |
|---|---|---|
| `email` | `str \| None`, unique | Login identifier |
| `hashed_password` | `str \| None` | bcrypt hash (never plaintext) |
| `role` | `AgentRole` | `AGENT` / `MANAGER` / `ADMIN` (default `AGENT`) |

`AgentRole` (`app/models/enums.py`):

- **AGENT** — submits verifications; sees only the agent surface.
- **MANAGER** — everything an agent can do **plus** the review queue,
  statistics, compliance reports, and staff/API-key management.
- **ADMIN** — reserved for Openxtech platform staff; a manager **cannot**
  assign it.

Credential fields are nullable so pre-existing agent rows survive; `role`
backfills to `AGENT`.

**Migration:** `alembic/versions/f4a1c9d2b3e7_add_agent_auth_fields.py`
(creates the `agent_role` type, adds the three columns, unique email
constraint). Apply with:

```bash
uv run alembic upgrade head
```

---

## 2. Security primitives (`app/core/security.py`)

The module already held API-key generation/hashing. Phase 4a added:

### Passwords — bcrypt
- `hash_password(password) -> str` and `verify_password(password, hash) -> bool`.
- Each password is **SHA-256 pre-hashed then base64-encoded** before bcrypt.
  bcrypt only consumes its first 72 bytes; the pre-hash means a long password
  is hashed *in full* and uniformly, instead of being silently truncated (or
  rejected outright by bcrypt ≥ 4.1). A malformed stored hash makes
  `verify_password` return `False` rather than raise.

### Session tokens — JWT (HS256)
- `create_access_token(*, subject, role, expires_delta=None) -> str` — signs a
  JWT with claims `sub` (agent id), `role`, `iat`, `exp`.
- `decode_access_token(token) -> dict` — validates signature + expiry; raises
  `jwt.InvalidTokenError` (incl. expired) on any problem.
- Config used (`app/core/config.py`): `secret_key`, `jwt_algorithm` (`HS256`),
  `access_token_expire_minutes` (`60`). No new settings were introduced.

---

## 3. Authentication model — two credentials, one `Principal`

There are **two kinds of caller**:

1. **Machine** — the MFI's own software, using an `X-API-Key` header (the
   pre-existing gateway). This is the MFI's master credential.
2. **Human** — an agent/manager signed into the dashboard, carrying an
   `Authorization: Bearer <jwt>` token from `POST /auth/login`.

### Dependencies (`app/api/v1/deps.py`)

| Dependency | Accepts | Yields | Use |
|---|---|---|---|
| `get_current_mfi` | API key | `MfiAccount` | legacy machine-only routes |
| `get_metered_mfi` | API key | `MfiAccount` | + quota enforcement |
| `get_current_agent` | bearer | `Agent` | dashboard-only, any role |
| `require_manager` | bearer | `Agent` | dashboard-only, manager+ |
| **`get_principal`** | **either** | `Principal` | any authenticated caller |
| **`get_metered_principal`** | **either** | `Principal` | + quota (verify) |
| **`require_manager_principal`** | **either** | `Principal` | manager-level actions |

### `Principal`

```python
@dataclass
class Principal:
    mfi_account: MfiAccount   # tenant, for row-level scoping
    agent: Agent | None       # the human, or None for a machine caller
    is_manager: bool          # API-key caller OR agent with MANAGER/ADMIN role
    # actor_type -> ActorType (SYSTEM for machines, else the agent's role)
    # actor_id   -> str(agent.id) or None
```

`get_principal` prefers the bearer token when both are present. **An API key
is trusted as full tenant access** (`is_manager=True`); a bearer token carries
the agent's own role. This lets the dashboard reach these routes with real
RBAC while keeping the machine-integration path (and its tests) working. A
missing/invalid/expired token — or a token for a **disabled** agent (checked
on every request via `AgentStatus`) — is a `401`; a disabled agent is locked
out immediately even if its token hasn't expired.

### Authorization
`require_manager_principal` raises `AuthorizationError` (**403**) unless the
caller is manager-level. Audit-log entries now record the real actor
(`actor_type` + `actor_id` from the `Principal`) instead of a hardcoded value.

---

## 4. Endpoint reference (all under `/api/v1`)

| Method & path | Auth / role | Purpose |
|---|---|---|
| `POST /auth/login` | public | email + password → JWT + identity |
| `GET /auth/me` | bearer (any) | the signed-in agent's profile |
| `GET /account` | **any authenticated** | account + subscription/quota summary |
| `POST /kyc/verify` | any authenticated (metered) | run a verification |
| `GET /kyc/verifications` | API key *(see §9)* | history list |
| `GET /kyc/verifications/{id}` | API key *(see §9)* | verification detail |
| `GET /kyc/verifications/stats` | **manager** | dashboard statistics |
| `GET /kyc/reviews` | **manager** | pending review queue |
| `POST /kyc/reviews/{id}/decision` | **manager** | approve / reject |
| `POST /kyc/reports` | **manager** | generate a compliance report |
| `GET /kyc/reports` · `/{id}` | **manager** | list / fetch reports |
| `GET /kyc/reports/{id}/pdf` | **manager** | download the PDF |
| `GET /kyc/monitoring/drift` | API key *(see §9)* | face-match drift report |
| `GET /agents` · `POST /agents` · `PATCH /agents/{id}` | **manager** | staff management |
| `GET /api-keys` · `POST /api-keys` · `DELETE /api-keys/{id}` | **manager** | key management |

### Login (`POST /auth/login`)
Body `{email, password}`. On success returns `{access_token, token_type,
role, agent_id, full_name, mfi_account_id}`. Unknown email, wrong password,
and disabled account all return the **same** generic `401` (`Invalid email or
password.`) so the endpoint can't be used to enumerate accounts.

### Verify attribution
`POST /kyc/verify` now records **who** submitted: a dashboard submission sets
`Verification.agent_id` and `submission_method = DASHBOARD` and audits the
agent; a machine (API-key) call stays `submission_method = API` / actor
`SYSTEM`.

---

## 5. Statistics (`app/services/stats.py`, `GET …/verifications/stats`)

Manager-only. Query params `start`, `end` (inclusive dates), optional
`branch`. Returns, scoped to the caller's MFI:

- `total`, and the display bands `verified` (VERIFIED + APPROVED), `pending`,
  `rejected`;
- `by_status` — raw counts per status value;
- `per_day` — `{date, verified, pending, rejected}` buckets;
- `by_branch` — counts via the `Verification → Agent` outer join (branch lives
  on the agent; unattributed rows fall under "Unassigned");
- `avg_processing_seconds` — mean of `processed_at − created_at`.

Backs the manager dashboard's KPI cards, per-day stacked bars, status donut,
and by-branch bars. `start > end` → `400`.

---

## 6. Compliance PDF (`app/services/report_pdf.py`, `GET …/reports/{id}/pdf`)

`ComplianceReport` stores only the aggregate snapshot, so the PDF's detail
table is gathered at render time: `reporting.report_rows(db, report)` joins
each verification in the report's period to its agent for the branch/agent
columns.

`render_report_pdf(report, rows, *, mfi_name)` (ReportLab) produces the
Openxtech-branded layout from the design mockup: header (generation stamp +
report id), four KPI cards (total / verified / pending / rejected in the brand
colours), a paginated detail table (CLIENT ID · DATE · BRANCH · AGENT ·
STATUS, colour-coded status, repeating header), and a "Confidential — for
COBAC audit purposes only" footer with "Page X of Y" (via a `_NumberedCanvas`
that defers rendering until the total page count is known). The endpoint
streams it as `application/pdf` with an attachment filename.

---

## 7. Staff management (`app/api/v1/routes/agents.py`)

Manager-only.

- `GET /agents` — list the MFI's agents (never the password hash).
- `POST /agents` — provision an agent (`full_name`, `email`, `password`,
  `branch`, `role`). Enforces: the **plan's `max_agents` limit**
  (Starter 3 / Growth 15 / Pro & Enterprise unlimited), a **globally unique
  email**, and **refuses the `ADMIN` role**. The password is stored bcrypt-
  hashed; the new agent can immediately log in.
- `PATCH /agents/{id}` — partial update of `full_name` / `branch` / `role` /
  `status` (e.g. promote to MANAGER, or set `DISABLED` to lock the account
  out). Scoped to the caller's MFI (`404` otherwise); still can't assign
  `ADMIN`.

---

## 8. API-key management (`app/api/v1/routes/api_keys.py`)

Manager-only. Keys are the MFI's machine credential for `/kyc/verify`.

- `GET /api-keys` — list keys by `id`, `prefix`, `is_active`, `created_at`,
  `last_used_at`. **The secret is never included.**
- `POST /api-keys` — mint a key; the plaintext `full_key` (`kyc_live_…`) is
  returned **exactly once**. Only the HMAC-SHA256 digest (peppered) and the
  display prefix are stored.
- `DELETE /api-keys/{id}` — revoke (soft: `is_active = False`); the key
  immediately stops authenticating.

---

## 9. Packaging & config changes

- **Dropped `passlib`** (unmaintained; its bcrypt backend breaks against
  bcrypt ≥ 4.1) in favour of the **`bcrypt`** library directly. It's now a
  core dependency.
- **Moved `reportlab` into core dependencies** (from the `dashboard` extra):
  the PDF is rendered **server-side** by the API; the Streamlit dashboard only
  downloads the result. `pyjwt` was already declared.
- Lockfile regenerated. Sync with both extras as usual:
  `uv sync --extra ml --extra dev`.

### Still API-key-only (deferred to Phase 4b)
`GET /kyc/verifications`, `GET /kyc/verifications/{id}`, and
`GET /kyc/monitoring/drift` still authenticate via `get_current_mfi` (API key
only). Phase 4b will move them to `get_principal` so the dashboard's History /
My-Submissions / monitoring views work with a bearer token, and add
agent-scoped filtering (an agent sees only their own submissions).

---

## 10. Security & hardening notes

What's already in place:

- **No plaintext secrets.** Passwords are bcrypt-hashed; API keys are stored
  as an HMAC-SHA256 digest mixed with a server-side pepper
  (`settings.api_key_pepper`) plus a non-secret display prefix.
- **Enumeration-resistant login** (single generic error).
- **Immediate lock-out.** An agent's `status` is checked on every request, so
  disabling an account rejects even an unexpired token.
- **Stateless tokens** with a 60-minute expiry (`access_token_expire_minutes`).
  There is no refresh token or server-side revocation list yet — re-login on
  expiry; account disablement is the revocation mechanism.

### ⚠️ `secret_key` hardening (do before production — Phase 6)

JWTs are signed with `settings.secret_key` using **HS256**. The dev default
(`"change-me-in-production"`) is **23 bytes**, below the **32-byte minimum**
that RFC 7518 §3.2 mandates for an HMAC-SHA-256 key — the test suite emits
`InsecureKeyLengthWarning` because of it. This is fine for local development
but **must not** ship: a short/guessable signing key lets an attacker forge
valid session tokens for any agent/role.

**Before deploying:**

- Set a strong, random `SECRET_KEY` (≥ 32 bytes, e.g.
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`) via the
  environment / `.env` — never commit it.
- Likewise set a strong `API_KEY_PEPPER` (the API-key digest depends on it; a
  weak pepper weakens every stored key).
- Rotating `secret_key` invalidates all outstanding JWTs (everyone re-logs in),
  which is the intended kill-switch.

Also queued for Phase-6 hardening: HTTPS/TLS termination, rate-limiting the
login endpoint, and (optionally) token revocation / shorter-lived tokens with
refresh.

---

## 11. Tests

Phase 4a is covered by unit tests (password/JWT primitives, PDF renderer) and
integration tests (login + role dependencies, RBAC 403s across
reviews/reports/agents/api-keys, stats aggregation + branch filter, the PDF
download, and agent/API-key management). The full suite (**196 tests**) passes
and ruff is clean. A shared-DB test-isolation bug was also fixed: a
report-count assertion was global and is now scoped to the test's own account.
