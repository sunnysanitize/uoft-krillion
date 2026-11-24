# One image for both the API service and the nightly generator job on Cloud Run.
# Base pinned by digest so a retag upstream can't change what ships. Bump it by hand.
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Every package, direct or transitive, is pinned and hash-checked, so a rebuild can't pull in different code.
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.lock

COPY rarest_blue ./rarest_blue

# Run unprivileged, with code the app can't rewrite.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER 10001

# Cloud Run sets PORT. The generator job overrides this with `python -m rarest_blue.entrypoints.cli.generate`.
CMD ["sh", "-c", "exec uvicorn --factory rarest_blue.entrypoints.http.app:create_app --host 0.0.0.0 --port ${PORT:-8080} --no-server-header"]
