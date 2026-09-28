const el = id => document.getElementById(id);
const fmt = n => new Intl.NumberFormat('da-DK').format(n);
const human = n => n >= 1024 ** 3 ? (n / 1024 ** 3).toLocaleString('da-DK', {maximumFractionDigits: 1}) + ' GB' : (n / 1024 ** 2).toLocaleString('da-DK', {maximumFractionDigits: 0}) + ' MB';
async function refresh() {
  try {
    const response = await fetch('/api/status', {cache: 'no-store'});
    if (!response.ok) throw new Error('Kunne ikke hente status (' + response.status + ')');
    const s = await response.json();
    el('status').textContent = s.label;
    el('status').dataset.tone = s.tone;
    el('status-detail').textContent = s.running ? 'Backup kører. Nye filer vises herunder, mens de hentes.' : s.pending ? 'Anmodningen er sendt. Synkroniseringen starter om lidt.' : s.tone === 'error' ? 'Se aktivitetsloggen for fejlen og kontrollér Google-login.' : 'Dine billeder bliver gemt lokalt på din Unraid-server.';
    el('count').textContent = fmt(s.count);
    el('used').textContent = human(s.bytes);
    el('last-run').textContent = s.last_run;
    el('last-result').textContent = s.last_exit === '0' ? 'Kørsel gennemført' : s.last_exit ? 'Fejlede · exitkode ' + s.last_exit : 'Afventer første backup';
    el('next-run').textContent = s.next_run;
    el('activity-badge').textContent = s.running ? '● KØRER' : s.online ? '● LIVE' : '● OFFLINE';
    el('activity-badge').className = 'badge ' + s.tone;
    el('start').disabled = s.running || s.pending || !s.online;
    el('start').textContent = s.running ? 'Synkroniserer…' : s.pending ? 'Starter snart…' : '↻   Start backup nu';
    el('log').textContent = s.log;
    const list = el('recent');
    list.replaceChildren();
    if (!s.recent.length) list.textContent = 'Der er endnu ingen filer i backupmappen.';
    for (const f of s.recent) {
      const row = document.createElement('div'); row.className = 'file-row';
      const icon = document.createElement('span'); icon.className = 'file-icon'; icon.textContent = /\.(mp4|mov|avi|mkv|webm)$/i.test(f.name) ? '▶' : '▧';
      const middle = document.createElement('div'); middle.className = 'file-middle';
      const title = document.createElement('b'); title.textContent = f.name; title.title = f.name;
      const sub = document.createElement('small'); sub.textContent = f.time;
      const size = document.createElement('small'); size.textContent = human(f.bytes);
      middle.append(title, sub); row.append(icon, middle, size); list.append(row);
    }
    el('free').textContent = s.total ? human(s.free) + ' fri' : '–';
    el('disk-bar').style.width = s.total ? Math.min(100, Math.max(0, 100 * (s.total - s.free) / s.total)) + '%' : '0%';
    el('updated').textContent = 'Opdateret ' + new Date().toLocaleTimeString('da-DK', {hour: '2-digit', minute: '2-digit', second: '2-digit'});
  } catch (error) {
    el('status').textContent = 'Forbindelsen er afbrudt';
    el('status').dataset.tone = 'error';
    el('status-detail').textContent = error.message;
    el('updated').textContent = 'Kunne ikke opdatere';
  }
}
el('refresh').addEventListener('click', refresh);
el('open-login').addEventListener('click', () => {
  const popup = window.open('/login/', 'fotoarkiv-google-login', 'popup=yes,width=1280,height=900,resizable=yes,scrollbars=yes');
  if (popup) popup.focus();
  else window.location.href = '/login/';
});
refresh();
setInterval(refresh, 8000);
