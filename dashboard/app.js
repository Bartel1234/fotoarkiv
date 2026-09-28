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
    renderAccounts(s.accounts || [], s);
  } catch (error) {
    el('status').textContent = 'Forbindelsen er afbrudt';
    el('status').dataset.tone = 'error';
    el('status-detail').textContent = error.message;
    el('updated').textContent = 'Kunne ikke opdatere';
  }
}
el('refresh').addEventListener('click', refresh);
const token = document.querySelector('#start-form input[name=token]').value;
async function postAccount(url, data) {
  const response = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({...data, token})});
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}
function actionButton(label, account, action) {
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'outline'; button.textContent = label;
  button.addEventListener('click', async () => {
    let popup;
    if (action === 'login') popup = window.open('/login/', 'fotoarkiv-google-login', 'popup=yes,width=1280,height=900,resizable=yes,scrollbars=yes');
    try {
      await postAccount('/api/accounts/' + encodeURIComponent(account) + '/' + action, {});
      if (popup) popup.focus();
      if (action === 'login' && !popup) window.location.href = '/login/';
      if (action === 'start') refresh();
    } catch (error) {
      if (popup) popup.close();
      el('account-message').textContent = error.message;
    }
  });
  return button;
}
function renderAccounts(accounts, summary) {
  const list = el('account-list'); list.replaceChildren();
  const legacy = {email: 'legacy', folder: 'Hovedmappen (eksisterende konto)', count: null, bytes: null,
                  online: summary.online, running: summary.running, last_run: summary.last_run};
  for (const account of [legacy, ...accounts]) {
    const card = document.createElement('div'); card.className = 'account-card';
    const detail = document.createElement('div');
    const title = document.createElement('strong'); title.textContent = account.email === 'legacy' ? 'Eksisterende konto' : account.email;
    const info = document.createElement('small');
    info.textContent = (account.online ? account.running ? 'Synkroniserer' : 'Klar' : 'Offline') +
      ' · ' + account.folder + (account.count === null ? '' : ' · ' + fmt(account.count) + ' filer / ' + human(account.bytes));
    detail.append(title, info);
    const controls = document.createElement('div'); controls.className = 'account-actions';
    controls.append(actionButton('Google-login ↗', account.email, 'login'), actionButton('Start backup', account.email, 'start'));
    card.append(detail, controls); list.append(card);
  }
}
el('add-account-form').addEventListener('submit', async event => {
  event.preventDefault();
  const email = el('account-email').value.trim();
  try {
    const result = await postAccount('/api/accounts', {email});
    el('account-message').textContent = 'Konto tilføjet. Mappe: ' + result.folder;
    el('add-account-form').reset();
    await refresh();
  } catch (error) { el('account-message').textContent = error.message; }
});
refresh();
setInterval(refresh, 8000);
