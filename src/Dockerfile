# One image for both the API service and the nightly generator job on Cloud Run.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY rarest_blue ./rarest_blue

# Cloud Run sets PORT. The generator job overrides this with `python -m rarest_blue.generate`.
CMD ["sh", "-c", "exec uvicorn rarest_blue.api:app --host 0.0.0.0 --port ${PORT:-8080}"]
