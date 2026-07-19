# syntax=docker/dockerfile:1

# Two stages: the ML stack needs a compiler to install but not to run, and
# leaving build-essential in the final image adds hundreds of megabytes to
# something already large because of torch and tensorflow.
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# The ML wheels are huge (torch, and tensorflow alone is ~600 MB). uv's
# default per-download timeout is 30s, which a large wheel on a slow link
# can exceed; raise it so the install doesn't abort mid-download.
ENV UV_HTTP_TIMEOUT=600

WORKDIR /app

# Dependencies first, from the lock file, so the layer is cached until the
# lock actually changes. --frozen refuses to silently re-resolve: the image
# must contain exactly what CI tested.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --extra ml

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-editable --extra ml


FROM python:3.11-slim AS runtime

# Runtime libraries only. tesseract for the OCR stage; libGL/glib for OpenCV;
# libgles2 + libegl1 for MediaPipe's face detector (it dlopen's
# libGLESv2.so.2 / libEGL.so.1 even on a headless CPU box); libpq for psycopg.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        tesseract-ocr \
        libgl1 \
        libglib2.0-0 \
        libgles2 \
        libegl1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Never run the API as root: a pipeline that shells out to OCR and decodes
# attacker-supplied images is exactly where you want a non-privileged user.
RUN useradd --create-home --uid 1000 kyc

WORKDIR /app

COPY --from=builder --chown=kyc:kyc /app/.venv /app/.venv
COPY --chown=kyc:kyc . .

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# DeepFace fetches its ArcFace / anti-spoof weights on first use and caches
# them here. Mount a volume at this path in production, or every replacement
# container re-downloads ~150 MB and the first verification pays for it.
ENV DEEPFACE_HOME=/home/kyc

USER kyc

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
