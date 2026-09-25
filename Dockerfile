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

RUN pip install "pip==25.2"

FROM base AS test

COPY tests ./tests
COPY Makefile ./
COPY install.py ./
COPY esp32-dev ./esp32-dev
COPY Dockerfile compose.yaml ./
COPY .github/workflows/container.yml .github/workflows/container.yml

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

FROM runtime AS toolchain

ENV DEBIAN_FRONTEND=noninteractive \
    ESP32_DEV_PREFIX=/opt/esp32-dev \
    IDF_TOOLS_PATH=/opt/esp32-dev/.espressif \
    PLATFORMIO_CORE_DIR=/opt/esp32-dev/platformio \
    GIT_CONFIG_COUNT=1 \
    GIT_CONFIG_KEY_0=safe.directory \
    GIT_CONFIG_VALUE_0=/workspace

ARG IDF_TARGETS=esp32
ENV IDF_TARGETS=${IDF_TARGETS}

RUN esp32-dev setup \
        --prefix /opt/esp32-dev \
        --idf-targets "${IDF_TARGETS}" \
        --skip-udev \
        --skip-dialout \
        --skip-shell \
        --no-sudo \
    && chmod -R a+rX /opt/esp32-dev \
    && chmod +x /app/scripts/toolchain-entrypoint.sh \
    && /app/scripts/toolchain-entrypoint.sh python -m esptool version \
    && /app/scripts/toolchain-entrypoint.sh pio --version \
    && /app/scripts/toolchain-entrypoint.sh idf.py --version \
    && /app/scripts/toolchain-entrypoint.sh cargo --version \
    && /app/scripts/toolchain-entrypoint.sh bash -ec 'command -v esp-generate' \
    && /app/scripts/toolchain-entrypoint.sh idf.py create-project --path /tmp/idf-smoke smoke \
    && /app/scripts/toolchain-entrypoint.sh bash -ec 'cd /tmp/idf-smoke && idf.py set-target "${IDF_TARGETS%%,*}" && idf.py build' \
    && rm -rf /tmp/idf-smoke \
    && mkdir -p /tmp/pio-smoke/src \
    && printf '%s\n' '[env:esp32dev]' 'platform = espressif32' 'board = esp32dev' 'framework = arduino' > /tmp/pio-smoke/platformio.ini \
    && printf '%s\n' 'void setup(){}' 'void loop(){}' > /tmp/pio-smoke/src/main.cpp \
    && /app/scripts/toolchain-entrypoint.sh pio run -d /tmp/pio-smoke \
    && rm -rf /tmp/pio-smoke \
    && groupadd --gid 1000 esp \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash esp \
    && chown -R esp:esp /opt/esp32-dev /workspace

USER esp
WORKDIR /workspace
ENTRYPOINT ["/app/scripts/toolchain-entrypoint.sh"]
CMD ["idf.py", "--version"]
