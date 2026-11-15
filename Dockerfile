# zjm-rag runs only inside this hardened container. See docs/lean/07-container.md.

# zg is a native binary. Node only fetches it, so Node stays in this stage, and the image
# takes the binary plus the four libraries it links against (`ldd`), nothing else.
FROM node:22-slim AS zg
RUN npm install -g @zvec/zvec-grep@0.3.0 \
    && cd /usr/local/lib/node_modules/@zvec/zvec-grep \
    && mkdir -p /zg/bin /zg/lib \
    && cp bin/zg.exe /zg/bin/zg \
    && cp lib/libzvec_c_api.so lib/libllama.so.0 lib/libggml.so.0 lib/libggml-base.so.0 /zg/lib/ \
    && cp node_modules/@zvec/zvec-grep-*/LICENSE /zg/LICENSE

FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git age \
    && rm -rf /var/lib/apt/lists/*

COPY --from=zg /zg /opt/zg
RUN ln -s /opt/zg/bin/zg /usr/local/bin/zg

WORKDIR /src
COPY . /src
RUN pip install --no-cache-dir .

ENV ZVEC_GREP_MODEL_CACHE=/opt/zjm/models
RUN mkdir -p /opt/zjm/models/code-seed /opt/zjm/models/multi-seed \
    && echo seed > /opt/zjm/models/code-seed/seed.md \
    && echo seed > /opt/zjm/models/multi-seed/seed.md \
    && (cd /opt/zjm/models/code-seed && ZVEC_GREP_HOME=/tmp/code-seed-home zg --index . \
        --embedding local/potion-code-16m-v2 --mode direct --hidden) \
    && (cd /opt/zjm/models/multi-seed && ZVEC_GREP_HOME=/tmp/multi-seed-home zg --index . \
        --embedding local/potion-multilingual-128m --mode direct --hidden) \
    && rm -rf /opt/zjm/models/code-seed /opt/zjm/models/multi-seed /tmp/code-seed-home /tmp/multi-seed-home \
    && chmod -R a+rX /opt/zjm/models

ENV ZJM_IN_CONTAINER=1 ZJM_CONFIG=/etc/zjm/config.json HOME=/tmp/home

RUN useradd -u 10001 -M -d /data -s /usr/sbin/nologin zjm \
    && mkdir -p /data /tmp/home \
    && chown 10001:10001 /data /tmp/home \
    && chmod 0700 /data

VOLUME /data
USER 10001:10001

ENTRYPOINT ["zjm"]
