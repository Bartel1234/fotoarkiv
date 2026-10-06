'use strict';
const upgradeEl=id=>document.getElementById(id);
let releaseData={};
function renderJobDetails(account){
 const data=account.live||{};let text='';
 if(account.running&&account.phase==='downloading')text=(data.completed_files||0)+I18n.t(' hentede filer · ')+human(data.completed_bytes||0)+' · '+human(data.average_bytes_per_second||0)+'/s · '+I18n.t('Seneste aktivitet: ')+Math.floor((data.activity_age||0)/60)+' min';
 if(account.running&&data.stalled&&account.phase==='downloading')text+=' · '+I18n.t('Ingen registreret fremgang i 15 minutter. Se loggen før du afbryder.');
 if(account.running&&account.phase==='retrying')text=I18n.t('Midlertidig fejl. Nyt forsøg starter efter ventetiden.');
 return text;
}
upgradeEl('email-open').addEventListener('click',async()=>{
 try{const response=await fetch('/api/email',{cache:'no-store'});if(!response.ok)throw Error(await response.text());const data=await response.json();
  for(const key of ['host','port','security','username','sender','recipient','language'])upgradeEl('smtp-'+key).value=data[key]??({port:587,security:'starttls',language:'en'}[key]||'');
  upgradeEl('smtp-enabled').checked=!!data.enabled;upgradeEl('smtp-password').value='';upgradeEl('smtp-clear').checked=false;
  upgradeEl('smtp-password').placeholder=I18n.t(data.password_saved?'Adgangskode gemt — lad feltet stå tomt for at beholde den':'SMTP-adgangskode');upgradeEl('smtp-message').textContent='';upgradeEl('email-dialog').showModal();
 }catch(error){upgradeEl('account-message').textContent=error.message;}
});
upgradeEl('smtp-close').addEventListener('click',()=>upgradeEl('email-dialog').close());
upgradeEl('smtp-form').addEventListener('submit',async event=>{
 event.preventDefault();upgradeEl('smtp-save').disabled=true;
 try{const settings={enabled:upgradeEl('smtp-enabled').checked,port:Number(upgradeEl('smtp-port').value),password:upgradeEl('smtp-password').value,clear_password:upgradeEl('smtp-clear').checked};
  for(const key of ['host','security','username','sender','recipient','language'])settings[key]=upgradeEl('smtp-'+key).value;
  await postAccount('/api/email/save',{settings});upgradeEl('smtp-password').value='';upgradeEl('smtp-message').textContent=I18n.t('Mailindstillinger gemt. Aktiver mail på de ønskede konti.');
 }catch(error){upgradeEl('smtp-message').textContent=error.message;}finally{upgradeEl('smtp-save').disabled=false;}
});
upgradeEl('smtp-test').addEventListener('click',async()=>{
 upgradeEl('smtp-test').disabled=true;upgradeEl('smtp-message').textContent=I18n.t('Sender testmail med gemte indstillinger…');
 try{await postAccount('/api/email/test',{});upgradeEl('smtp-message').textContent=I18n.t('Testmail sendt.');}catch(error){upgradeEl('smtp-message').textContent=error.message;}finally{upgradeEl('smtp-test').disabled=false;}
});
upgradeEl('tools-diagnostics').addEventListener('click',async()=>{
 try{const response=await fetch('/api/diagnostics/'+encodeURIComponent(toolsAccount),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})});if(!response.ok)throw Error(await response.text());
  const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download='photoharbor-diagnostics.json';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }catch(error){upgradeEl('tools-message').textContent=error.message;}
});
function showVersions(data){
 releaseData=data.update||{};upgradeEl('installed-version').textContent=releaseData.installed||'';
 const channel=upgradeEl('version-channel').value;const info=releaseData.channels?.[channel];
 upgradeEl('channel-version').textContent=info?.version||I18n.t('Version kunne ikke hentes');
 upgradeEl('channel-notes').textContent=info?.notes||'';
 const link=upgradeEl('channel-link');link.hidden=!info; if(info){link.href=info.url;link.textContent=I18n.t('Se udgivelsen på GitHub');}
 upgradeEl('channel-image').textContent=channel==='beta'?'ghcr.io/bartel1234/fotoarkiv:beta':'';
}
upgradeEl('version-channel').value=document.querySelector('.app-version').textContent.includes('beta')?'beta':'stable';
upgradeEl('version-channel').addEventListener('change',()=>showVersions({update:releaseData}));
upgradeEl('versions-open').addEventListener('click',()=>{upgradeEl('versions-dialog').showModal();refresh();});
upgradeEl('versions-close').addEventListener('click',()=>upgradeEl('versions-dialog').close());
