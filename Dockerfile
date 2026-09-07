# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts

RUN pip install --upgrade pip

FROM base AS test

COPY tests ./tests
COPY Makefile ./
COPY install.py ./
COPY esp32-dev ./esp32-dev

RUN apt-get update \
    && apt-get install -y --no-install-recommends make \
    && rm -rf /var/lib/apt/lists/* \
    && pip install -e ".[dev]"

ENTRYPOINT ["make"]
CMD ["test"]

FROM base AS runtime

RUN pip install .

ENTRYPOINT ["esp32-dev"]
CMD ["--help"]
