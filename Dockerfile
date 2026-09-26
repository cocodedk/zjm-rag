# zjm-rag runs only inside this hardened container. See docs/lean/07-container.md.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @zvec/zvec-grep@0.2.2 @anthropic-ai/claude-code@2.1.283 \
    && apt-get purge -y curl gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY . /src
RUN pip install --no-cache-dir .

ENV ZVEC_GREP_MODEL_CACHE=/opt/zjm/models
RUN mkdir -p /opt/zjm/models/code-seed /opt/zjm/models/multi-seed \
    && echo seed > /opt/zjm/models/code-seed/seed.md \
    && echo seed > /opt/zjm/models/multi-seed/seed.md \
    && (cd /opt/zjm/models/code-seed && ZVEC_GREP_HOME=/tmp/code-seed-home zg index . \
        --embedding local/potion-code-16m-v2 --mode direct --hidden) \
    && (cd /opt/zjm/models/multi-seed && ZVEC_GREP_HOME=/tmp/multi-seed-home zg index . \
        --embedding local/potion-multilingual-128m --mode direct --hidden) \
    && rm -rf /opt/zjm/models/code-seed /opt/zjm/models/multi-seed /tmp/code-seed-home /tmp/multi-seed-home

ENV ZJM_IN_CONTAINER=1 ZJM_CONFIG=/etc/zjm/config.json HOME=/tmp/home

RUN useradd -u 10001 -M -d /data -s /usr/sbin/nologin zjm \
    && mkdir -p /data /tmp/home \
    && chown 10001:10001 /data /tmp/home \
    && chmod 0700 /data

VOLUME /data
USER 10001:10001

ENTRYPOINT ["zjm"]
