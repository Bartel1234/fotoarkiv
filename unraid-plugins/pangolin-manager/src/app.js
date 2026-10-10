(() => {
  'use strict';
  if (window.PangolinManager) return;
  const base = '/plugins/pangolin-manager/api.php';
  const q = (s, root = document) => root.querySelector(s);
  const qa = (s, root = document) => [...root.querySelectorAll(s)];
  const el = (tag, text = '', cls = '') => {const e = document.createElement(tag);e.textContent = text;if(cls)e.className=cls;return e;};
  let busy = false, lastStatus = null, settings = null, settingsLoaded = false;
  async function api(action, payload, extra = {}) {
    const options = {credentials: 'same-origin', cache: 'no-store'};
    let url = base + '?action=' + encodeURIComponent(action);
    if (payload !== undefined) {
      const token = typeof window.csrf_token === 'string' ? window.csrf_token : '';
      if (!token) throw new Error('Sessionen kunne ikke læses. Genindlæs Unraid-siden.');
      options.method = 'POST';
      // Unraid validates and removes csrf_token in local_prepend.php. Preserve
      // a separately named copy for the plugin's own fail-closed validation.
      options.body = new URLSearchParams({action, csrf_token: token, pm_csrf_token: token, payload: JSON.stringify(payload), ...extra});
      url = base;
    }
    const controller = new AbortController();options.signal=controller.signal;
    const timer = setTimeout(() => controller.abort(), 25000);
    try {
      const response = await fetch(url, options);
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'Unraid svarede med en fejl.');
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('Kontrollen tog for lang tid. Prøv igen, eller kontrollér pluginets baggrundskontrol.');
      if (error instanceof SyntaxError) throw new Error('Unraid returnerede ikke statusdata. Kontrollér at du stadig er logget ind.');
      throw error;
    } finally {clearTimeout(timer);}
  }
  function message(text, error = false) {
    [q('#pm-message'), q('[data-pm-widget-message]')].filter(Boolean).forEach(e => {
      e.textContent = text;e.className = 'pm-message' + (error ? ' pm-error' : '');
      e.hidden = !text;
    });
  }
  function badge(e, data) {
    e.textContent = data?.label || 'Ukendt';e.dataset.state = data?.state || 'unknown';
    e.title = data?.detail || '';
  }
  function serviceSummary(services = []) {
    if (!services.length) return 'Ingen tilføjet';
    const up = services.filter(s => s.state === 'up').length;
    const down = services.filter(s => s.state === 'down').length;
    const unknown = services.filter(s => s.state === 'unknown').length;
    return `${up}/${services.length} svarer` + (down ? ` · ${down} fejl` : '') + (unknown ? ` · ${unknown} ukendt` : '');
  }
  function safeLink(e, url) {
    try {const u = new URL(url);if(!['http:', 'https:'].includes(u.protocol))throw new Error();e.href=u.href;e.hidden=false;}
    catch (_) {e.removeAttribute('href');e.hidden=true;}
  }
  function render(s) {
    lastStatus = s;
    ['container', 'tunnel', 'endpoint'].forEach(k => {
      qa(`[data-pm-${k}]`).forEach(e => badge(e, s[k]));
      qa(`[data-pm-${k}-detail]`).forEach(e => e.textContent = s[k]?.detail || 'Ingen måling endnu.');
    });
    qa('[data-pm-summary]').forEach(e => e.textContent = s.summary || 'Ingen status endnu.');
    qa('[data-pm-services-summary]').forEach(e => e.textContent = serviceSummary(s.services));
    qa('[data-pm-time]').forEach(e => {
      if (!s.checked_at) {e.textContent = 'Ingen måling endnu';return;}
      const date = new Date(s.checked_at * 1000);
      e.textContent = `${s.stale ? 'Forældet · ' : ''}Kontrolleret ${date.toLocaleTimeString('da-DK', {hour:'2-digit', minute:'2-digit', second:'2-digit'})}`;
    });
    qa('[data-pm-open]').forEach(e => safeLink(e, s.endpoint_url || ''));
    const r = q('[data-pm-restarts]');if(r)r.textContent = s.container?.restarts !== undefined ? `${s.container.restarts} Docker-genstarter registreret` : '';
    const table = q('[data-pm-services]');
    if (table) {
      table.replaceChildren();
      if (!s.services?.length) {const row=el('tr');const cell=el('td','Tilføj tjenester under Indstillinger.','pm-muted');cell.colSpan=5;row.append(cell);table.append(row);}
      (s.services || []).forEach(svc => {
        const row = el('tr');row.append(el('td', svc.name), el('td', svc.url, 'pm-url'));
        const state = el('td');const b=el('span','','pm-badge');badge(b,svc);state.append(b);row.append(state);
        row.append(el('td', svc.ms !== undefined ? `${svc.ms} ms` : '—'));
        const linkCell = el('td');if(svc.public_url){const link=el('a','Åbn ↗');link.target='_blank';link.rel='noopener noreferrer';safeLink(link,svc.public_url);linkCell.append(link);}row.append(linkCell);table.append(row);
      });
    }
    const restart=q('#pm-restart');if(restart)restart.disabled=!s.configured;
  }
  async function poll() {
    if (busy || document.hidden) return;
    try {render((await api('status')).status);} catch (e) {
      if (lastStatus) {
        const unknown = {state:'unknown',label:'Kan ikke opdateres',detail:e.message};
        render({...lastStatus,stale:true,container:unknown,tunnel:unknown,endpoint:unknown,
          services:(lastStatus.services||[]).map(s=>({...s,...unknown})),summary:'Status kunne ikke opdateres. Kontrollér sessionen og forbindelsen til Unraid.'});
      }
      message(e.message,true);
    }
  }
  async function test() {
    if (busy) return;
    busy = true;qa('[data-pm-test]').forEach(e=>{e.disabled=true;e.textContent='Kontrollerer…';});message('Kontrollerer forbindelsen…');
    try {render((await api('test', {})).status);message('Kontrollen er færdig.');}
    catch(e){message(e.message,true);}
    finally {busy=false;qa('[data-pm-test]').forEach(e=>{e.disabled=false;e.textContent=q('#pm-panel')?'Test forbindelse':'Test';});}
  }
  function tab(name) {
    qa('[data-tab]').forEach(e=>e.classList.toggle('active',e.dataset.tab===name));
    qa('[data-view]').forEach(e=>e.hidden=e.dataset.view!==name);
    if(name==='settings' && !settingsLoaded)loadSettings();
    if(name==='logs')loadLogs();
  }
  function inputLabel(title,name,value,placeholder='',type='text') {
    const label=el('label',title);const input=el('input');input.name=name;input.type=type;input.value=value || '';input.placeholder=placeholder;label.append(input);return label;
  }
  function addService(s = {}) {
    const editor=q('#pm-service-editor');
    if(editor.children.length>=12){message('Der kan højst tilføjes 12 tjenester.',true);return;}
    const row=el('div','','pm-service-edit');
    row.append(inputLabel('Navn','name',s.name,'PhotoHarbor'),inputLabel('Lokal URL','url',s.url,'http://192.168.1.10:8787','url'),inputLabel('Offentligt link (valgfrit)','public_url',s.public_url,'https://fotos.dit-domæne.dk','url'));
    const label=el('label','Kontroltype');const select=el('select');select.name='mode';
    [['http','HTTP-sundhed (2xx/3xx)'],['reachable','Server svarer (alle HTTP-svar)']].forEach(([v,t])=>{const o=el('option',t);o.value=v;select.append(o);});
    select.value=s.mode||'http';label.append(select);row.append(label);
    const remove=el('button','Fjern','pm-btn');remove.type='button';remove.addEventListener('click',()=>row.remove());row.append(remove);editor.append(row);
  }
  async function loadSettings() {
    const form=q('#pm-settings');if(!form)return;
    try {
      const [config, containers] = await Promise.allSettled([api('settings'),api('containers')]);
      if(config.status!=='fulfilled')throw config.reason;
      settings=config.value.settings;
      const select=form.elements.container;select.replaceChildren();const empty=el('option','Vælg container…');empty.value='';select.append(empty);
      const list=containers.status==='fulfilled'?containers.value.containers:[];
      if(settings.container && !list.some(c=>c.name===settings.container))list.push({name:settings.container,image:'ikke fundet',suggested:false});
      list.forEach(c=>{const option=el('option',`${c.name}${c.suggested?' · Newt':''} (${c.image})`);option.value=c.name;select.append(option);});
      ['container','endpoint','health_file','api_url','org_id','site_id'].forEach(k=>form.elements[k].value=settings[k]||'');
      form.elements.notifications.checked=settings.notifications;
      form.elements.api_key.value='';form.elements.clear_api_key.checked=false;
      q('#pm-api-key-state').textContent=settings.has_api_key?'API-nøgle er gemt. Den vises ikke her.':'Ingen API-nøgle gemt.';
      q('#pm-service-editor').replaceChildren();settings.services.forEach(addService);settingsLoaded=true;
      if(containers.status!=='fulfilled')message(containers.reason.message,true);
    }catch(e){message(e.message,true);}
  }
  async function save(event) {
    event.preventDefault();const form=event.currentTarget;
    if(!settingsLoaded){message('Indstillingerne er ikke indlæst. Genindlæs siden, før du gemmer.',true);return;}
    const values={};['container','endpoint','health_file','api_url','api_key','org_id','site_id'].forEach(k=>values[k]=form.elements[k].value.trim());
    values.notifications=form.elements.notifications.checked;values.clear_api_key=form.elements.clear_api_key.checked;
    values.services=qa('.pm-service-edit').map(row=>{const s={};['name','url','public_url','mode'].forEach(k=>s[k]=q(`[name="${k}"]`,row).value.trim());return s;});
    const button=q('button[type="submit"]',form);button.disabled=true;
    try {const data=await api('save',values);settings=data.settings;form.elements.api_key.value='';form.elements.clear_api_key.checked=false;
      q('#pm-api-key-state').textContent=settings.has_api_key?'API-nøgle er gemt. Den vises ikke her.':'Ingen API-nøgle gemt.';
      message('Indstillinger gemt.');tab('overview');await test();}
    catch(e){message(e.message,true);}finally{button.disabled=false;}
  }
  async function loadLogs() {
    const button=q('#pm-load-logs');if(!button)return;button.disabled=true;
    try {q('#pm-log').textContent=(await api('logs',{})).logs||'Ingen loglinjer i det seneste døgn.';}
    catch(e){message(e.message,true);}finally{button.disabled=false;}
  }
  async function restart() {
    const button=q('#pm-confirm-restart');button.disabled=true;
    try {message('Genstarter Newt…');const r=await api('restart',{}, {confirm:'restart-newt'});q('#pm-restart-dialog').close();message(r.message);await poll();}
    catch(e){message(e.message,true);}finally{button.disabled=false;}
  }
  function init() {
    qa('[data-pm-test]').forEach(e=>e.addEventListener('click',test));
    qa('[data-tab]').forEach(e=>e.addEventListener('click',()=>tab(e.dataset.tab)));
    q('#pm-settings')?.addEventListener('submit',save);
    q('#pm-add-service')?.addEventListener('click',()=>addService());
    q('#pm-load-logs')?.addEventListener('click',loadLogs);
    q('#pm-restart')?.addEventListener('click',()=>q('#pm-restart-dialog').showModal());
    q('#pm-cancel-restart')?.addEventListener('click',()=>q('#pm-restart-dialog').close());
    q('#pm-confirm-restart')?.addEventListener('click',restart);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});
    poll();setInterval(poll,30000);
  }
  window.PangolinManager = {init};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
