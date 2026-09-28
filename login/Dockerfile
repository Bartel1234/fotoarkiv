FROM jakewharton/gphotos-sync:trunk AS sync-binaries
FROM dorowu/ubuntu-desktop-lxde-vnc:latest

# The base image ships Chrome 89 and an obsolete Google APT signing key.
RUN find /etc/apt/sources.list.d -type f -exec sed -i '/dl.google.com\/linux\/chrome\/deb/d' {} + \
    && apt-get update \
    && curl -fsSL https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -o /tmp/google-chrome.deb \
    && apt-get install -y --no-install-recommends /tmp/google-chrome.deb \
    && rm -f /tmp/google-chrome.deb \
    && rm -rf /var/lib/apt/lists/* \
    && google-chrome --version

# Both the interactive login and headless sync must open the same Chrome profile.
# chromedp prefers a chromium executable; this wrapper selects the installed Chrome.
RUN printf '#!/bin/sh\nexec /usr/bin/google-chrome --no-sandbox "$@"\n' > /usr/local/bin/chromium \
    && chmod +x /usr/local/bin/chromium
COPY --from=sync-binaries /usr/bin/gphotos-cdp /usr/local/bin/gphotos-cdp
COPY fotoarkiv-supervisor.conf /etc/supervisor/conf.d/fotoarkiv.conf
