# syntax=docker/dockerfile:1

FROM node:24-alpine AS frontend-build

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run typecheck && npm test -- --run && npm run build

FROM python:3.14-slim AS python-runtime

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy only the package inputs needed by the runtime image. In particular,
# local credentials, measurement output, tests, and frontend tooling stay out.
COPY pyproject.toml uv.lock README.md .VERSION ./
COPY measure/ ./measure/

# Create virtual environment and install dependencies
RUN uv sync --locked

# The CLI does not serve these files, but keeping one Python base avoids
# dependency drift between the standalone and Home Assistant images.
COPY --from=frontend-build /frontend/dist /app/measure/static

# Set PATH to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"

FROM python-runtime AS ha-app

ENV POWERCALC_MEASURE_DATA_ROOT=/data

EXPOSE 8099

# The Supervisor restarts the app when the container reports unhealthy. A
# restart aborts an active measurement session, which is preferable to
# leaving a hung app running unattended.
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/health', timeout=5)"]

ENTRYPOINT ["python", "-m", "measure.ha_app.main"]
CMD ["--host", "0.0.0.0", "--port", "8099", "--data-root", "/data"]

FROM python-runtime AS runtime

# Install direct-device and OCR capabilities only in the standalone CLI image.
# The Home Assistant image stays limited to its entity-based adapters.
RUN apt-get update && apt-get install -y libgl1 tesseract-ocr && rm -rf /var/lib/apt/lists/* \
    && uv sync --locked --extra cli --extra ocr

ENTRYPOINT ["python", "-m", "measure.measure"]
