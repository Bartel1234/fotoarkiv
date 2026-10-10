// DOM interaction tests using jsdom. This is not a visual browser/layout test.
const {JSDOM}=require(process.env.PM_TEST_JSDOM || 'jsdom');
const fs=require('fs'),path=require('path'),assert=require('assert');
const root=path.join(__dirname,'..'),script=fs.readFileSync(path.join(root,'src/app.js'),'utf8');
let status={configured:true,checked_at:Math.floor(Date.now()/1000),stale:false,
 container:{state:'up',label:'Kører',restarts:0},tunnel:{state:'up',label:'Forbundet'},endpoint:{state:'up',label:'Svarer'},
 endpoint_url:'https://pangolin.example.com',summary:'Ingen fejl.',
 services:[{name:'PhotoHarbor',url:'http://192.168.1.10:8787',public_url:'https://fotos.example.com',state:'up',label:'Svarer',ms:12,mode:'http'}]};
let settings={container:'Newt',endpoint:'https://pangolin.example.com',health_file:'',api_url:'',org_id:'',site_id:'',has_api_key:true,notifications:false,services:status.services};
let restartCount=0,saved=null,testCount=0,denyStatus=false,logsCount=0;
async function until(fn){for(let i=0;i<100;i++){if(fn())return;await new Promise(r=>setTimeout(r,10));}throw Error('Timed out waiting for UI');}
function mount(html){
 const dom=new JSDOM(html,{url:'http://unraid.test/Tools/PangolinManager',runScripts:'outside-only',pretendToBeVisual:true});
 const w=dom.window;w.csrf_token='fixture-csrf';w.AbortController=AbortController;
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
 w.HTMLDialogElement.prototype.close=function(){this.open=false;};
 let interval;
 w.setInterval=fn=>{interval=fn;return 1;};
 w.fetch=async(url,options)=>{
  const body=new URLSearchParams(options.body||'');const action=body.get('action')||new URL(url,'http://unraid.test').searchParams.get('action');
  if(options.method==='POST')assert.equal(body.get('csrf_token'),'fixture-csrf');
  const result={ok:true};
  if(action==='status'){if(denyStatus)throw Error('Fixture network failed');result.status=status;}
  if(action==='test'){result.status=status;testCount++;}
  if(action==='settings')result.settings=settings;
  if(action==='containers')result.containers=[{name:'Newt',image:'fosrl/newt:fixture',suggested:true}];
  if(action==='save'){saved=JSON.parse(body.get('payload'));settings={...settings,...saved};delete settings.api_key;result.settings=settings;}
  if(action==='logs'){logsCount++;result.logs='NEWT_SECRET=[skjult]\nINFO connected';}
  if(action==='restart'){assert.equal(body.get('confirm'),'restart-newt');restartCount++;result.message='Newt er genstartet.';}
  return {ok:true,json:async()=>structuredClone(result)};
 };
 w.eval(script);return {dom,w,doc:w.document,poll:()=>interval()};
}
(async()=>{
 const html=fs.readFileSync(path.join(root,'src/PangolinManager.page'),'utf8').split('\n---\n')[1];
 const {dom,w,doc,poll}=mount(html);
 await until(()=>doc.querySelector('[data-pm-tunnel]').textContent==='Forbundet');
 assert.equal(doc.querySelectorAll('[data-pm-services] tr').length,1);
 assert.equal(doc.querySelector('[data-pm-container]').dataset.state,'up');
 doc.querySelector('[data-tab="settings"]').click();
 await until(()=>doc.querySelector('#pm-api-key-state').textContent.includes('gemt'));
 assert.equal(doc.querySelector('[name="api_key"]').value,'');
 const before=doc.querySelectorAll('.pm-service-edit').length;doc.querySelector('#pm-add-service').click();assert.equal(doc.querySelectorAll('.pm-service-edit').length,before+1);
 [...doc.querySelectorAll('.pm-service-edit')].at(-1).querySelector('button').click();assert.equal(doc.querySelectorAll('.pm-service-edit').length,before);
 doc.querySelector('[name="endpoint"]').value='https://new.example.com';
 doc.querySelector('#pm-settings').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
 await until(()=>saved && testCount===1);
 assert.equal(saved.endpoint,'https://new.example.com');assert.equal(saved.api_key,'');assert.equal(saved.services.length,1);
 doc.querySelector('#pm-restart').click();assert(doc.querySelector('dialog').open);assert.equal(restartCount,0);
 doc.querySelector('#pm-cancel-restart').click();assert(!doc.querySelector('dialog').open);assert.equal(restartCount,0);
 doc.querySelector('#pm-restart').click();doc.querySelector('#pm-confirm-restart').click();await until(()=>restartCount===1&&!doc.querySelector('dialog').open);
 doc.querySelector('[data-tab="logs"]').click();await until(()=>doc.querySelector('#pm-log').textContent.includes('[skjult]'));assert.equal(logsCount,1);
 status.services[0].name='<img src=x onerror="window.pmInjected=true">';await poll();assert.equal(doc.querySelector('[data-pm-services] img'),null);assert.equal(w.pmInjected,undefined);assert(doc.querySelector('[data-pm-services]').textContent.includes('<img'));
 status={...status,stale:true,tunnel:{state:'unknown',label:'Forældet måling'},summary:'Målingerne er for gamle.'};await poll();assert.equal(doc.querySelector('[data-pm-tunnel]').dataset.state,'unknown');
 denyStatus=true;await poll();assert.equal(doc.querySelector('[data-pm-container]').dataset.state,'unknown');assert(doc.querySelector('#pm-message').textContent.includes('failed'));denyStatus=false;
 dom.window.close();
 const widget=fs.readFileSync(path.join(root,'src/PangolinManagerDashboard.page'),'utf8').split("<<<'PM_TILE'\n")[1].split('\nPM_TILE;')[0];
 status.tunnel={state:'up',label:'Forbundet'};status.stale=false;
 const tile=mount('<table>'+widget+'</table>');await until(()=>tile.doc.querySelector('[data-pm-tunnel]').textContent==='Forbundet');
 assert.equal(tile.doc.querySelector('[data-pm-services-summary]').textContent,'1/1 svarer');assert.equal(tile.doc.querySelector('[data-pm-open]').href,'https://pangolin.example.com/');
 tile.doc.querySelector('[data-pm-test]').click();await until(()=>testCount===2);tile.w.close();
 console.log('PASS: DOM interactions for panel and Dashboard tile: status, settings, secret field, service edits, CSRF payload, restart/cancel, logs, hostile labels, stale status and failed refresh');
})().catch(e=>{console.error(e);process.exit(1)});
