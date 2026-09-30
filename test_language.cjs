// Language preference and safe text translation without a browser dependency.
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const root=path.join(__dirname,'dashboard');
const catalog=JSON.parse(fs.readFileSync(path.join(root,'translations.json'),'utf8'));
function session(saved, cookie='') {
 const heading={dataset:{i18n:'Backup overblik'},textContent:''};
 const input={attrs:{'data-i18n-placeholder':'Søg efter filnavn'},getAttribute(k){return this.attrs[k]},setAttribute(k,v){this.attrs[k]=v}};
 const buttons=['en','da'].map(lang=>({dataset:{language:lang},attrs:{},setAttribute(k,v){this.attrs[k]=v},addEventListener(k,fn){this.click=fn}}));
 const events=[];let preference=saved;
 const document={documentElement:{},cookie,getElementById:()=>({textContent:JSON.stringify(catalog)}),querySelectorAll:q=>q==='[data-i18n]'?[heading]:q==='[data-language]'?buttons:q==='[data-i18n-placeholder]'?[input]:[]};
 const context=vm.createContext({document,localStorage:{getItem:()=>preference,setItem:(k,v)=>{preference=v}},location:{protocol:'https:'},window:{dispatchEvent:e=>events.push(e.type)},Event:class {constructor(type){this.type=type}}});
 vm.runInContext(fs.readFileSync(path.join(root,'i18n.js'),'utf8'),context);
 return {phase:account=>vm.runInContext('I18n.phase('+JSON.stringify(account)+')',context),document,heading,input,buttons,events,get preference(){return preference},t:key=>vm.runInContext('I18n.t('+JSON.stringify(key)+')',context)};
}
let s=session(null);assert.equal(s.document.documentElement.lang,'en');assert.equal(s.heading.textContent,'Backup overview');assert.equal(s.input.attrs.placeholder,'Search by filename');assert.equal(s.t('Ugyldig formular'),'Invalid form token');
assert.equal(s.phase({phase:'indexing',indexed_items:1000,indexed_albums:86}).title,'Indexing photos and albums');assert.equal(s.phase({phase:'indexing',indexed_items:1000,indexed_albums:86}).detail,'1,000 indexed photos · 86 albums');assert.equal(s.phase({phase:'idle'}),null);
s.buttons[1].click();assert.equal(s.heading.textContent,'Backup overblik');assert.equal(s.preference,'da');assert.equal(s.phase({phase:'indexing',indexed_items:1000,indexed_albums:86}).detail,'1.000 indekserede billeder · 86 albums');assert.equal(s.buttons[1].attrs['aria-pressed'],'true');assert.match(s.document.cookie,/fotoarkiv_language=da/);assert.match(s.document.cookie,/Secure/);assert.equal(s.t('Ugyldig formular'),'Ugyldig formular');assert.deepEqual(s.events,['languagechange']);
s=session(s.preference);assert.equal(s.document.documentElement.lang,'da');s.buttons[0].click();assert.equal(s.heading.textContent,'Backup overview');assert.equal(s.preference,'en');assert.equal(s.t('album title unchanged'),'album title unchanged');
for(const filename of ['index.html','archive.html']){
 const source=fs.readFileSync(path.join(root,filename),'utf8');assert.match(source,/lang="en"/);assert.match(source,/data-language="en"/);assert.match(source,/data-language="da"/);
 for(const match of source.matchAll(/data-i18n(?:-placeholder|-title|-aria-label)?="([^"]+)"/g))assert.ok(catalog[match[1]],'Missing translation: '+match[1]);
}
console.log('English default, both languages, saved preference, translated labels/errors, flags and unchanged album titles passed');
