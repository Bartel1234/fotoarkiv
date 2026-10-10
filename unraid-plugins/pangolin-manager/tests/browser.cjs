// A real browser with mocked API responses. No connection to the user's server.
const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
const root=path.join(__dirname,'..');
const pageSource=fs.readFileSync(path.join(root,'src/PangolinManager.page'),'utf8').split('\n---\n')[1];
const css=fs.readFileSync(path.join(root,'src/style.css'),'utf8');
const js=fs.readFileSync(path.join(root,'src/app.js'),'utf8');
const baseStatus={configured:true,checked_at:Math.floor(Date.now()/1000),stale:false,
 container:{state:'up',label:'Kører',detail:'Container: Newt',restarts:0},
 tunnel:{state:'up',label:'Forbundet',detail:'Newts forbindelsesfil findes.'},
 endpoint:{state:'up',label:'Svarer',detail:'HTTP 200'},endpoint_url:'https://pangolin.example.com',
 services:[{name:'PhotoHarbor',url:'http://192.168.1.10:8787',public_url:'https://fotos.example.com',state:'up',label:'Svarer',detail:'HTTP 200',ms:12,mode:'http'},
 {name:'Home Assistant',url:'http://192.168.1.10:8123',public_url:'',state:'up',label:'Svarer',detail:'HTTP 200',ms:8,mode:'http'},
 {name:'Nextcloud',url:'http://192.168.1.10:8443',public_url:'',state:'down',label:'HTTP-fejl',detail:'HTTP 503',ms:18,mode:'http'}],
 summary:'Den lokale kontrol af Nextcloud fejler. Kontrollér adresse, port og container.'};
let status=structuredClone(baseStatus),restarts=0,saved=null;
const settings={container:'Newt',endpoint:'https://pangolin.example.com',health_file:'',api_url:'',has_api_key:true,org_id:'',site_id:'',notifications:false,services:baseStatus.services.map(({name,url,public_url,mode})=>({name,url,public_url,mode}))};
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.PM_TEST_BROWSER?{executablePath:process.env.PM_TEST_BROWSER}:{}),args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1360,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('http://unraid.test/**',async route=>{
  const req=route.request(),u=new URL(req.url());
  if(u.pathname.endsWith('style.css'))return route.fulfill({contentType:'text/css',body:css});
  if(u.pathname.endsWith('app.js'))return route.fulfill({contentType:'text/javascript',body:js});
  if(u.pathname.endsWith('api.php')){
   const body=new URLSearchParams(req.postData()||'');const action=body.get('action')||u.searchParams.get('action');
   if(req.method()==='POST')assert.equal(body.get('csrf_token'),'fixture-csrf');
   let result={ok:true};
   if(action==='status'||action==='test')result.status=status;
   if(action==='settings')result.settings=settings;
   if(action==='containers')result.containers=[{name:'Newt',image:'fosrl/newt:1.9.0',suggested:true}];
   if(action==='logs')result.logs='INFO Newt connected\nNEWT_SECRET=[skjult]';
   if(action==='save'){saved=JSON.parse(body.get('payload'));Object.assign(settings,saved);delete settings.api_key;settings.has_api_key=true;result.settings=settings;}
   if(action==='restart'){assert.equal(body.get('confirm'),'restart-newt');restarts++;result.message='Newt er genstartet.';}
   return route.fulfill({contentType:'application/json',body:JSON.stringify(result)});
  }
  if(u.pathname==='/preview-dark'||u.pathname==='/preview-light'){
   const dark=u.pathname.endsWith('dark');
   return route.fulfill({contentType:'text/html',body:`<!doctype html><html lang="da"><meta charset="utf-8"><style>body{margin:0;background:${dark?'#151719':'#fafafa'};color:${dark?'#e0e3e6':'#242a30'};font-family:Arial,sans-serif;color-scheme:${dark?'dark':'light'}}.shell{background:${dark?'#22262b':'#fff'};padding:18px 32px;border-bottom:1px solid #8884;font-size:13px}.shell span{float:right;color:#92979e}</style><div class="shell">UNRAID · DeathStar <span>Dashboard &nbsp; Main &nbsp; Shares &nbsp; Docker &nbsp; Tools</span></div><script>var csrf_token='fixture-csrf';</script>${pageSource}</html>`});
  }
  if(u.pathname==='/widget'){
   const source=fs.readFileSync(path.join(root,'src/PangolinManagerDashboard.page'),'utf8');
   const tile=source.split("<<<'PM_TILE'\n")[1].split('\nPM_TILE;')[0];
   return route.fulfill({contentType:'text/html',body:`<!doctype html><meta charset="utf-8"><style>body{background:#151719;color:#e0e3e6;font:14px Arial;color-scheme:dark;padding:30px}table{width:380px;background:#22262b;border-radius:8px;padding:20px}.section{font-size:17px;font-weight:bold;padding-bottom:16px}.control{display:none}</style><link rel="stylesheet" href="/plugins/pangolin-manager/style.css"><script>var csrf_token='fixture-csrf';</script><table>${tile}</table><script src="/plugins/pangolin-manager/app.js"></script>`});
  }
  return route.abort();
 });
 await page.goto('http://unraid.test/preview-dark');await page.locator('[data-pm-tunnel]').filter({hasText:'Forbundet'}).waitFor();
 assert.equal(await page.locator('[data-pm-services] tr').count(),3);
 await page.screenshot({path:path.join(root,'dist/panel-dark.png'),fullPage:true});
 await page.getByRole('button',{name:'Indstillinger',exact:true}).click();await page.locator('#pm-api-key-state').filter({hasText:'API-nøgle er gemt'}).waitFor();
 assert.equal(await page.locator('[name="api_key"]').inputValue(),'');
 await page.locator('[name="endpoint"]').fill('https://new.example.com');
 await page.getByRole('button',{name:'Gem indstillinger',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#pm-message').textContent.includes('færdig'));
 assert.equal(saved.endpoint,'https://new.example.com');assert.equal(saved.api_key,'');assert.equal(saved.services.length,3);
 await page.getByRole('button',{name:'Genstart Newt…',exact:true}).click();
 assert.equal(restarts,0);await page.getByRole('button',{name:'Annuller',exact:true}).click();assert.equal(restarts,0);
 await page.getByRole('button',{name:'Genstart Newt…',exact:true}).click();await page.locator('#pm-confirm-restart').click();await page.waitForFunction(()=>!document.querySelector('#pm-restart-dialog').open);assert.equal(restarts,1);
 // An API label with HTML must render as literal text, never execute.
 status.services[0].name='<img src=x onerror="window.pmInjected=true">';
 await page.getByRole('button',{name:'Test forbindelse',exact:true}).click();await page.waitForFunction(()=>document.querySelector('[data-pm-services]').textContent.includes('<img'));
 assert.equal(await page.evaluate(()=>window.pmInjected),undefined);
 status=structuredClone(baseStatus);
 await page.goto('http://unraid.test/preview-light');await page.locator('[data-pm-tunnel]').filter({hasText:'Forbundet'}).waitFor();await page.screenshot({path:path.join(root,'dist/panel-light.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(root,'dist/panel-mobile.png'),fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'Mobile page fits viewport');
 await page.goto('http://unraid.test/widget');await page.locator('[data-pm-tunnel]').filter({hasText:'Forbundet'}).waitFor();await page.setViewportSize({width:480,height:600});await page.screenshot({path:path.join(root,'dist/widget-dark.png'),fullPage:true});
 status={...baseStatus,stale:true,tunnel:{state:'unknown',label:'Forældet måling'},summary:'Målingerne er for gamle.'};
 await page.getByRole('button',{name:'Test',exact:true}).click();await page.locator('[data-pm-tunnel]').filter({hasText:'Forældet måling'}).waitFor();assert.equal(await page.locator('[data-pm-tunnel]').getAttribute('data-state'),'unknown');
 assert.deepEqual(errors,[]);await browser.close();console.log('PASS: browser rendering, settings, CSRF payload, restart confirmation, XSS, stale status and mobile layout');
})().catch(e=>{console.error(e);process.exit(1)});
