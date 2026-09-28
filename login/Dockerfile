FROM dorowu/ubuntu-desktop-lxde-vnc:latest

# The upstream desktop image bundles Chrome, but its version can lag behind.
# Install Google's current stable package whenever this image is rebuilt.
RUN apt-get update \
    && curl -fsSL https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -o /tmp/google-chrome.deb \
    && apt-get install -y --no-install-recommends /tmp/google-chrome.deb \
    && rm -f /tmp/google-chrome.deb \
    && rm -rf /var/lib/apt/lists/* \
    && google-chrome --version

COPY fotoarkiv-supervisor.conf /etc/supervisor/conf.d/fotoarkiv.conf
