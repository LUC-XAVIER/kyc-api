# KYC-API — Implementation Plan

Companion to the **Analysis Document** (`KYC_API_Cahier_Analyse.docx`) and
the **Design Document** (`KYC_API_Cahier_Conception.docx`). This document
translates those deliverables into a concrete, phased build plan and records
the agreed project layout.

> **Status legend:** ✅ done · 🔨 in progress · ⬜ not started

---

## 1. Project layout

Each module in Design doc §5.1 maps to one home in the tree. The FastAPI
backend, the Streamlit dashboard, and the ML training code are kept as
separate top-level concerns because they are separate processes.

```
kyc-api/
├── app/                      # FastAPI backend (the API service)
│   ├── main.py               # app factory: CORS, exception handlers, router, Swagger
│   ├── core/                 # config (pydantic-settings), logging, exceptions, security
│   ├── api/v1/routes/        # API Gateway: health, verify, reviews, reports, subscriptions, admin
│   ├── schemas/              # Pydantic request/response models (the API contract)
│   ├── models/               # SQLAlchemy ORM entities (Data Layer)
│   ├── db/                   # engine, session, declarative base
│   ├── services/             # business logic (subscription, verification, reporting, audit)
│   └── pipeline/             # ML verification pipeline modules
├── dashboard/                # Streamlit app (separate process)
├── ml/                       # academic contribution: anti-spoof training + pipeline evaluation
├── alembic/                  # database migrations
├── scripts/                  # seed_plans.py, build_faiss_index.py, ...
├── docker/                   # Dockerfile + docker-compose (Postgres/pgvector)
├── tests/{unit,integration}/ # mirrors app/
└── docs/                     # analysis & design documents, this plan, diagrams
```

## 2. Tooling

- **Dependency management:** `uv` (Python **3.11** pinned), `pyproject.toml`
  with deps split into `core` / `ml` / `dashboard` / `dev` optional groups so
  the API can be built and tested without the heavy ML stack.
- **Quality:** `ruff` (PEP 8, 79-col, Google docstrings — Design doc §4.2.2),
  `pytest`, `Locust` (load), Alembic (schema), MLflow (model versioning).
- **Commits:** Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`,
  `refactor:`), one clean commit per phase boundary.

## 3. Build phases

| Phase | Scope | Status |
|-------|-------|--------|
| **0** | **Scaffold** — config, Docker/Postgres, FastAPI skeleton + `/health`, tooling, passing smoke test | ✅ |
| **1** | **Data layer** — the 12 ORM entities + subscription/usage fields, pgvector embedding column, Alembic migrations, seed the 4 subscription plans | ✅ |
| **2** | **API gateway + subscriptions** — API-key auth (hashed), quota enforcement (80% warn / 100% block), request validation, `/kyc/verify` wired to a *stub* pipeline → fully demoable API | ✅ |
| **3** | **ML pipeline** — preprocess → OCR (CM NIC) → liveness → face match (ArcFace) → duplicate (FAISS/pgvector) → decision engine, wired into the orchestrator (early-exit per Design §6.3.1) | ✅ |
| **3b** | **Anti-spoofing classifier** *(academic contribution)* — LBP feature extraction, SVM training on NUAA + local data, MLflow tracking, evaluation report | ✅ |
| **4** | **Dashboard** — login, camera-only agent form, manager review queue, stats, ReportLab compliance PDF, subscription view | ✅ |
| **5** | **Compliance & monitoring** — immutable audit trail everywhere, report generation, Evidently drift monitoring | ✅ |
| **6** | **Hardening & deployment** — secrets guard, login throttle, PII encryption at rest, HTTPS, CI/CD, Locust load test (<10 s, FAR<1% / FRR<5%) | 🚧 |

**Phase 4 note:** built as an **Angular 19 SPA** (`KYC-Frontend/`), not
Streamlit. Streamlit could not deliver the camera capture flow or the
role-separated agent/manager apps the spec needs. See `DASHBOARD-BACKEND.md`.

**Phase 6 note:** deploying to a **VPS**, not Railway/Render — the ML image is
too large and memory-hungry for their small tiers. See `DEPLOYMENT.md`.

**Sequencing rationale:** Phases 0–2 deliver a working multi-tenant API with
quota enforcement and a stub verifier — fully demoable — *before* any ML
model is touched. The highest-uncertainty work (Phase 3/3b accuracy) then sits
on a proven skeleton instead of blocking it. Each pipeline module is built and
unit-tested independently (NFR07, IEEE-730).

## 4. Phase 1 detail (current)

**Entities** (Analysis doc §4.1): `SubscriptionPlan`, `MfiAccount`, `Agent`,
`ApiKey`, `Verification`, `ExtractedData`, `FaceEmbedding`, `LivenessResult`,
`FaceMatchResult`, `DuplicateFlag`, `AuditLog`, `ComplianceReport`.

**Design choices for this phase:**
- UUID primary keys (non-enumerable — appropriate for KYC data).
- Timestamps `timestamptz` with server defaults; status fields as DB enums.
- `FaceEmbedding.vector` is a `pgvector` `Vector(512)` column (ArcFace dim).
- Multi-tenancy: every tenant-owned row carries `mfi_account_id`.
- Subscription usage tracked on `MfiAccount` (`current_period_usage`,
  `billing_cycle_start`) against the linked `SubscriptionPlan` quota.
- API keys stored **hashed** (NFR03), never in plaintext.

**Deliverables:** `app/db/{base,session}.py`, `app/models/*`, Alembic env +
initial migration, `scripts/seed_plans.py` (Starter/Growth/Pro/Enterprise per
Design §6.2), offline DDL-compile + metadata unit tests.

**Run (after `docker compose up -d db`):**
```bash
uv run alembic upgrade head
uv run python -m scripts.seed_plans
```

## 5. Open items / risks

- ⚠️ `docs/KYC_API_Cahier_Conception.docx` was found **corrupt on disk**
  (truncated ZIP) and should be re-saved from the source editor.
- The **Technical Requirements Document** referenced by both docs is not yet
  in the repository.
- Encryption-at-rest (NFR03/NFR04) is **partly done**: the identifying
  `extracted_data` fields are AES-GCM sealed in the column, but face
  embeddings stay readable in pgvector on purpose and rely on host volume
  encryption instead — sealing them would foreclose SQL-side ANN search,
  which duplicate detection needs as tenants grow. The VPS must therefore be
  provisioned with full-disk encryption. See `DASHBOARD-BACKEND.md` §10.
- The **camera → verify path has never run end-to-end**: `getUserMedia`
  requires a secure context, and the dev VM has no camera device at all. It
  is only testable once the app is live on HTTPS — a required gate before
  declaring Phase 6 done.
- **Email delivery is broken** (SMTP send succeeds, mail never arrives).
  Manager signup and PIN reset both depend on emailed links, so this blocks
  launch regardless of everything else.
- **NFR01's 10-second budget** has only ever been measured on a developer
  machine; the Locust run against real VPS hardware is still outstanding.
