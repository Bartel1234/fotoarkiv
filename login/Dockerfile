FROM golang:1.26-alpine AS sync-binaries
WORKDIR /src/gphotos-cdp
COPY go.mod go.sum ./
RUN go mod download
COPY gphotos-cdp-main.go ./main.go
RUN CGO_ENABLED=0 go build -buildvcs=false -mod=readonly -o /go/bin/gphotos-cdp .
FROM dorowu/ubuntu-desktop-lxde-vnc:latest

# The base image ships Chrome 89 and an obsolete Google APT signing key.
RUN find /etc/apt/sources.list.d -type f -exec sed -i '/dl.google.com\/linux\/chrome\/deb/d' {} + \
    && apt-get update \
    && curl -fsSL https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -o /tmp/google-chrome.deb \
    && apt-get install -y --no-install-recommends /tmp/google-chrome.deb \
    && rm -f /tmp/google-chrome.deb \
    && rm -rf /var/lib/apt/lists/* \
    && google-chrome --version

# Use the same Chrome and profile format for login and headless sync.
RUN printf '#!/bin/sh\nexec /usr/bin/google-chrome --no-sandbox "$@"\n' > /usr/local/bin/chromium \
    && chmod +x /usr/local/bin/chromium
COPY --from=sync-binaries /go/bin/gphotos-cdp /usr/local/bin/gphotos-cdp
RUN gphotos-cdp -h >/dev/null 2>&1 || test "$?" -eq 2
COPY fotoarkiv-supervisor.conf /etc/supervisor/conf.d/fotoarkiv.conf

COPY organize.py /usr/local/bin/fotoarkiv-organize.py
RUN python3 --version

COPY organize-one.sh /usr/local/bin/fotoarkiv-organize-one
RUN chmod +x /usr/local/bin/fotoarkiv-organize-one
