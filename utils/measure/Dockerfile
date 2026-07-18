# syntax=docker/dockerfile:1

ARG FINAL_STAGE=runtime

FROM node:24-alpine AS frontend-build

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run typecheck && npm test -- --run && npm run build

FROM python:3.14-slim AS python-runtime

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /uvx /bin/

WORKDIR /app

# Install locked third-party dependencies before copying the project. Source
# changes can then reuse this expensive layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

# Use the managed environment in every final image and dependency stage.
ENV PATH="/app/.venv/bin:$PATH"

FROM python-runtime AS ha-app-dependencies

RUN uv sync --locked --extra app --no-install-project

FROM python-runtime AS cli-dependencies

RUN apt-get update && apt-get install -y libgl1 tesseract-ocr && rm -rf /var/lib/apt/lists/* \
    && uv sync --locked --extra cli --extra ocr --no-install-project

FROM ha-app-dependencies AS ha-app

# Copy only the project inputs needed by the final images. In particular,
# local credentials, measurement output, tests, and frontend tooling stay out.
COPY README.md .VERSION ./
COPY measure/ ./measure/
RUN uv sync --locked --extra app

# Serve the compiled frontend from the Home Assistant app image.
COPY --from=frontend-build /frontend/dist /app/measure/static

ENV POWERCALC_MEASURE_DATA_ROOT=/data

EXPOSE 8099

# The Supervisor restarts the app when the container reports unhealthy. A
# restart aborts an active measurement session, which is preferable to
# leaving a hung app running unattended.
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/health', timeout=5)"]

ENTRYPOINT ["python", "-m", "measure.ha_app.main"]
CMD ["--host", "0.0.0.0", "--port", "8099", "--data-root", "/data"]

FROM cli-dependencies AS runtime

# Install direct-device and OCR capabilities only in the standalone CLI image.
# The Home Assistant image stays limited to its entity-based adapters.
COPY README.md .VERSION ./
COPY measure/ ./measure/
RUN uv sync --locked --extra cli --extra ocr

ENTRYPOINT ["python", "-m", "measure.measure"]

# Preserve the standalone CLI as the local default while allowing builders
# without a target option to select the Home Assistant stage.
FROM ${FINAL_STAGE} AS final
