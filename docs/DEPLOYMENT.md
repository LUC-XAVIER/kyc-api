# Deployment

Phase 6. The API, its Postgres, and a TLS-terminating reverse proxy run as a
Docker Compose stack on a single VPS. GitHub Actions builds the image, pushes
it to GHCR, and redeploys over SSH on every green push to `main`.

## 1. Why a VPS, and what to buy

The original plan said Railway/Render. That predates the ML pipeline. The
image carries CPU torch, TensorFlow (via DeepFace), EasyOCR, MediaPipe and
FAISS; roughly 2–3 GB is resident once the models load, and DeepFace caches
another ~150 MB of weights on disk. By the time a PaaS tier is large enough,
a plain VPS is cheaper and less constrained.

| Item | Spec | Indicative cost |
|---|---|---|
| VPS | 4 vCPU / **8 GB** RAM / 80 GB SSD | ~€8–15 per month |
| Domain | any TLD | ~$10–15 per year |
| TLS certificate | Let's Encrypt, automatic via Caddy | free |
| Image registry | GHCR | free for this repo |

8 GB rather than 4: torch and TensorFlow both load into the API process and
Postgres sits alongside them. A 4 GB box boots and then OOMs under concurrent
verifications.

**Enable full-disk encryption when provisioning the VPS.** Face embeddings are
stored unencrypted in pgvector by deliberate choice (see
`DASHBOARD-BACKEND.md` §10); volume encryption is what covers them at rest.
Retrofitting it later means rebuilding the host.

## 2. Host setup (once)

1. Point the domain's **A record at the VPS IP before first start** — Caddy
   solves an ACME challenge over port 80 on boot, and fails if DNS is wrong.
2. Install Docker and the compose plugin.
3. Create the app directory (this is `VPS_APP_DIR` below) and copy in
   `docker/docker-compose.prod.yml` and `docker/Caddyfile`.
4. Write `.env` **next to the compose file, on the host**:

   ```
   ENVIRONMENT=production
   SECRET_KEY=<python -c "import secrets; print(secrets.token_urlsafe(48))">
   API_KEY_PEPPER=<same generator, different value>
   ENCRYPTION_KEY=<python -c "from app.core.crypto import generate_key; print(generate_key())">
   POSTGRES_PASSWORD=<long random>
   APP_DOMAIN=kyc.example.com
   GITHUB_REPOSITORY=<owner>/<repo>   # all lower-case — GHCR rejects capitals
   DASHBOARD_URL=https://kyc.example.com
   EMAIL_ENABLED=true
   SMTP_HOST=...
   SMTP_USER=...
   SMTP_PASSWORD=...
   EMAIL_FROM=KYC-API <no-reply@kyc.example.com>
   ```

   This file is the only place production secrets exist. It is never in the
   image and never in the repo.

   **Back up `ENCRYPTION_KEY` somewhere safe before the first deploy.** It is
   the only thing that can read the encrypted PII columns; losing it means
   losing every client's identity data irrecoverably.

5. First run, to create the schema and seed reference data:

   ```bash
   docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
   docker compose -f docker-compose.prod.yml run --rm api python -m scripts.seed_plans
   docker compose -f docker-compose.prod.yml up -d
   ```

   The seed step is idempotent and also runs on every deploy; the four
   subscription plans are reference data the app cannot function without.

## 3. GitHub configuration

Create a `production` environment (Settings → Environments) and add:

| Secret | Value |
|---|---|
| `VPS_HOST` | VPS IP or hostname |
| `VPS_USER` | deploy user |
| `VPS_SSH_KEY` | private key for that user |
| `VPS_APP_DIR` | absolute path to the app directory |
| `APP_DOMAIN` | e.g. `kyc.example.com` |

Adding a required reviewer to that environment turns every production deploy
into a one-click approval. Recommended: the deploy is automatic, but not
unattended.

## 4. The pipeline

`ci.yml` runs on every push and PR: ruff, `alembic upgrade head` against a
pgvector service, the full pytest suite, then the Angular build and its Karma
tests.

`deploy.yml` triggers on CI **completing successfully on `main`** — via
`workflow_run`, checking `conclusion == 'success'`. It builds the image, pushes
it to GHCR tagged both `latest` and the commit SHA, pulls it on the VPS, runs
migrations, restarts the API, and then polls `/api/v1/health` until it answers.
A deploy that rolls a broken image fails the run rather than reporting success.

Rollback is a `workflow_dispatch` run with `ref` set to a previous SHA.

## 5. Things that will bite

- **Migrations run automatically before the new image serves.** That is safe
  for additive changes, which is the convention here. A destructive migration
  needs a maintenance window, not an automatic deploy.
- **DeepFace weights** are downloaded on first use into `/home/kyc`, mounted
  as the `kyc_models` volume. Without that volume every replacement container
  re-downloads ~150 MB, and the first verification after each deploy pays for
  it.
- **Postgres publishes no ports.** It is reachable only on the compose
  network. Do not add a `ports:` mapping to "debug something" — that exposes
  every embedding and encrypted row to the internet.
- **The camera needs HTTPS.** `getUserMedia` only exists in a secure context,
  which is why capture has never worked on the dev VM. The first real
  camera → verify test can only happen once this is live on the domain.
- **NFR01's 10-second budget has never been measured off a developer laptop.**
  Run the Locust suite against staging before trusting it on shared vCPUs.
