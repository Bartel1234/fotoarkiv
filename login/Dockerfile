FROM dorowu/ubuntu-desktop-lxde-vnc:latest

# The base image ships Chrome 89 and an obsolete Google APT signing key.
# Remove its Google repository before refreshing Ubuntu's package lists.
RUN find /etc/apt/sources.list.d -type f -exec sed -i '/dl.google.com\/linux\/chrome\/deb/d' {} + \
    && apt-get update \
    && curl -fsSL https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -o /tmp/google-chrome.deb \
    && apt-get install -y --no-install-recommends /tmp/google-chrome.deb \
    && rm -f /tmp/google-chrome.deb \
    && rm -rf /var/lib/apt/lists/* \
    && google-chrome --version

COPY fotoarkiv-supervisor.conf /etc/supervisor/conf.d/fotoarkiv.conf
