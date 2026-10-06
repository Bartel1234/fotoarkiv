"""Read account stages without treating old logs as current progress."""
import re

STAGES={'starting','waiting_login','indexing','organizing','downloading','checking','finishing','checking_content','reviewing_albums'}

def progress(state, raw_log, *, online, running, pending, stopping, login_active):
    result={'phase':'idle','indexed_items':None,'indexed_albums':None}
    if not online:
        result['phase']='offline'
    elif stopping:
        result['phase']='stopping'
    elif pending and login_active:
        result['phase']='waiting_login'
    elif running:
        try:stage=(state/'phase').read_text().strip()
        except OSError:stage=''
        result['phase']=stage if stage in STAGES else 'starting'
        if stage=='indexing':
            # Discard counts from an earlier run still present in the log tail.
            tail=raw_log.rsplit('Henter albums og Google-datoer',1)[-1]
            if 'Henter albums og Google-datoer' in raw_log or 'Starter synkronisering:' not in tail:
                matches=re.findall(r'Albumindeksering: (\d+) billeder, (\d+) albums',tail)
                if matches:result.update(indexed_items=int(matches[-1][0]),indexed_albums=int(matches[-1][1]))
    elif pending:
        result['phase']='starting'
    elif (state/'paused').exists():
        result['phase']='paused'
    return result
