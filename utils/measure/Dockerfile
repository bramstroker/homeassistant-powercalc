# syntax=docker/dockerfile:1

FROM python:3.13-slim-bullseye AS runtime

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install git for dependencies that come from git repositories
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy all source code (needed for building the local package)
COPY . .

# Create virtual environment and install dependencies
RUN uv sync --locked

# Set PATH to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["python", "-m", "measure.measure"]
