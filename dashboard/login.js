'use strict';
const screen=document.getElementById('screen'), status=document.getElementById('status');
const account=document.body.dataset.account, token=document.getElementById('token').value;
const da=document.cookie.split(';').some(c=>c.trim()==='fotoarkiv_language=da');
const t=(en,dansk)=>da?dansk:en;
document.documentElement.lang=da?'da':'en';
document.getElementById('done').textContent=t('Finish sign-in','Afslut login');
document.getElementById('send-text').textContent=t('Insert text','Indsæt tekst');
document.getElementById('text').placeholder=t('Type or paste text','Skriv eller indsæt tekst');
document.querySelector('label').textContent=t('For phone keyboards or paste: click the Google field first','Til mobilens tastatur eller indsættelse: klik først på feltet hos Google');
document.getElementById('hint').textContent=t('Sign in to Google above, then select Finish sign-in. PhotoHarbor keeps your session on your server.','Log ind hos Google ovenfor, og vælg Afslut login. PhotoHarbor gemmer sessionen på din server.');
if(account==='legacy')document.getElementById('account').textContent=t('Existing account','Eksisterende konto');
const socket=new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/login/stream?account='+encodeURIComponent(account));
let ready=false, ended=false, width=1280, height=800;
function send(data){if(socket.readyState===WebSocket.OPEN)socket.send(JSON.stringify(data));}
socket.onopen=()=>send({token});
socket.onmessage=event=>{
  const data=JSON.parse(event.data);
  if(data.type==='frame'){
    const image=new Image();
    image.onload=()=>{
      width=data.width;height=data.height;
      // CDP may downscale the JPEG independently of CSS/device coordinates.
      screen.width=image.naturalWidth;screen.height=image.naturalHeight;
      screen.getContext('2d').drawImage(image,0,0);
      send({type:'ack',session:data.session});
    };
    image.onerror=()=>send({type:'ack',session:data.session});
    image.src='data:image/jpeg;base64,'+data.image;
  } else if(data.type==='ready'){
    ready=true;status.textContent=t('Ready — click a Google field and sign in.','Klar — klik på et felt hos Google, og log ind.');
  } else if(data.type==='waiting')status.textContent=t('Starting Google sign-in…','Starter Google-login…');
  else if(data.type==='closed'){
    ended=true;ready=false;screen.getContext('2d').clearRect(0,0,screen.width,screen.height);
    status.textContent=t('Sign-in browser closed. You can return to PhotoHarbor.','Login-browseren er lukket. Du kan gå tilbage til PhotoHarbor.');
  } else if(data.type==='error'){
    ended=true;status.textContent=t(data.message,'Login kunne ikke starte. Luk vinduet, og prøv Google-login igen.');
  }
};
socket.onclose=()=>{ready=false;if(!ended)status.textContent=t('Connection ended. Close this window and reopen Google sign-in in PhotoHarbor.','Forbindelsen er afbrudt. Luk vinduet, og åbn Google-login igen i PhotoHarbor.');};
socket.onerror=()=>{status.textContent=t('Could not connect to the sign-in browser.','Kunne ikke forbinde til login-browseren.');};
function point(event){const r=screen.getBoundingClientRect();return{x:Math.max(0,Math.min(width,(event.clientX-r.left)*width/r.width)),y:Math.max(0,Math.min(height,(event.clientY-r.top)*height/r.height))};}
const button=e=>['left','middle','right'][e.button]||'none';
screen.addEventListener('pointerdown',e=>{if(!ready)return;e.preventDefault();screen.focus();screen.setPointerCapture(e.pointerId);send({type:'mouse',event:'mousePressed',button:button(e),...point(e)});});
screen.addEventListener('pointerup',e=>{if(ready)send({type:'mouse',event:'mouseReleased',button:button(e),...point(e)});});
screen.addEventListener('pointercancel',e=>{if(ready)send({type:'mouse',event:'mouseReleased',button:'left',...point(e)});});
screen.addEventListener('pointermove',e=>{if(ready)send({type:'mouse',event:'mouseMoved',button:e.buttons?'left':'none',...point(e)});});
screen.addEventListener('wheel',e=>{if(!ready)return;e.preventDefault();const factor=e.deltaMode===1?16:e.deltaMode===2?height:1;send({type:'mouse',event:'mouseWheel',button:'none',...point(e),deltaX:Math.max(-10000,Math.min(10000,e.deltaX*factor)),deltaY:Math.max(-10000,Math.min(10000,e.deltaY*factor))});},{passive:false});
screen.addEventListener('contextmenu',e=>e.preventDefault());
for(const [event,type] of [['keydown','keyDown'],['keyup','keyUp']])screen.addEventListener(event,e=>{
  if(!ready)return;
  // Let the local browser supply clipboard text through its paste event.
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='v')return;
  e.preventDefault();
  const text=type==='keyDown'&&e.key.length===1&&!e.ctrlKey&&!e.metaKey&&!e.altKey?e.key:'';
  send({type:'key',event:type,key:e.key,code:e.code,text,virtualKey:e.keyCode,modifiers:(e.altKey?1:0)|(e.ctrlKey?2:0)|(e.metaKey?4:0)|(e.shiftKey?8:0)});
});
screen.addEventListener('paste',e=>{if(!ready)return;e.preventDefault();send({type:'text',text:e.clipboardData.getData('text').slice(0,8192)});});
document.getElementById('text-form').addEventListener('submit',e=>{e.preventDefault();if(!ready)return;const input=document.getElementById('text');send({type:'text',text:input.value.slice(0,8192)});input.value='';screen.focus();});
document.getElementById('done').addEventListener('click',async e=>{
  e.target.disabled=true;
  try{
    const response=await fetch('/api/accounts/'+encodeURIComponent(account)+'/close-login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})});
    if(!response.ok)throw new Error('Close failed');
    status.textContent=t('Closing sign-in and saving the session…','Afslutter login og gemmer sessionen…');
  }catch(error){status.textContent=t('Could not close sign-in. Please try again.','Kunne ikke afslutte login. Prøv igen.');e.target.disabled=false;}
});
