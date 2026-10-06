"""Local job telemetry, SMTP delivery and a deliberately restricted diagnostic export."""
import argparse
import json
import os
import re
import smtplib
import ssl
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from backup_state import atomic, load, settings

ADDRESS = re.compile(r'^[^\s@<>\r\n,;]+@[^\s@<>\r\n,;]+\.[^\s@<>\r\n,;]+$')

def smtp_path(state):
    return (state.parent.parent if state.parent.name == 'accounts' else state)/'smtp.json'

def smtp_validate(data, previous=None):
    if not isinstance(data,dict): raise ValueError('Invalid email settings')
    previous = previous or {}
    config = {key:data.get(key,default) for key,default in [('enabled',False),('host',''),('port',587),('security','starttls'),('username',''),('sender',''),('recipient',''),('language','en')]}
    if type(config['enabled']) is not bool or type(config['port']) is not int or not 1<=config['port']<=65535: raise ValueError('Invalid SMTP port or switch')
    if config['security'] not in ('starttls','tls') or config['language'] not in ('en','da'): raise ValueError('Choose encrypted SMTP and a supported language')
    for key in ('host','username','sender','recipient'):
        value=config[key]
        if not isinstance(value,str) or len(value)>254 or any(ord(c)<32 for c in value): raise ValueError('Invalid SMTP field')
        config[key]=value.strip()
    password=data.get('password','')
    if not isinstance(password,str) or len(password)>4096: raise ValueError('Invalid SMTP password')
    config['password'] = '' if data.get('clear_password') is True else password or previous.get('password','')
    if config['enabled'] and (not config['host'] or '/' in config['host'] or not ADDRESS.fullmatch(config['sender']) or not ADDRESS.fullmatch(config['recipient'])): raise ValueError('Enter SMTP host, sender and one recipient address')
    return config

def smtp_public(config):
    return {key:value for key,value in config.items() if key!='password'} | {'password_saved':bool(config.get('password'))}

def smtp_save(path,config):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    with os.fdopen(os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as file:
        os.fchmod(file.fileno(),0o600);json.dump(config,file)
    temporary.replace(path)

def send_mail(config,subject,body):
    config=smtp_validate(config)
    if not config['enabled']: raise ValueError('Email is disabled')
    message=EmailMessage();message['From']=config['sender'];message['To']=config['recipient'];message['Subject']=subject;message.set_content(body)
    context=ssl.create_default_context()
    client=smtplib.SMTP_SSL(config['host'],config['port'],timeout=15,context=context) if config['security']=='tls' else smtplib.SMTP(config['host'],config['port'],timeout=15)
    with client as server:
        if config['security']=='starttls': server.ehlo();server.starttls(context=context);server.ehlo()
        if config['username']: server.login(config['username'],config['password'])
        server.send_message(message)

def downloaded(state):
    entries={}
    try:
        with (state/'downloads.jsonl').open() as file:
            for line in file:
                try:
                    entry=json.loads(line)
                    if entry.get('bytes',0)>0: entries[(entry['id'],entry['name'])]=entry
                except (ValueError,KeyError,TypeError): continue
    except OSError: pass
    return {'downloaded_files':len(entries),'downloaded_images':sum(e['kind']=='image' for e in entries.values()),'downloaded_videos':sum(e['kind']=='video' for e in entries.values()),'downloaded_bytes':sum(e['bytes'] for e in entries.values())}

def notify_email(state,entry):
    policy=settings(state);config=load(smtp_path(state),{})
    if not policy.get('email_enabled') or not config.get('enabled'): return
    if policy.get('email_mode','all')=='errors' and entry['result'] in (0,130,131): return
    da=config.get('language')=='da'
    outcome={0:('gennemført','completed'),130:('afbrudt','stopped'),131:('sat på pause','paused'),132:('sat på pause: lav diskplads','paused: low disk space')}.get(entry['result'],('fejlet','failed'))[0 if da else 1]
    account=state.name if state.parent.name=='accounts' else ('Eksisterende konto' if da else 'Existing account')
    amount=f"{entry.get('downloaded_bytes',0)/1024**2:.1f} MB"
    subject=f"PhotoHarbor: {outcome} — {entry.get('downloaded_files',0)} {'filer' if da else 'files'}, {amount}"
    values=[('Opgave','Task',entry['mode']),('Konto','Account',account),('Resultat','Result',outcome),('Start','Started',entry['started']),('Afsluttet','Finished',entry['finished']),('Varighed','Duration',f"{entry['duration']} s"),('Hentede billeder','Downloaded photos',entry.get('downloaded_images',0)),('Hentede videoer','Downloaded videos',entry.get('downloaded_videos',0)),('Hentet størrelse','Downloaded size',amount),('Genforsøg','Retries',entry.get('retries',0)),('Exitkode','Exit code',entry['result'])]
    space=load(state/'storage.json',{})
    if 'free' in space:values.append(('Ledig plads','Free space',f"{space['free']/1024**3:.1f} GB"))
    verification=entry.get('verification') or {}
    if verification.get('available'):
        values.extend([('Manglende katalogfiler','Missing catalog files',verification.get('missing',0)),('Tomme katalogfiler','Empty catalog files',verification.get('empty',0))])
    content=load(state/'content.json',{})
    if entry['mode']=='content': values.extend([('Kontrollerede filer','Checked files',content.get('checked',0)),('Ændrede checksums','Changed checksums',content.get('changed',0)),('Afkodningsfejl','Decode errors',content.get('decode_errors',0))])
    body='\n'.join(f'{a if da else b}: {value}' for a,b,value in values)
    body+='\n\n'+('Tallet omfatter færdige downloads i denne kørsel, inklusive genhentninger. Albumreferencer og filer sprunget over tælles ikke. En gennemført kørsel er ikke bevis for fuld Google-dækning. Ved fejl: se kontoens aktivitet i PhotoHarbor.' if da else 'Counts include completed downloads in this run, including redownloads. Album references and skipped files are excluded. A completed run does not prove full Google coverage. On failure, check the account activity in PhotoHarbor.')
    try:
        send_mail(config,subject,body);atomic(state/'email-status.json',{'ok':True,'at':entry['finished']})
    except Exception:
        atomic(state/'email-status.json',{'ok':False,'at':entry['finished']});print('Email delivery failed; backup result is unchanged',flush=True)

def live(state):
    data=load(state/'live.json',{})
    current=load(state/'current-run.json',{})
    now=time.time();started=current.get('started',now)
    age=max(0,now-data.get('at',started))
    return {**data,'duration':int(max(0,now-started)),'activity_age':int(age),'stalled':bool(current and age>900),'average_bytes_per_second':data.get('completed_bytes',0)/max(1,now-started)}

def index_due(root,state,force=False):
    metadata=load(root/'.fotoarkiv/metadata.json',{})
    if force or metadata.get('complete') is not True: return True
    try: updated=datetime.fromisoformat(metadata['updated'].replace('Z','+00:00')).timestamp()
    except (ValueError,KeyError,TypeError): return True
    hours=settings(state).get('index_hours',24)
    return hours==0 or not 0<=time.time()-updated<hours*3600

def retryable(state):
    failure=load(state/'download-failure.json',{})
    return failure.get('retryable') is True and time.time()-failure.get('at',0)<120

def diagnostics(state,version):
    # Allowlist structured fields. No raw logs, filenames, account names, paths,
    # SMTP/ntfy settings, browser URLs, tokens or media enter this document.
    report={'format':'photoharbor-diagnostics','schema':1,'version':version,'generated':datetime.now(timezone.utc).isoformat()}
    for file,keys in [('storage.json',('free','total','reserve','low','warning')),('live.json',('at','visited','completed_files','completed_bytes','attempt')),('verification.json',('checked','missing','empty','unbacked_items','available')),('email-status.json',('ok','at'))]:
        data=load(state/file,{})
        report[file.removesuffix('.json')]={k:data[k] for k in keys if k in data}
    report['history']=[{k:e[k] for k in ('started','finished','duration','result','mode','new_files','new_bytes','downloaded_files','downloaded_bytes','downloaded_images','downloaded_videos','retries') if k in e} for e in load(state/'history.json',[])[:20]]
    failure=load(state/'download-failure.json',{})
    report['failure']={k:failure[k] for k in ('at','retryable','category') if k in failure}
    report['policy']={k:settings(state)[k] for k in ('enabled','hour','days','index_hours','retry_count','min_free_gb','min_free_percent')}
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['index-due','retryable']);p.add_argument('state',type=Path);p.add_argument('root',type=Path,nargs='?');p.add_argument('--force',action='store_true');a=p.parse_args()
    raise SystemExit(0 if (index_due(a.root,a.state,a.force) if a.action=='index-due' else retryable(a.state)) else 1)
