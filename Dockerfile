# zjm-rag runs only inside this hardened container. See docs/lean/07-container.md.

# zjm-engine is built from engine/ with the toolchain pinned in engine/rust-toolchain.toml. The same
# stage fetches the four model files at pinned revisions and checks each sha256: a mismatch fails the
# build. The multilingual model's tokenizer is then turned into the memory-mappable vocab/ folder.
FROM rust:1.93.0-slim-bookworm AS engine
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /engine
COPY engine /engine
RUN cargo build --release --locked

ARG MULTI_REVISION=73908c3438cf03b6a01bcb9611d62b23d0726f08
ARG MULTI_MODEL_SHA256=14b5eb39cb4ce5666da8ad1f3dc6be4346e9b2d601c073302fa0a31bf7943397
ARG MULTI_TOKENIZER_SHA256=19f1909063da3cfe3bd83a782381f040dccea475f4816de11116444a73e1b6a1
ARG CODE_REVISION=e9d2a44ca6a05ac6685f3b23709ea57eb7352d5b
ARG CODE_MODEL_SHA256=75cf7a6c2171b230ad19b1e7d8e0b1aee86da5a02af8e7cacedd9921d227623c
ARG CODE_TOKENIZER_SHA256=107bbdcbad4bff1d299b7a4c3a2fb17c52890688b7dd0e4c9deab79d3c4f3d45
RUN set -eu; \
    fetch() { \
        mkdir -p "/models/$2"; \
        for file in model.safetensors tokenizer.json; do \
            curl -fsSL --retry 3 -o "/models/$2/$file" "https://huggingface.co/$1/resolve/$3/$file"; \
        done; \
        echo "$4  /models/$2/model.safetensors" | sha256sum -c -; \
        echo "$5  /models/$2/tokenizer.json" | sha256sum -c -; \
    }; \
    fetch minishlab/potion-multilingual-128M potion-multilingual-128m "$MULTI_REVISION" \
        "$MULTI_MODEL_SHA256" "$MULTI_TOKENIZER_SHA256"; \
    fetch minishlab/potion-code-16M-v2 potion-code-16m-v2 "$CODE_REVISION" \
        "$CODE_MODEL_SHA256" "$CODE_TOKENIZER_SHA256"; \
    /engine/target/release/zjm-engine vocab /models/potion-multilingual-128m/tokenizer.json \
        /models/potion-multilingual-128m/vocab; \
    chmod -R a+rX /models

FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git age \
    && rm -rf /var/lib/apt/lists/*

COPY --from=engine /engine/target/release/zjm-engine /usr/local/bin/zjm-engine
COPY --from=engine /models /opt/zjm/models

WORKDIR /src
COPY . /src
RUN pip install --no-cache-dir .

ENV ZJM_IN_CONTAINER=1 ZJM_CONFIG=/etc/zjm/config.json HOME=/tmp/home

RUN useradd -u 10001 -M -d /data -s /usr/sbin/nologin zjm \
    && mkdir -p /data /tmp/home \
    && chown 10001:10001 /data /tmp/home \
    && chmod 0700 /data

VOLUME /data
USER 10001:10001

ENTRYPOINT ["zjm"]
