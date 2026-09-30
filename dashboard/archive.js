const archiveEl = id => document.getElementById(id);
const archiveState = {account: '', page: 1, total: 0, selected: new Map(), items: []};
const archiveFormat = n => new Intl.NumberFormat('da-DK').format(n);
const archiveSize = n => n >= 1024 ** 3 ? (n / 1024 ** 3).toLocaleString('da-DK', {maximumFractionDigits: 1}) + ' GB' : (n / 1024 ** 2).toLocaleString('da-DK', {maximumFractionDigits: 1}) + ' MB';
const archiveKey = item => item.id + '/' + item.name;

function archiveSelection() {
  const list = [...archiveState.selected.values()];
  const bytes = list.reduce((sum, item) => sum + item.size, 0);
  archiveEl('archive-selection').textContent = list.length + ' valgt · ' + archiveSize(bytes);
  archiveEl('archive-zip').disabled = !list.length || list.length > 500 || bytes > 10 * 1024 ** 3;
  archiveEl('archive-message').textContent = list.length > 500 || bytes > 10 * 1024 ** 3 ? 'Vælg højst 500 filer og 10 GB ad gangen.' : '';
}

function archivePreview(item) {
  const dialog = archiveEl('archive-preview');
  const container = archiveEl('archive-media');
  container.replaceChildren();
  const media = document.createElement(item.kind === 'video' ? 'video' : 'img');
  media.src = item.url;
  if (item.kind === 'video') { media.controls = true; media.preload = 'metadata'; }
  media.alt = item.name;
  container.append(media);
  archiveEl('archive-caption').textContent = item.name + ' · ' + archiveSize(item.size);
  archiveEl('archive-download').href = item.url + '?download=1';
  archiveEl('archive-download').download = item.name;
  dialog.showModal();
}

function archiveRender() {
  const grid = archiveEl('archive-grid');
  grid.replaceChildren();
  if (!archiveState.items.length) {
    grid.textContent = 'Ingen filer på denne side.';
  }
  for (const item of archiveState.items) {
    const card = document.createElement('div'); card.className = 'archive-card';
    const preview = document.createElement('button'); preview.type = 'button'; preview.className = 'archive-tile';
    if (item.thumb) {
      const img = document.createElement('img'); img.src = item.thumb; img.loading = 'lazy'; img.alt = '';
      preview.append(img);
    } else {
      const icon = document.createElement('span'); icon.textContent = '▶ Video'; preview.append(icon);
    }
    preview.addEventListener('click', () => archivePreview(item));
    const name = document.createElement('strong'); name.textContent = item.name; name.title = item.name;
    const meta = document.createElement('small'); meta.textContent = archiveSize(item.size) + ' · ' + (item.date_source === 'google' ? 'Google-dato ' : 'hentet ') + item.modified;
    const label = document.createElement('label'); label.className = 'archive-check';
    const check = document.createElement('input'); check.type = 'checkbox'; check.checked = archiveState.selected.has(archiveKey(item));
    check.addEventListener('change', () => {
      if (check.checked) archiveState.selected.set(archiveKey(item), item);
      else archiveState.selected.delete(archiveKey(item));
      archiveSelection();
    });
    label.append(check, document.createTextNode(' Vælg'));
    card.append(preview, name, meta, label); grid.append(card);
  }
  archiveEl('archive-total').textContent = archiveFormat(archiveState.total) + ' filer';
  archiveEl('archive-page').textContent = 'Side ' + archiveState.page + ' af ' + Math.max(1, Math.ceil(archiveState.total / 48));
  archiveEl('archive-prev').disabled = archiveState.page <= 1;
  archiveEl('archive-next').disabled = archiveState.page * 48 >= archiveState.total;
  archiveSelection();
}

async function archiveLoad() {
  if (!archiveState.account) return;
  archiveEl('archive-grid').textContent = 'Indlæser filer…';
  try {
    const params = new URLSearchParams({account: archiveState.account, page: archiveState.page,
      q: archiveEl('archive-search').value.trim(), album: archiveEl('archive-album').value});
    const response = await fetch('/api/archive?' + params, {cache: 'no-store'});
    if (!response.ok) throw new Error(await response.text());
    const data = await response.json();
    const albumSelect=archiveEl('archive-album');
    const chosen=albumSelect.value;
    albumSelect.replaceChildren(new Option('Alle billeder og videoer',''), new Option('Uden album','__none__'));
    for(const album of data.albums || []) albumSelect.append(new Option(album.title+' ('+album.count+')',album.id));
    albumSelect.value=chosen;
    const org=data.organization;
    archiveEl('organization-status').textContent=org ? 'Senest organiseret: '+org.updated+(org.missing_metadata ? ' · '+org.missing_metadata+' filer uden Google-metadata' : '')+(org.copies ? ' · '+org.copies+' albumkopier (hardlink ikke muligt)' : '') : 'Filerne er endnu ikke organiseret.';
    archiveState.items = data.items;
    archiveState.total = data.total;
    archiveRender();
  } catch (error) {
    archiveEl('archive-grid').textContent = 'Kunne ikke hente filer.';
    archiveEl('archive-message').textContent = error.message;
  }
}

function archiveInit() {
  archiveState.account = document.body.dataset.account;
  archiveLoad();
}

archiveEl('archive-account').addEventListener('change', event => {
  archiveState.account = event.target.value; archiveState.page = 1; archiveState.selected.clear(); archiveLoad();
});
archiveEl('archive-find').addEventListener('click', () => { archiveState.page = 1; archiveState.selected.clear(); archiveLoad(); });
archiveEl('archive-search').addEventListener('keydown', event => {
  if (event.key === 'Enter') { event.preventDefault(); archiveState.page = 1; archiveState.selected.clear(); archiveLoad(); }
});
archiveEl('archive-prev').addEventListener('click', () => { archiveState.page--; archiveLoad(); });
archiveEl('archive-next').addEventListener('click', () => { archiveState.page++; archiveLoad(); });
archiveEl('archive-close').addEventListener('click', () => archiveEl('archive-preview').close());
archiveEl('archive-preview').addEventListener('close', () => archiveEl('archive-media').replaceChildren());
archiveEl('archive-zip').addEventListener('click', () => {
  const selected = [...archiveState.selected.values()];
  const form = document.createElement('form'); form.method = 'post'; form.action = '/api/archive/zip';
  form.target = 'archive-download-frame'; form.hidden = true;
  const fields = {
    token: archiveEl('archive-token').value,
    account: archiveState.account,
    files: JSON.stringify(selected.map(item => ({id: item.id, name: item.name})))
  };
  for (const [key, value] of Object.entries(fields)) {
    const input = document.createElement('input'); input.type = 'hidden'; input.name = key; input.value = value; form.append(input);
  }
  document.body.append(form); form.submit(); form.remove();
  archiveEl('archive-message').textContent = 'ZIP-download er startet. Filerne pakkes, mens de sendes til browseren.';
});
archiveInit();

archiveEl('archive-album').addEventListener('change',()=>{archiveState.page=1;archiveState.selected.clear();archiveLoad();});
archiveEl('archive-organize').addEventListener('click',async()=>{
  const button=archiveEl('archive-organize');button.disabled=true;
  try {
    const response=await fetch('/api/accounts/'+encodeURIComponent(archiveState.account)+'/organize',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({token:archiveEl('archive-token').value})});
    if(!response.ok) throw Error(await response.text());
    archiveEl('organization-status').textContent='Organisering bestilt. Følg fremdriften i kontoens aktivitetslog.';
  } catch(e) {archiveEl('organization-status').textContent=e.message;}
  finally {button.disabled=false;}
});

async function archiveRunStatus() {
  try {
    const response=await fetch('/api/status',{cache:'no-store'});
    if(!response.ok) return;
    const data=await response.json();
    const account=archiveState.account==='legacy' ? data : (data.accounts||[]).find(a=>a.email===archiveState.account);
    if(!account) return;
    const busy=account.running||account.pending||account.stopping;
    archiveEl('archive-stop').hidden=!busy;
    archiveEl('archive-stop').disabled=!!account.stopping;
    archiveEl('archive-stop').textContent=account.stopping?'Afbryder…':'Afbryd backup';
    archiveEl('archive-organize').disabled=!!busy||!account.online;
    if(busy) archiveEl('organization-status').textContent=account.stopping?'Afbryder backup…':account.running?'Kontoens backup eller organisering kører.':'Kontoens kørsel afventer start.';
  } catch (_) {}
}
archiveEl('archive-stop').addEventListener('click',async()=>{
  const button=archiveEl('archive-stop');button.disabled=true;
  try {
    const response=await fetch('/api/accounts/'+encodeURIComponent(archiveState.account)+'/stop',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({token:archiveEl('archive-token').value})});
    if(!response.ok) throw Error(await response.text());
    archiveEl('organization-status').textContent='Afbryder backup…';
    await archiveRunStatus();
  } catch(e) {archiveEl('organization-status').textContent=e.message;button.disabled=false;}
});
archiveRunStatus();
setInterval(archiveRunStatus,8000);
