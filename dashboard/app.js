const el = id => document.getElementById(id);
let selectedAccount = null;
let refreshNumber = 0;
const fmt = n => new Intl.NumberFormat(I18n.locale()).format(n);
const human = n => n >= 1024 ** 3 ? (n / 1024 ** 3).toLocaleString(I18n.locale(), {maximumFractionDigits: 1}) + ' GB' : (n / 1024 ** 2).toLocaleString(I18n.locale(), {maximumFractionDigits: 0}) + ' MB';
async function refresh() {
  const number = ++refreshNumber;
  try {
    const response = await fetch('/api/status', {cache: 'no-store'});
    if (!response.ok) throw new Error(I18n.t('Kunne ikke hente status (') + response.status + ')');
    const s = await response.json();
    if (number !== refreshNumber) return;
    const active = selectedAccount === 'legacy' ? null : (s.accounts || []).find(a => a.email === selectedAccount) || (s.accounts || [])[0];
    if (active) selectedAccount = active.email;
    const view = active || s;
    const phase = I18n.phase(view);
    const label = phase ? phase.title + (active ? " · " + active.email : "") : active ? active.running ? I18n.t('Synkroniserer') + ' ' + active.email : !active.online ? I18n.t('Konto offline: ') + active.email : active.pending ? I18n.t('Starter ') + active.email : active.last_exit === '130' ? I18n.t('Backup afbrudt: ') + active.email : active.last_exit && active.last_exit !== '0' ? I18n.t('Backup fejlede: ') + active.email : I18n.t('Klar: ') + active.email : s.label;
    const tone = active ? !active.online || (active.last_exit && active.last_exit !== '0' && active.last_exit !== '130' && !active.running) ? 'error' : active.running ? 'active' : 'pending' : s.tone;
    el('status').textContent = label;
    el('status').dataset.tone = tone;
    el('status-detail').textContent = phase ? phase.detail : view.running ? I18n.t('Backup kører. Nye filer vises herunder, mens de hentes.') : view.pending ? I18n.t('Anmodningen er sendt. Synkroniseringen starter om lidt.') : tone === 'error' ? I18n.t('Se aktivitetsloggen for fejlen og kontrollér Google-login.') : I18n.t('Dine billeder bliver gemt lokalt på din Unraid-server.');
    el('count').textContent = fmt(s.count);
    el('used').textContent = human(s.bytes);
    el('last-run').textContent = view.last_run;
    el('last-result').textContent = view.last_exit === '130' ? I18n.t('Afbrudt af brugeren') : view.last_exit === '0' ? I18n.t('Kørsel afsluttet · kontrollér antal filer') : view.last_exit ? I18n.t('Fejlede · exitkode ') + view.last_exit : I18n.t('Afventer første backup');
    el('next-run').textContent = view.next_run;
    el('activity-badge').textContent = view.running ? I18n.t('● KØRER') : view.online ? '● LIVE' : '● OFFLINE';
    el('activity-badge').className = 'badge ' + tone;
    el('start').disabled = view.running || view.pending || view.stopping || view.paused || !view.online;
    el('start').textContent = phase ? phase.title + '…' : view.running ? I18n.t('Synkroniserer…') : view.pending ? I18n.t('Starter snart…') : I18n.t('↻   Start backup nu');
    el('log').textContent = view.log;
    const list = el('recent');
    list.replaceChildren();
    if (!s.recent.length) list.textContent = I18n.t('Der er endnu ingen filer i backupmappen.');
    for (const f of s.recent) {
      const row = document.createElement('div'); row.className = 'file-row';
      const icon = document.createElement('span'); icon.className = 'file-icon'; icon.textContent = /\.(mp4|mov|avi|mkv|webm)$/i.test(f.name) ? '▶' : '▧';
      const middle = document.createElement('div'); middle.className = 'file-middle';
      const title = document.createElement('b'); title.textContent = f.name; title.title = f.name;
      const sub = document.createElement('small'); sub.textContent = f.time;
      const size = document.createElement('small'); size.textContent = human(f.bytes);
      middle.append(title, sub); row.append(icon, middle, size); list.append(row);
    }
    el('free').textContent = s.total ? human(s.free) + I18n.t(' fri') : '–';
    el('disk-bar').style.width = s.total ? Math.min(100, Math.max(0, 100 * (s.total - s.free) / s.total)) + '%' : '0%';
    el('updated').textContent = I18n.t('Opdateret ') + new Date().toLocaleTimeString(I18n.locale(), {hour: '2-digit', minute: '2-digit', second: '2-digit'});
    renderAccounts(s.accounts || [], s);
    updateAccountTools(s);
  } catch (error) {
    if (number !== refreshNumber) return;
    el('status').textContent = I18n.t('Forbindelsen er afbrudt');
    el('status').dataset.tone = 'error';
    el('status-detail').textContent = error.message;
    el('updated').textContent = I18n.t('Kunne ikke opdatere');
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
    if (action === 'rescan' && !window.confirm(I18n.t('Start en fuld gennemgang fra de ældste billeder? De eksisterende filer bevares, men nogle kan blive hentet igen.'))) return;
    const feedback = button.closest('.account-card')?.querySelector('.account-feedback');
    if (action === 'start' || action === 'rescan' || action === 'close-login' || action === 'stop') {
      button.disabled = true;
      button.textContent = I18n.t('Sender anmodning…');
      if (feedback) feedback.textContent = action === 'stop' ? I18n.t('Sender anmodning om at afbryde…') : I18n.t('Sender anmodning…');
    }
    let popup;
    if (action === 'login') popup = window.open('/login/?account=' + encodeURIComponent(account), 'fotoarkiv-google-login', 'popup=yes,width=1280,height=900,resizable=yes,scrollbars=yes');
    try {
      await postAccount('/api/accounts/' + encodeURIComponent(account) + '/' + action, {});
      if (popup) popup.focus();
      if (action === 'login' && !popup) window.location.href = '/login/?account=' + encodeURIComponent(account);
      if (action === 'start' || action === 'rescan' || action === 'close-login' || action === 'stop') {
        if (feedback) feedback.textContent = action === 'stop' ? I18n.t('Afbryder backup…') : action === 'close-login' ? I18n.t('Afslutter login-browseren…') : I18n.t('Start er bestilt. Login-browseren lukkes automatisk.');
        await refresh();
      }
    } catch (error) {
      if (popup) popup.close();
      if (feedback) feedback.textContent = I18n.t('Anmodningen mislykkedes: ') + error.message;
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
  const legacy = {...summary, email: 'legacy', folder: I18n.t('Hovedmappen (eksisterende konto)'), count: null, bytes: null,
                  online: summary.online, running: summary.running, pending: summary.pending, stopping: summary.stopping, login_active: summary.login_active, last_run: summary.last_run};
  for (const account of [legacy, ...accounts]) {
    const card = document.createElement('div'); card.className = 'account-card';
    if (account.email === selectedAccount) card.style.borderColor = '#8370f5';
    card.addEventListener('click', event => {
      if (event.target.closest('button')) return;
      selectedAccount = account.email; refresh();
    });
    const detail = document.createElement('div');
    const title = document.createElement('strong'); title.textContent = account.email === 'legacy' ? I18n.t('Eksisterende konto') : account.email;
    const phase = I18n.phase(account);
    const info = document.createElement('small');
    info.textContent = (phase ? phase.title : account.online ? account.running ? I18n.t('Synkroniserer') : account.pending ? I18n.t('Afventer start') : I18n.t('Klar') : 'Offline') +
      ' · ' + account.folder + (account.count === null ? '' : ' · ' + fmt(account.count) + I18n.t(' filer / ') + human(account.bytes));
    detail.append(title, info);
    const controls = document.createElement('div'); controls.className = 'account-actions';
    const startButton = actionButton(phase ? phase.title + '…' : account.running ? I18n.t('Synkroniserer…') : account.pending ? I18n.t('Starter snart…') : I18n.t('Start backup'), account.email, 'start');
    startButton.disabled = account.running || account.pending || account.stopping || account.paused || !account.online;
    controls.append(actionButton(I18n.t('Google-login ↗'), account.email, 'login'), startButton, actionButton(I18n.t('Gennemgå hele arkivet'), account.email, 'rescan'));
    const browse = document.createElement('button');
    browse.type = 'button'; browse.className = 'outline'; browse.textContent = I18n.t('Se billeder og videoer');
    browse.addEventListener('click', event => {
      event.stopPropagation(); selectedAccount = account.email;
      window.location.assign('/archive/' + encodeURIComponent(account.email));
    });
    controls.append(browse);
    const tools=document.createElement('button');tools.type='button';tools.className='outline';tools.textContent=I18n.t('Indstillinger og historik');
    tools.addEventListener('click',event=>{event.stopPropagation();openAccountTools(account);});controls.append(tools);
    if(account.paused || (account.running && ['backup','repair'].includes(account.run_mode))){
      const pause=actionButton(I18n.t(account.paused?'Genoptag backup':'Sæt backup på pause'),account.email,account.paused?'resume':'pause');
      pause.disabled=!!account.stopping||!account.online||(account.paused&&(account.running||account.pending));controls.append(pause);
    }
    if(account.email !== 'legacy') {
      const remove=document.createElement('button');remove.type='button';remove.className='outline danger';remove.textContent=I18n.t('Fjern konto');
      remove.addEventListener('click',event=>{event.stopPropagation();openRemoval(account);});controls.append(remove);
    }
    if (account.running || account.pending || account.stopping) {
      const stop=actionButton(account.stopping ? I18n.t('Afbryder…') : I18n.t('Afbryd backup'), account.email, 'stop');
      stop.classList.add('danger'); stop.disabled=account.stopping;
      controls.append(stop);
    }
    if (account.login_active) controls.append(actionButton(I18n.t('Afslut login'), account.email, 'close-login'));
    if(account.removing) controls.querySelectorAll('button').forEach(button=>{button.disabled=true;});
    const feedback = document.createElement('div');
    feedback.className = 'account-feedback';
    feedback.setAttribute('role', 'status');
    feedback.setAttribute('aria-live', 'polite');
    feedback.textContent = phase ? phase.detail : account.stopping ? I18n.t('◷ Afbryder backup – venter på at processerne lukker.') : account.running ? I18n.t('● Backup kører nu – nye filer vises i overblikket.') : account.pending ? account.login_active ? I18n.t('◷ Afslutter login-browseren før backup…') : I18n.t('◷ Start er bestilt – venter på synkroniseringsmotoren.') : account.login_active ? I18n.t('Login-browseren er åben. Start backup lukker den automatisk.') : '';
    const verification=document.createElement('small');verification.className='account-verification';verification.textContent=verificationText(account.verification);
    if(account.storage?.warning)verification.textContent+=' · '+I18n.t('Lav diskplads: ')+human(account.storage.free)+I18n.t(' ledig');
    card.append(detail, controls, feedback, verification);
    list.append(card);
  }
}
el('add-account-form').addEventListener('submit', async event => {
  event.preventDefault();
  const email = el('account-email').value.trim();
  try {
    const result = await postAccount('/api/accounts', {email});
    el('account-message').textContent = I18n.t('Konto tilføjet. Mappe: ') + result.folder;
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

window.addEventListener("languagechange", refresh);

let removalAccount=null, removalStep=1, removalBusy=false;
const removalMode=()=>document.querySelector('input[name=remove-mode]:checked').value;
function removalWarning() {return I18n.t(removalMode()==='keep' ? 'Backupfilerne bevares i kontoens mappe. Loginprofilen og kørselsplanen fjernes.' : 'Alle lokale billeder, videoer og metadata i kontoens backupmappe slettes. Det kan ikke fortrydes.');}
function renderRemoval() {
  el('remove-step-label').textContent=I18n.t('Trin ')+removalStep+I18n.t(' af 3');
  document.querySelectorAll('[data-remove-step]').forEach(section=>{section.hidden=Number(section.dataset.removeStep)!==removalStep;});
  el('remove-back').hidden=removalStep===1;el('remove-next').hidden=removalStep===3;el('remove-submit').hidden=removalStep!==3;
  el('remove-review').textContent=removalWarning();el('remove-final-warning').textContent=removalWarning();
  el('remove-submit').disabled=removalBusy || !el('remove-acknowledge').checked || el('remove-confirm-email').value!==removalAccount.email;
}
function openRemoval(account) {
  removalAccount=account;removalStep=1;removalBusy=false;
  document.querySelector('input[name=remove-mode][value=keep]').checked=true;
  el('remove-account-name').textContent=account.email;el('remove-confirm-email').value='';el('remove-acknowledge').checked=false;el('remove-message').textContent='';
  el('remove-account-dialog').querySelectorAll('button,input').forEach(node=>{node.disabled=false;});
  renderRemoval();el('remove-account-dialog').showModal();
}
el('remove-cancel').addEventListener('click',()=>{if(!removalBusy)el('remove-account-dialog').close();});
el('remove-account-dialog').addEventListener('cancel',event=>{if(removalBusy)event.preventDefault();});
el('remove-next').addEventListener('click',()=>{removalStep=Math.min(3,removalStep+1);renderRemoval();if(removalStep===3)el('remove-confirm-email').focus();});
el('remove-back').addEventListener('click',()=>{removalStep=Math.max(1,removalStep-1);renderRemoval();});
el('remove-confirm-email').addEventListener('input',renderRemoval);el('remove-acknowledge').addEventListener('change',renderRemoval);
window.addEventListener('languagechange',()=>{if(removalAccount && el('remove-account-dialog').open)renderRemoval();});
el('remove-submit').addEventListener('click',async()=>{
  if(removalBusy || el('remove-confirm-email').value!==removalAccount.email || !el('remove-acknowledge').checked)return;
  removalBusy=true;el('remove-account-dialog').querySelectorAll('button,input').forEach(node=>{node.disabled=true;});
  el('remove-message').textContent=I18n.t('Fjerner konto – stopper backup og login…');
  try {
    const result=await postAccount('/api/accounts/'+encodeURIComponent(removalAccount.email)+'/remove',{mode:removalMode(),confirmation:el('remove-confirm-email').value});
    if(selectedAccount===removalAccount.email)selectedAccount=null;
    el('remove-account-dialog').close();el('account-message').textContent=I18n.t(result.kept_data ? 'Kontoen er fjernet. Backupfilerne er bevaret.' : 'Kontoen er fjernet, og dens lokale backupfiler er slettet.');await refresh();
  } catch(error) {el('remove-message').textContent=error.message;}
  finally {removalBusy=false;el('remove-account-dialog').querySelectorAll('button,input').forEach(node=>{node.disabled=false;});renderRemoval();}
});
