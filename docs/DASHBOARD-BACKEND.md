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
| `GET /kyc/verifications/{id}` | API key *(see §9)* | verification detail (incl. `available_images`) |
| `GET /kyc/verifications/{id}/images/{kind}` | API key *(see §9)* | one captured image (`ID_FRONT`/`ID_BACK`/`SELFIE`), decrypted |
| `GET /kyc/verifications/stats` | **manager** | dashboard statistics |
| `GET /kyc/reviews` | **manager** | pending review queue |
| `POST /kyc/reviews/{id}/decision` | **manager** | approve / reject |
| `POST /kyc/reports` | **manager** | generate a compliance report |
| `GET /kyc/reports` · `/{id}` | **manager** | list / fetch reports |
| `GET /kyc/reports/{id}/pdf` | **manager** | download the PDF |
| `GET /kyc/monitoring/drift` | API key *(see §9)* | face-match drift report |
| `GET /agents` · `POST /agents` · `PATCH /agents/{id}` | **manager** | staff management |
| `GET /api-keys` · `POST /api-keys` · `DELETE /api-keys/{id}` | **manager** | key management |
| `GET /admin/stats` | **platform admin** | cross-tenant Overview totals |
| `GET /admin/mfis` | **platform admin** | every MFI + rollup counts |
| `GET /admin/mfis/{id}` | **platform admin** | one MFI drill-down |
| `PATCH /admin/mfis/{id}/status` | **platform admin** | enable/disable an MFI (audited) |
| `GET /admin/audit` | **platform admin** | platform-wide audit trail (paginated) |

### Verification images
The detail response carries `available_images` — the kinds actually stored
(`ID_FRONT`/`ID_BACK`/`SELFIE`, no back for a passport) — so a client fetches
only images that exist. `GET …/{id}/images/{kind}` streams one decrypted image
under the **same scope as the detail endpoint** (the caller's MFI; an agent
only their own submissions). The bytes are biometric, so the response is sent
`Cache-Control: private, no-store`. The dashboard loads them as authenticated
blobs and shows them inside the History detail popup.

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

### Platform admin (Openxtech, cross-tenant)
The `ADMIN` role is the Openxtech operator who oversees **every** MFI, so —
unlike a manager — an admin belongs to **no** MFI: `users.mfi_account_id` is
now nullable and null for the admin (migration `d3e4f5a6b7c8`). Seed one with
`python -m scripts.seed_admin`. The `/admin/*` routes are gated by
`require_platform_admin` (`role == ADMIN`) and never apply per-tenant scoping.
`GET /admin/stats` aggregates platform totals (MFI/verification/user counts,
plan mix, last-14-day bars, quota warnings); `GET /admin/mfis[/{id}]` list and
drill into accounts. `PATCH /admin/mfis/{id}/status` flips an account between
`ACTIVE` and `SUSPENDED` and audits it (`mfi.suspended`/`mfi.reactivated`).
`GET /admin/audit` returns the platform-wide audit trail (newest first,
`limit`/`offset` paginated), each row joined to its MFI name — the same
immutable `audit_logs` the suspend/reactivate actions above write to.
**Suspension is enforced at authentication**: a `SUSPENDED` MFI's staff can no
longer log in and its API keys are rejected (both raise `401`). A platform
admin has no MFI, so this check never blocks them.

---

## 5. Statistics (`app/services/stats.py`, `GET …/verifications/stats`)

Manager-only. Query params `start`, `end` (inclusive dates), optional
`branch`. Returns, scoped to the caller's MFI:

- `total`, and the display bands `verified` (VERIFIED + APPROVED), `pending`,
  `rejected`;
- `by_status` — raw counts per status value;
- `per_day` — `{date, verified, pending, rejected}` buckets, one for **every**
  day of the requested range including the empty ones, so a chart plotted from
  it keeps a fixed x-axis;
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
- **Brute-force throttle.** Consecutive failed PINs are counted on
  `users.failed_login_count`; at `login_max_attempts` (5) the account is
  locked for `login_lockout_minutes` (15) via `users.locked_until`. The lock
  is checked *before* the PIN, so a locked account rejects even a correct
  one. State is in Postgres, not process memory, so it survives restarts and
  holds across uvicorn workers — an in-memory per-IP limiter would give N
  workers N× the allowance and fall to IP rotation regardless. Lockout is
  always time-boxed: a permanent lock would let anyone who knows an agent's
  phone number deny them service at will.
- **PII encrypted at rest (NFR03/NFR04).** `extracted_data.full_name`,
  `id_number`, `date_of_birth` and `place_of_birth` are sealed with
  AES-256-GCM (`app/core/crypto.py`) via the `EncryptedString` /
  `EncryptedDate` column types, so a database dump or a leaked backup does
  not expose a client's identity. Encryption is randomized per write, which
  deliberately rules out equality search on those columns — nothing queries
  them, and deterministic encryption would leak which rows share a value.
- **Immediate lock-out.** An agent's `status` is checked on every request, so
  disabling an account rejects even an unexpired token.
- **Stateless tokens** with a 60-minute expiry (`access_token_expire_minutes`).
  There is no refresh token or server-side revocation list yet — re-login on
  expiry; account disablement is the revocation mechanism.

### Required secrets (enforced at startup)

`Settings._reject_weak_secrets` refuses to construct when
`ENVIRONMENT=production` (case-insensitive) and any guarded secret is still
the shipped `"change-me-in-production"` placeholder or is shorter than the
32-byte HS256 floor (RFC 7518 §3.2). Every offender is reported at once, so a
deploy isn't fixed one variable per restart. The check is a fail-fast at
import: a misconfigured production process dies at startup rather than
serving forgeable tokens. Non-production is untouched, so the local stack and
the test suite keep their weak defaults.

| Variable | Protects | Rotation cost |
|---|---|---|
| `SECRET_KEY` | Signs dashboard JWTs (HS256) | Invalidates all outstanding sessions — the intended kill-switch |
| `API_KEY_PEPPER` | Mixed into the stored API-key digest | Invalidates every issued API key |
| `ENCRYPTION_KEY` | Seals the PII columns (AES-256-GCM) | **Makes existing encrypted rows unreadable — re-encrypt before rotating** |

Generate them with `python -c "import secrets; print(secrets.token_urlsafe(48))"`
(`SECRET_KEY`, `API_KEY_PEPPER`) and
`python -c "from app.core.crypto import generate_key; print(generate_key())"`
(`ENCRYPTION_KEY`, which must decode to exactly 32 bytes). Set them via the
environment / `.env`; never commit them. `ENCRYPTION_KEY` must also be present
when running `alembic upgrade`, since the migration that introduced the
encrypted columns re-encrypts existing rows in Python.

### Face embeddings are covered by volume encryption, not column encryption

`face_embeddings.vector` is deliberately left in a pgvector column. Sealing it
would force it to opaque `BYTEA` and permanently foreclose SQL-side ANN
search — which matters, because `PgVectorDuplicateStore.build_index` currently
loads *every* embedding for an MFI on *every* verify request, and the natural
fix at scale is an IVFFlat/HNSW index doing the search in Postgres. Full-disk
/ volume encryption on the host covers the realistic threat here (stolen disk,
leaked backup) without closing that door. This is an accepted trade-off, not
an oversight — revisit it if the threat model grows to include a live database
compromise.

### Still queued for Phase 6

HTTPS/TLS termination (which also unblocks `getUserMedia`, since the agent
camera needs a secure context), per-IP rate limiting as a second layer in
front of the per-account throttle, encryption of the host volume, Locust load
testing against the NFR01 10-second budget, and optionally token revocation /
shorter-lived tokens with refresh.

---

## 11. Tests

Phase 4a is covered by unit tests (password/JWT primitives, PDF renderer) and
integration tests (login + role dependencies, RBAC 403s across
reviews/reports/agents/api-keys, stats aggregation + branch filter, the PDF
download, and agent/API-key management). The full suite (**196 tests**) passes
and ruff is clean. A shared-DB test-isolation bug was also fixed: a
report-count assertion was global and is now scoped to the test's own account.
