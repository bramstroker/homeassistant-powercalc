# syntax=docker/dockerfile:1

# The builder image, used to build the virtual environment
FROM python:3.13-bullseye AS builder

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

WORKDIR /app

COPY pyproject.toml ./

RUN python -m venv .venv && \
    . .venv/bin/activate && \
    uv pip install -e . && \
    uv pip install git+https://github.com/studioimaginaire/phue.git@6d8976be9b17da94887365e001e8475fe58c5f2d

# The runtime image, used to just run the code provided its virtual environment
FROM python:3.13-slim-bullseye AS runtime

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}
COPY . .

ENTRYPOINT ["python", "-m", "measure.measure"]
