# Multi-stage production Dockerfile for TraceOps SRE Engine
# Target: Native Google Cloud Run

# Stage 1: Build & dependency compilation
FROM python:3.11-slim as builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Minimal runtime image
FROM python:3.11-slim as runner

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy source tree
COPY . .

# Cloud Run non-root user
RUN useradd --create-home --shell /usr/sbin/nologin traceops \
    && chown -R traceops:traceops /app

USER traceops

ENV PYTHONUNBUFFERED=1 \
    PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/healthz || exit 1

CMD exec uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 2 --loop uvloop
