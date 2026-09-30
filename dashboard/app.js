const el = id => document.getElementById(id);
let selectedAccount = null;
const fmt = n => new Intl.NumberFormat('da-DK').format(n);
const human = n => n >= 1024 ** 3 ? (n / 1024 ** 3).toLocaleString('da-DK', {maximumFractionDigits: 1}) + ' GB' : (n / 1024 ** 2).toLocaleString('da-DK', {maximumFractionDigits: 0}) + ' MB';
async function refresh() {
  try {
    const response = await fetch('/api/status', {cache: 'no-store'});
    if (!response.ok) throw new Error('Kunne ikke hente status (' + response.status + ')');
    const s = await response.json();
    const active = (s.accounts || []).find(a => a.email === selectedAccount) || (s.accounts || [])[0];
    if (active) selectedAccount = active.email;
    const view = active || s;
    const label = active ? active.running ? 'Synkroniserer ' + active.email : !active.online ? 'Konto offline: ' + active.email : active.pending ? 'Starter ' + active.email : active.last_exit && active.last_exit !== '0' ? 'Backup fejlede: ' + active.email : 'Klar: ' + active.email : s.label;
    const tone = active ? !active.online || (active.last_exit && active.last_exit !== '0' && !active.running) ? 'error' : active.running ? 'active' : 'pending' : s.tone;
    el('status').textContent = label;
    el('status').dataset.tone = tone;
    el('status-detail').textContent = view.running ? 'Backup kører. Nye filer vises herunder, mens de hentes.' : view.pending ? 'Anmodningen er sendt. Synkroniseringen starter om lidt.' : tone === 'error' ? 'Se aktivitetsloggen for fejlen og kontrollér Google-login.' : 'Dine billeder bliver gemt lokalt på din Unraid-server.';
    el('count').textContent = fmt(s.count);
    el('used').textContent = human(s.bytes);
    el('last-run').textContent = view.last_run;
    el('last-result').textContent = view.last_exit === '0' ? 'Kørsel afsluttet · kontrollér antal filer' : view.last_exit ? 'Fejlede · exitkode ' + view.last_exit : 'Afventer første backup';
    el('next-run').textContent = view.next_run;
    el('activity-badge').textContent = view.running ? '● KØRER' : view.online ? '● LIVE' : '● OFFLINE';
    el('activity-badge').className = 'badge ' + tone;
    el('start').disabled = view.running || view.pending || !view.online;
    el('start').textContent = view.running ? 'Synkroniserer…' : view.pending ? 'Starter snart…' : '↻   Start backup nu';
    el('log').textContent = view.log;
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
  button.addEventListener('click', async event => {
    event.stopPropagation();
    selectedAccount = account;
    if (action === 'rescan' && !window.confirm('Start en fuld gennemgang fra de ældste billeder? De eksisterende filer bevares, men nogle kan blive hentet igen.')) return;
    const feedback = button.closest('.account-card')?.querySelector('.account-feedback');
    if (action === 'start' || action === 'rescan' || action === 'close-login') {
      button.disabled = true;
      button.textContent = 'Sender anmodning…';
      if (feedback) feedback.textContent = 'Sender startanmodning…';
    }
    let popup;
    if (action === 'login') popup = window.open('/login/', 'fotoarkiv-google-login', 'popup=yes,width=1280,height=900,resizable=yes,scrollbars=yes');
    try {
      await postAccount('/api/accounts/' + encodeURIComponent(account) + '/' + action, {});
      if (popup) popup.focus();
      if (action === 'login' && !popup) window.location.href = '/login/';
      if (action === 'start' || action === 'rescan' || action === 'close-login') {
        if (feedback) feedback.textContent = action === 'close-login' ? 'Afslutter login-browseren…' : 'Start er bestilt. Login-browseren lukkes automatisk.';
        await refresh();
      }
    } catch (error) {
      if (popup) popup.close();
      if (feedback) feedback.textContent = 'Kunne ikke starte: ' + error.message;
      button.disabled = false;
      button.textContent = label;
      el('account-message').textContent = error.message;
    }
  });
  return button;
}
function renderAccounts(accounts, summary) {
  const list = el('account-list');
  list.replaceChildren();
  const legacy = {email: 'legacy', folder: 'Hovedmappen (eksisterende konto)', count: null, bytes: null,
                  online: summary.online, running: summary.running, pending: summary.pending, login_active: summary.login_active, last_run: summary.last_run};
  for (const account of [legacy, ...accounts]) {
    const card = document.createElement('div'); card.className = 'account-card';
    if (account.email === selectedAccount) card.style.borderColor = '#8370f5';
    card.addEventListener('click', event => {
      if (event.target.closest('button')) return;
      selectedAccount = account.email; refresh();
    });
    const detail = document.createElement('div');
    const title = document.createElement('strong'); title.textContent = account.email === 'legacy' ? 'Eksisterende konto' : account.email;
    const info = document.createElement('small');
    info.textContent = (account.online ? account.running ? 'Synkroniserer' : account.pending ? 'Afventer start' : 'Klar' : 'Offline') +
      ' · ' + account.folder + (account.count === null ? '' : ' · ' + fmt(account.count) + ' filer / ' + human(account.bytes));
    detail.append(title, info);
    const controls = document.createElement('div'); controls.className = 'account-actions';
    const startButton = actionButton(account.running ? 'Synkroniserer…' : account.pending ? 'Starter snart…' : 'Start backup', account.email, 'start');
    startButton.disabled = account.running || account.pending || !account.online;
    controls.append(actionButton('Google-login ↗', account.email, 'login'), startButton, actionButton('Gennemgå hele arkivet', account.email, 'rescan'));
    const browse = document.createElement('button');
    browse.type = 'button'; browse.className = 'outline'; browse.textContent = 'Se billeder og videoer';
    browse.addEventListener('click', event => {
      event.stopPropagation(); selectedAccount = account.email;
      window.location.assign('/archive/' + encodeURIComponent(account.email));
    });
    controls.append(browse);
    if (account.login_active) controls.append(actionButton('Afslut login', account.email, 'close-login'));
    const feedback = document.createElement('div');
    feedback.className = 'account-feedback';
    feedback.setAttribute('role', 'status');
    feedback.setAttribute('aria-live', 'polite');
    feedback.textContent = account.running ? '● Backup kører nu – nye filer vises i overblikket.' : account.pending ? account.login_active ? '◷ Afslutter login-browseren før backup…' : '◷ Start er bestilt – venter på synkroniseringsmotoren.' : account.login_active ? 'Login-browseren er åben. Start backup lukker den automatisk.' : '';
    card.append(detail, controls, feedback);
    list.append(card);
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
el('start-form').addEventListener('submit', async event => {
  if (!selectedAccount) return;
  event.preventDefault();
  try { await postAccount('/api/accounts/' + encodeURIComponent(selectedAccount) + '/start', {}); await refresh(); }
  catch (error) { el('account-message').textContent = error.message; }
});
refresh();
setInterval(refresh, 8000);
