FROM golang:1.26-alpine AS sync-binaries
WORKDIR /src/gphotos-cdp
COPY login/go.mod login/go.sum ./
RUN go mod download
COPY login/gphotos-cdp-main.go ./main.go
RUN CGO_ENABLED=0 go build -buildvcs=false -mod=readonly -o /go/bin/gphotos-cdp .

FROM python:3.12-slim-bookworm
ARG VERSION=0.2.0-beta.6
ARG REVISION
LABEL org.opencontainers.image.title="PhotoHarbor" \
      org.opencontainers.image.description="Local backup for Google Photos" \
      org.opencontainers.image.source="https://github.com/Bartel1234/fotoarkiv" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.revision="$REVISION"
ARG TARGETARCH
RUN test "${TARGETARCH:-amd64}" = amd64 \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl ffmpeg supervisor xvfb openbox x11-utils util-linux procps fonts-liberation tzdata \
    && curl -fsSL https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -o /tmp/google-chrome.deb \
    && apt-get install -y --no-install-recommends /tmp/google-chrome.deb \
    && rm /tmp/google-chrome.deb \
    && rm -rf /var/lib/apt/lists/* \
    && google-chrome --version
RUN pip install --no-cache-dir 'aiohttp>=3.10,<4' 'zipstream-ng>=1.8,<2' 'Pillow>=11,<13'
COPY --from=sync-binaries /go/bin/gphotos-cdp /usr/local/bin/gphotos-cdp
RUN printf '#!/bin/sh\nexec /usr/bin/google-chrome --no-sandbox "$@"\n' > /usr/local/bin/chromium \
    && chmod +x /usr/local/bin/chromium
COPY dashboard/ /app/
COPY VERSION /app/VERSION
COPY worker.sh account-worker.sh /controller/
COPY login/login-loop.sh /controller/login-loop.sh
COPY login/organize.py /usr/local/bin/fotoarkiv-organize.py
COPY login/organize-one.sh /usr/local/bin/fotoarkiv-organize-one
COPY container/ /container/
RUN chmod +x /usr/local/bin/fotoarkiv-organize-one /container/entrypoint.sh \
    && mkdir -p /config /accounts /control /download \
    && ln -s /config /tmp/gphotos-cdp
ENV DISPLAY=:99 RESOLUTION=1280x800 TZ=Europe/Copenhagen PHOTOS_DIR=/download
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 CMD ["python", "/container/healthcheck.py"]
ENTRYPOINT ["/container/entrypoint.sh"]

