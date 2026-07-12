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

# Install git for dependencies that come from git repositories
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

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

ENTRYPOINT ["python", "-m", "measure.app"]
CMD ["--host", "0.0.0.0", "--port", "8099", "--data-root", "/data"]

FROM python-runtime AS runtime

# OCR remains a CLI-only capability. Keep its native dependencies out of the
# Home Assistant image, where only Home Assistant entity measurements are supported.
RUN uv sync --locked --extra ocr

ENTRYPOINT ["python", "-m", "measure.measure"]
