'use strict';
let toolsAccount=null;
let toolsCurrentAccount=null;
const toolEl=id=>document.getElementById(id);
const toolText=(node,text)=>{node.textContent=text;return node;};
function verificationText(report){
  if(!report||!report.available)return I18n.t('Ingen backupkontrol endnu. Kør kontrol efter første backup.');
  let text=I18n.t('Seneste kontrol: ')+report.at+' · '+report.checked+I18n.t(' katalogfiler kontrolleret · ')+report.missing+I18n.t(' mangler · ')+report.empty+I18n.t(' tomme');
  if(report.unbacked_items!==null)text+=' · '+report.unbacked_items+I18n.t(' Google-elementer uden lokal fil');
  return text;
}
function updateAccountTools(data){
  showVersions(data);
  const update=data.update||{};
  const box=toolEl('release-notice');
  box.replaceChildren();
  if(update.state==='available'){
    const link=document.createElement('a');link.className='outline';link.href=update.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=I18n.t('Ny version: ')+update.latest;
    box.append(link,document.createTextNode(' · '+I18n.t('Installer via Update Stack.')));box.hidden=false;
  }else if(update.state==='unavailable'){box.textContent=I18n.t('Kunne ikke kontrollere nye versioner. Din installerede version vises nederst.');box.hidden=false;}
  else box.hidden=true;
  if(!toolsAccount||!toolEl('account-tools').open)return;
  const account=toolsAccount==='legacy'?data:(data.accounts||[]).find(a=>a.email===toolsAccount);
  if(!account)return;
  toolsCurrentAccount=account;
  const busy=account.running||account.pending||account.stopping||account.removing;
  toolEl('tools-verify').disabled=!!busy||!account.online;toolEl('tools-repair').disabled=!!busy||!account.online;
  toolEl('tools-verification').textContent=verificationText(account.verification);
  renderLibraryTools(account,busy);
  toolEl('tools-success').textContent=I18n.t('Seneste vellykkede backup: ')+(account.last_success?.finished||I18n.t('Ingen endnu'));
  toolEl('tools-next').textContent=I18n.t('Næste kørsel: ')+(account.settings?.enabled?account.next_run:I18n.t('Automatisk backup er sat på pause'));
  toolEl('tools-email-status').textContent=account.email_notification?(account.email_notification.ok?I18n.t('Seneste mail sendt'):I18n.t('Seneste mail fejlede'))+' · '+account.email_notification.at:'';
  toolEl('tools-failure').textContent=account.failure?I18n.t('Seneste downloadfejl: ')+account.failure.category+' · '+(account.failure.id||'')+(account.failure.retryable?' · '+I18n.t('Midlertidig fejl'):''):'';
  toolEl('tools-notification-status').textContent=account.notification?(account.notification.ok?I18n.t('Seneste notifikation sendt'):I18n.t('Seneste notifikation fejlede'))+' · '+account.notification.at:'';
  const rows=toolEl('tools-history');rows.replaceChildren();
  for(const entry of account.history||[]){
    const row=document.createElement('tr');
    const result=entry.result===0?I18n.t('Afsluttet'):entry.result===131?I18n.t('Pause'):entry.result===132?I18n.t('Lav diskplads'):entry.result===130?I18n.t('Afbrudt'):I18n.t('Fejlet')+' ('+entry.result+')';
    const mode=I18n.t({backup:'Backup',repair:'Reparation',check:'Kontrol',organize:'Organisering',content:'Filindhold',duplicates:'Dubletter',albums:'Albumhistorik'}[entry.mode]||entry.mode);
    const size=(entry.new_bytes/1024**2).toLocaleString(I18n.locale(),{maximumFractionDigits:1})+' MB';
    for(const value of [entry.finished,mode,result,entry.new_files+' / '+size,Math.ceil(entry.duration/60)+' min'])row.append(toolText(document.createElement('td'),value));
    rows.append(row);
  }
  if(!rows.childElementCount){const row=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=5;cell.textContent=I18n.t('Historikken starter fra denne opdatering.');row.append(cell);rows.append(row);}
}
function openAccountTools(account){
  toolsAccount=account.email;
  toolEl('tools-name').textContent=account.email==='legacy'?I18n.t('Eksisterende konto'):account.email;
  const config=account.settings||{enabled:true,hour:3,days:[0,1,2,3,4,5,6],notify_url:'',notify_success:false};
  toolEl('schedule-enabled').checked=config.enabled;toolEl('schedule-hour').value=config.hour;
  document.querySelectorAll('[data-weekday]').forEach(node=>{node.checked=config.days.includes(Number(node.dataset.weekday));});
  toolEl('email-enabled').checked=!!config.email_enabled;toolEl('email-mode').value=config.email_mode||'all';toolEl('retry-count').value=config.retry_count??2;toolEl('index-hours').value=config.index_hours??24;
  toolEl('notify-url').value=config.notify_url;toolEl('notify-success').checked=config.notify_success;
  toolEl('reserve-gb').value=config.min_free_gb??2;toolEl('reserve-percent').value=config.min_free_percent??2;
  toolEl('album-confirm').value='';toolsCurrentAccount=account;
  toolEl('tools-message').textContent='';toolEl('account-tools').showModal();refresh();
}
toolEl('tools-close').addEventListener('click',()=>toolEl('account-tools').close());
toolEl('tools-settings-form').addEventListener('submit',async event=>{
  event.preventDefault();const button=toolEl('tools-save');button.disabled=true;
  try{
    const settings={email_enabled:toolEl('email-enabled').checked,email_mode:toolEl('email-mode').value,retry_count:Number(toolEl('retry-count').value),index_hours:Number(toolEl('index-hours').value),enabled:toolEl('schedule-enabled').checked,hour:Number(toolEl('schedule-hour').value),days:[...document.querySelectorAll('[data-weekday]:checked')].map(n=>Number(n.dataset.weekday)),notify_url:toolEl('notify-url').value.trim(),notify_success:toolEl('notify-success').checked,min_free_gb:Number(toolEl('reserve-gb').value),min_free_percent:Number(toolEl('reserve-percent').value)};
    await postAccount('/api/accounts/'+encodeURIComponent(toolsAccount)+'/settings',{settings});
    toolEl('tools-message').textContent=I18n.t('Indstillinger gemt. Tidsplanen opdateres inden for 10 sekunder.');await refresh();
  }catch(error){toolEl('tools-message').textContent=error.message;}
  finally{button.disabled=false;}
});
for(const [id,action]of [['tools-verify','verify'],['tools-repair','repair'],['tools-content','content'],['tools-duplicates','duplicates']])toolEl(id).addEventListener('click',async event=>{
  if(action==='repair'&&!window.confirm(I18n.t('Gennemgå Google-arkivet igen og hent manglende filer? Eksisterende filer bevares. Tomme filer gemmes i karantæne.')))return;
  event.target.disabled=true;
  try{await postAccount('/api/accounts/'+encodeURIComponent(toolsAccount)+'/'+action,{});toolEl('tools-message').textContent=I18n.t('Anmodning sendt. Følg status på kontoen.');await refresh();}
  catch(error){toolEl('tools-message').textContent=error.message;event.target.disabled=false;}
});

function toolsTable(id,rows){
  const body=toolEl(id);body.replaceChildren();
  for(const values of rows){const row=document.createElement('tr');for(const value of values)row.append(toolText(document.createElement('td'),String(value)));body.append(row);}
}
function renderLibraryTools(account,busy){
  const space=account.storage;
  toolEl('tools-space').textContent=space?(space.free/1024**3).toFixed(1)+' GB'+I18n.t(' ledig · reserve ')+(space.reserve/1024**3).toFixed(1)+' GB'+(space.warning?' · '+I18n.t('Lav diskplads'):''):I18n.t('Afventer måling');
  const coverage=account.coverage;
  toolEl('tools-coverage').textContent=coverage?.available?coverage.local+' / '+coverage.indexed+I18n.t(' Google-elementer med lokale filer · ')+coverage.missing+I18n.t(' mangler')+' · '+(coverage.indexed_at||coverage.at):I18n.t('Kør backup eller kontrol for at opdatere overblikket.');
  toolsTable('coverage-years',(coverage?.years||[]).map(r=>[r.year,r.indexed,r.local,r.missing]));
  toolsTable('coverage-albums',(coverage?.albums||[]).map(r=>[r.title,r.indexed,r.local,r.missing]));
  const content=account.content;
  toolEl('content-summary').textContent=content?I18n.t(content.deep?'Indholdskontrol':'Checksumkontrol')+' · '+content.checked+' / '+content.total+' · '+content.changed+I18n.t(' ændrede checksums · ')+content.decode_errors+I18n.t(' afkodningsfejl · ')+content.unverified+I18n.t(' ikke verificeret')+' · '+content.at+(content.interrupted?' · '+I18n.t('Afbrudt'):''):I18n.t('Ingen indholdskontrol endnu');
  toolsTable('content-issues',(content?.issues||[]).map(r=>[r.name,r.checksum_changed?I18n.t('Checksum ændret'):'',I18n.t({'decoded':'Afkodet','unsupported':'Format understøttes ikke','unverified':'Ikke verificeret','decode-error':'Afkodningsfejl','not-requested':'Kun checksum'}[r.decode]||r.decode)]));
  const duplicates=account.duplicates;
  toolEl('duplicates-summary').textContent=duplicates?duplicates.group_count+I18n.t(' dubletgrupper · ')+duplicates.extra_files+I18n.t(' ekstra filer · ')+(duplicates.extra_bytes/1024**3).toFixed(2)+' GB · '+duplicates.at:I18n.t('Ingen dubletkontrol endnu');
  toolsTable('duplicate-groups',(duplicates?.groups||[]).map(r=>[r.count,r.files.join('\n')]));
  const review=account.album_review;
  toolEl('album-review-summary').textContent=review?.available?review.changes.length+I18n.t(' ændrede albums · ')+review.obsolete+I18n.t(' gamle lokale albumreferencer'):I18n.t('Albumgennemgang opdateres ved backup.');
  toolsTable('album-changes',(review?.changes||[]).map(r=>[r.before||'–',r.after||'–','+'+r.added+' / −'+r.removed]));
  for(const id of ['tools-content','tools-duplicates'])toolEl(id).disabled=!!busy||!account.online;
  toolEl('album-approve').disabled=!!busy||!account.online||!review?.available||!(review.changes.length||review.obsolete)||toolEl('album-confirm').value!==toolsAccount;
}
toolEl('album-confirm').addEventListener('input',()=>{if(toolsCurrentAccount)renderLibraryTools(toolsCurrentAccount,toolsCurrentAccount.running||toolsCurrentAccount.pending||toolsCurrentAccount.stopping);});
toolEl('album-approve').addEventListener('click',async()=>{
  toolEl('album-approve').disabled=true;
  try{await postAccount('/api/accounts/'+encodeURIComponent(toolsAccount)+'/approve-albums',{confirmation:toolEl('album-confirm').value,revision:toolsCurrentAccount.album_review.revision});toolEl('tools-message').textContent=I18n.t('Albumopdatering bestilt. Hovedfiler og historikkopier bevares.');await refresh();}
  catch(error){toolEl('tools-message').textContent=error.message;}
});

let importedSettings=null;
toolEl('config-export').addEventListener('click',async()=>{
  try{const response=await fetch('/api/config/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})});if(!response.ok)throw Error(await response.text());
    const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download='photoharbor-settings.json';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(error){toolEl('account-message').textContent=error.message;}
});
toolEl('config-import').addEventListener('click',()=>{importedSettings=null;toolEl('config-file').value='';toolEl('config-preview').textContent='';toolEl('config-ack').checked=false;toolEl('config-restore').disabled=true;toolEl('config-dialog').showModal();});
toolEl('config-close').addEventListener('click',()=>toolEl('config-dialog').close());
toolEl('config-file').addEventListener('change',async()=>{
  importedSettings=null;toolEl('config-restore').disabled=true;toolEl('config-ack').checked=false;
  try{const file=toolEl('config-file').files[0];if(!file||file.size>262144)throw Error(I18n.t('Vælg en indstillingsfil under 256 KB.'));
    const document=JSON.parse(await file.text());const result=await postAccount('/api/config/preview',{document});importedSettings=document;
    toolEl('config-preview').textContent=result.accounts.map(a=>a.email+' · '+I18n.t(a.new?'Ny konto':'Opdater eksisterende konto')).join('\n');
  }catch(error){toolEl('config-preview').textContent=error.message;}
});
toolEl('config-ack').addEventListener('change',()=>{toolEl('config-restore').disabled=!importedSettings||!toolEl('config-ack').checked;});
toolEl('config-restore').addEventListener('click',async()=>{
  toolEl('config-restore').disabled=true;
  try{await postAccount('/api/config/restore',{document:importedSettings,confirmation:'IMPORT'});toolEl('config-dialog').close();toolEl('account-message').textContent=I18n.t('Indstillinger gendannet. Nye konti skal logge ind på Google.');await refresh();}
  catch(error){toolEl('config-preview').textContent=error.message;toolEl('config-restore').disabled=false;}
});
