#!/usr/bin/env python3
"""Build a standalone, offline-installable Unraid .plg. Requires Python only."""
import base64
import hashlib
import io
from pathlib import Path
import tarfile
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
VERSION = '0.1.0-beta.3'
DATE = '2026.10.10.2'
PLUGIN_URL = 'https://raw.githubusercontent.com/Bartel1234/fotoarkiv/main/unraid-plugins/pangolin-manager/pangolin-manager.plg'
dest = ROOT / 'dist'
dest.mkdir(exist_ok=True)
buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
    for path in sorted((ROOT / 'src').iterdir()):
        data = path.read_bytes()
        info = tarfile.TarInfo('usr/local/emhttp/plugins/pangolin-manager/' + path.name)
        info.size = len(data)
        info.mode = 0o755 if path.suffix == '.sh' else 0o644
        info.mtime = 0
        archive.addfile(info, io.BytesIO(data))
payload = buffer.getvalue()
sha = hashlib.sha256(payload).hexdigest()
package = '/boot/config/plugins/pangolin-manager/package-' + VERSION + '.tgz'
install = f'''#!/bin/bash
set -eu
if [[ ! -f /etc/unraid-version ]]; then echo "Pangolin Manager kræver Unraid."; exit 1; fi
/usr/bin/php -r '$v=parse_ini_file("/etc/unraid-version")["version"]??"0"; exit(version_compare($v,"7.0.0",">=") && extension_loaded("curl") ? 0 : 1);' || {{ echo "Kræver Unraid 7.x og PHP cURL."; exit 1; }}
echo "{sha}  {package}" | sha256sum --check --status
tar -xzf {package} -C /
chmod 755 /usr/local/emhttp/plugins/pangolin-manager/poll.sh
mkdir -p /var/local/pangolin-manager
chmod 700 /var/local/pangolin-manager
mkdir -p /boot/config/plugins/pangolin-manager
if [[ ! -f /boot/config/plugins/pangolin-manager/settings.json ]]; then
  /usr/bin/php -r 'require "/usr/local/emhttp/plugins/pangolin-manager/lib.php"; pm_write(pm_paths()["config"],pm_defaults());'
fi
printf '%s\\n' '* * * * * /usr/local/emhttp/plugins/pangolin-manager/poll.sh >/dev/null 2>&1' > /boot/config/plugins/pangolin-manager/pangolin-manager.cron
/usr/local/sbin/update_cron
/usr/bin/php /usr/local/emhttp/plugins/pangolin-manager/worker.php >/dev/null 2>&1 || true
echo "Pangolin Manager {VERSION} installeret. Åbn Tools → Pangolin Manager."
'''
remove = '''#!/bin/bash
set -eu
rm -f /boot/config/plugins/pangolin-manager/pangolin-manager.cron
/usr/local/sbin/update_cron
rm -rf /usr/local/emhttp/plugins/pangolin-manager
rm -rf /var/local/pangolin-manager
echo "Pangolin Manager afinstalleret. Indstillinger og din Newt-container er bevaret."
'''
xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<PLUGIN name="pangolin-manager" author="Lars Bartel" version="{DATE}" launch="Tools/PangolinManager" pluginURL="{PLUGIN_URL}" IconFA="exchange" icon="exchange" min="7.0.0">
<CHANGES>0.1.0-beta.3: Lokal Docker-forbindelse, PHP-kompatibilitet og konkrete fejlbeskeder.
0.1.0-beta.2: GitHub-installation og opdateringsadresse.
0.1.0-beta.1: Dashboard-widget, Newt-status, valgfri API, lokale HTTP-kontroller, logs og notifikationer. Første testudgave; ikke afprøvet på en fysisk Unraid-server.</CHANGES>
<FILE Name="{package}" Type="base64"><INLINE>{base64.b64encode(payload).decode()}</INLINE><SHA256>{sha}</SHA256></FILE>
<FILE Run="/bin/bash"><INLINE><![CDATA[{install}]]></INLINE></FILE>
<FILE Run="/bin/bash" Method="remove"><INLINE><![CDATA[{remove}]]></INLINE></FILE>
</PLUGIN>
'''
ET.fromstring(xml)
plg = dest / 'pangolin-manager.plg'
plg.write_text(xml)
(dest / 'SHA256SUMS.txt').write_text(hashlib.sha256(plg.read_bytes()).hexdigest() + '  pangolin-manager.plg\n')
output = dest / ('pangolin-manager-' + VERSION + '.zip')
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
    archive.write(plg, 'pangolin-manager.plg')
    archive.write(dest / 'SHA256SUMS.txt', 'SHA256SUMS.txt')
    for name in ['INSTALLATION-DA.md','README.md','LICENSE','VALIDATION.md','CHANGELOG.md','.gitignore','build.py']:
        archive.write(ROOT / name, name)
    for folder in ['src','tests']:
        for path in sorted((ROOT / folder).rglob('*')):
            if path.is_file() and '__pycache__' not in str(path): archive.write(path, path.relative_to(ROOT))
print(output)
