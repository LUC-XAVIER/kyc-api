# KYC-API

Automated biometric identity verification platform for Microfinance
Institutions (MFIs) in Cameroon. Processes a client's National Identity
Card and a live selfie through a multi-stage ML pipeline and returns a
COBAC-compliant KYC result: **VERIFIED**, **PENDING**, or **REJECTED**.

## Stack
- FastAPI, Python 3.11
- DeepFace / ArcFace (face matching)
- Tesseract OCR (NIC field extraction)
- MediaPipe + LBP-SVM (liveness / anti-spoofing)
- PostgreSQL + pgvector, FAISS (duplicate detection)
- Streamlit (dashboard)

## Project layout
```
app/            FastAPI backend (the API service)
  core/         config, security, logging, exceptions
  api/v1/       HTTP routes (API Gateway)
  schemas/      Pydantic request/response models (API contract)
  models/       SQLAlchemy ORM entities (Data Layer)
  db/           engine / session
  services/     business logic (subscription, reporting, audit, ...)
  pipeline/     ML verification pipeline modules
dashboard/      Streamlit app (separate process)
ml/             anti-spoofing training + pipeline evaluation
docker/         Dockerfile + docker-compose (Postgres/pgvector)
scripts/        seed plans, build FAISS index, ...
tests/          unit + integration tests
docs/           analysis & design documents (UML, diagrams)
```

## Getting started

Requires [uv](https://docs.astral.sh/uv/) and Docker.

```bash
# 1. Configure environment
cp .env.example .env

# 2. Install dependencies (API only; add ML/dashboard groups as needed)
uv sync                       # core
uv sync --extra dev           # + tooling & tests
# uv sync --extra ml --extra dashboard   # full stack

# 3. Start Postgres (pgvector)
docker compose -f docker/docker-compose.yml up -d db

# 4. Run the API
uv run uvicorn app.main:app --reload
# Swagger UI: http://localhost:8000/docs

# 5. Run tests / lint
uv run pytest
uv run ruff check .
```

Or run the full stack in containers:

```bash
docker compose -f docker/docker-compose.yml up --build
```

## Build phases
| Phase | Scope |
|-------|-------|
| 0 | Scaffold: config, Docker/Postgres, FastAPI skeleton, tooling ✅ |
| 1 | Data layer: 12 ORM entities, Alembic, seed subscription plans |
| 2 | API gateway + subscription quota enforcement |
| 3 | ML pipeline (preprocess → OCR → liveness → match → duplicate → decision) |
| 3b | Anti-spoofing classifier (academic contribution) |
| 4 | Streamlit dashboard |
| 5 | Compliance reporting, audit trail, drift monitoring |
| 6 | Hardening, evaluation, deployment |
