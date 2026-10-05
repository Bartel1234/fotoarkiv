'use strict';
let toolsAccount=null;
const toolEl=id=>document.getElementById(id);
const toolText=(node,text)=>{node.textContent=text;return node;};
function verificationText(report){
  if(!report||!report.available)return I18n.t('Ingen backupkontrol endnu. Kør kontrol efter første backup.');
  let text=I18n.t('Seneste kontrol: ')+report.at+' · '+report.checked+I18n.t(' katalogfiler kontrolleret · ')+report.missing+I18n.t(' mangler · ')+report.empty+I18n.t(' tomme');
  if(report.unbacked_items!==null)text+=' · '+report.unbacked_items+I18n.t(' Google-elementer uden lokal fil');
  return text;
}
function updateAccountTools(data){
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
  const busy=account.running||account.pending||account.stopping||account.removing;
  toolEl('tools-verify').disabled=!!busy||!account.online;toolEl('tools-repair').disabled=!!busy||!account.online;
  toolEl('tools-verification').textContent=verificationText(account.verification);
  toolEl('tools-success').textContent=I18n.t('Seneste vellykkede backup: ')+(account.last_success?.finished||I18n.t('Ingen endnu'));
  toolEl('tools-next').textContent=I18n.t('Næste kørsel: ')+(account.settings?.enabled?account.next_run:I18n.t('Automatisk backup er sat på pause'));
  toolEl('tools-notification-status').textContent=account.notification?(account.notification.ok?I18n.t('Seneste notifikation sendt'):I18n.t('Seneste notifikation fejlede'))+' · '+account.notification.at:'';
  const rows=toolEl('tools-history');rows.replaceChildren();
  for(const entry of account.history||[]){
    const row=document.createElement('tr');
    const result=entry.result===0?I18n.t('Afsluttet'):entry.result===130?I18n.t('Afbrudt'):I18n.t('Fejlet')+' ('+entry.result+')';
    const mode=I18n.t({backup:'Backup',repair:'Reparation',check:'Kontrol',organize:'Organisering'}[entry.mode]||entry.mode);
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
  toolEl('notify-url').value=config.notify_url;toolEl('notify-success').checked=config.notify_success;
  toolEl('tools-message').textContent='';toolEl('account-tools').showModal();refresh();
}
toolEl('tools-close').addEventListener('click',()=>toolEl('account-tools').close());
toolEl('tools-settings-form').addEventListener('submit',async event=>{
  event.preventDefault();const button=toolEl('tools-save');button.disabled=true;
  try{
    const settings={enabled:toolEl('schedule-enabled').checked,hour:Number(toolEl('schedule-hour').value),days:[...document.querySelectorAll('[data-weekday]:checked')].map(n=>Number(n.dataset.weekday)),notify_url:toolEl('notify-url').value.trim(),notify_success:toolEl('notify-success').checked};
    await postAccount('/api/accounts/'+encodeURIComponent(toolsAccount)+'/settings',{settings});
    toolEl('tools-message').textContent=I18n.t('Indstillinger gemt. Tidsplanen opdateres inden for 10 sekunder.');await refresh();
  }catch(error){toolEl('tools-message').textContent=error.message;}
  finally{button.disabled=false;}
});
for(const [id,action]of [['tools-verify','verify'],['tools-repair','repair']])toolEl(id).addEventListener('click',async event=>{
  if(action==='repair'&&!window.confirm(I18n.t('Gennemgå Google-arkivet igen og hent manglende filer? Eksisterende filer bevares. Tomme filer gemmes i karantæne.')))return;
  event.target.disabled=true;
  try{await postAccount('/api/accounts/'+encodeURIComponent(toolsAccount)+'/'+action,{});toolEl('tools-message').textContent=I18n.t('Anmodning sendt. Følg status på kontoen.');await refresh();}
  catch(error){toolEl('tools-message').textContent=error.message;event.target.disabled=false;}
});
