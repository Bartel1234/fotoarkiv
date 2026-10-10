<?php
declare(strict_types=1);
// Pangolin Manager 0.1.0-beta.4. No third-party runtime dependencies.
const PM_VERSION = '0.1.0-beta.4';
// Only explicitly authored, safe messages from this class reach the browser.
class PMException extends RuntimeException {}
function pm_paths(): array {
    return ['config'=>'/boot/config/plugins/pangolin-manager/settings.json',
        'runtime'=>'/var/local/pangolin-manager', 'vars'=>'/var/local/emhttp/var.ini',
        'notify'=>'/usr/local/emhttp/webGui/scripts/notify'];
}
function pm_defaults(): array {
    return ['container'=>'', 'endpoint'=>'', 'health_file'=>'', 'api_url'=>'', 'api_key'=>'',
        'org_id'=>'', 'site_id'=>'', 'notifications'=>false, 'services'=>[]];
}
function pm_config(): array {
    $p=pm_paths();
    if (!is_file($p['config'])) return pm_defaults();
    $c=json_decode((string)file_get_contents($p['config']),true);
    if (!is_array($c)) throw new PMException('Indstillingerne kan ikke læses. Gem dem igen fra panelet.');
    return array_replace(pm_defaults(),$c);
}
function pm_public_config(array $c): array {
    $c['has_api_key']=$c['api_key']!==''; unset($c['api_key']); return $c;
}
function pm_write(string $path, array $data): void {
    if (!is_dir(dirname($path)) && !mkdir(dirname($path),0700,true) && !is_dir(dirname($path)))
        throw new PMException('Mappen til indstillinger/status kunne ikke oprettes.');
    $tmp=tempnam(dirname($path),'.pm-');
    if ($tmp===false) throw new PMException('Kunne ikke oprette midlertidig fil.');
    try {
        if (file_put_contents($tmp,json_encode($data,JSON_UNESCAPED_UNICODE|JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR))===false)
            throw new PMException('Kunne ikke gemme filen.');
        chmod($tmp,0600);
        if (!rename($tmp,$path)) throw new PMException('Kunne ikke gemme filen.');
    } finally { if (is_file($tmp)) unlink($tmp); }
}
function pm_url(string $url, bool $httpsOnly=false): string {
    if ($url==='') return '';
    $u=parse_url($url);
    if (!$u || !isset($u['scheme'],$u['host']) || !in_array($u['scheme'],$httpsOnly?['https']:['http','https'],true)
        || isset($u['user']) || isset($u['pass']) || isset($u['fragment']) || preg_match('/[\x00-\x20\x7f]/',$url)
        || strlen($url)>1024) throw new InvalidArgumentException('Brug en gyldig HTTP(S)-adresse uden login eller mellemrum. API kræver HTTPS.');
    return $url;
}
function pm_validate(array $in, array $old): array {
    $c=pm_defaults();
    foreach (['container','endpoint','health_file','api_url','org_id','site_id'] as $k) {
        if (isset($in[$k]) && !is_string($in[$k])) throw new InvalidArgumentException('Ugyldig indstilling.');
        $c[$k]=trim((string)($in[$k]??''));
    }
    if ($c['container']!=='' && !preg_match('/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$/D',$c['container']))
        throw new InvalidArgumentException('Ugyldigt containernavn.');
    if ($c['health_file']!=='' && !preg_match('~^/[a-zA-Z0-9_./-]{1,200}$~D',$c['health_file']))
        throw new InvalidArgumentException('Healthcheck-fil skal være en absolut sti i Newt-containeren.');
    foreach (['org_id','site_id'] as $k) if ($c[$k]!=='' && !preg_match('/^[a-zA-Z0-9_-]{1,128}$/D',$c[$k]))
        throw new InvalidArgumentException('Ugyldigt organisation/site-ID.');
    $c['endpoint']=pm_url($c['endpoint']); $c['api_url']=rtrim(pm_url($c['api_url'],true),'/');
    if ($c['api_url']!=='' && (parse_url($c['api_url'],PHP_URL_QUERY)!==null || !preg_match('~/v1$~',parse_url($c['api_url'],PHP_URL_PATH)??'')))
        throw new InvalidArgumentException('API-baseadressen skal slutte med /v1 og må ikke have parametre.');
    $key=$in['api_key']??'';
    if (!is_string($key) || strlen($key)>4096 || preg_match('/[\x00-\x20\x7f]/',$key))
        throw new InvalidArgumentException('Ugyldig API-nøgle.');
    $c['api_key']=!empty($in['clear_api_key'])?'':($key!==''?$key:$old['api_key']);
    $c['notifications']=($in['notifications']??false)===true;
    $services=$in['services']??[];
    if (!is_array($services) || count($services)>12) throw new InvalidArgumentException('Der kan højst tilføjes 12 tjenester.');
    foreach ($services as $s) {
        if (!is_array($s)) throw new InvalidArgumentException('Ugyldig tjeneste.');
        foreach (['name','url','public_url','mode'] as $key) if (isset($s[$key]) && !is_string($s[$key]))
            throw new InvalidArgumentException('Ugyldigt tjenestefelt.');
        $name=trim((string)($s['name']??'')); $url=trim((string)($s['url']??''));
        if ($name==='' && $url==='') continue;
        if ($name==='' || strlen($name)>80 || preg_match('/[\x00-\x1f\x7f]/',$name) || $url==='')
            throw new InvalidArgumentException('Hver tjeneste skal have navn og lokal URL.');
        $public=pm_url(trim((string)($s['public_url']??'')));
        $mode=$s['mode']??'http'; if (!in_array($mode,['http','reachable'],true)) throw new InvalidArgumentException('Ugyldig kontroltype.');
        $c['services'][]=['name'=>$name,'url'=>pm_url($url),'public_url'=>$public,'mode'=>$mode];
    }
    return $c;
}
function pm_exec(array $args, float $timeout=4.0): array {
    // PHP-FPM's PATH can differ from the interactive shell on Unraid.
    if (($args[0]??'')==='docker') foreach (['/usr/bin/docker','/usr/local/bin/docker','/bin/docker'] as $binary) {
        if (is_executable($binary)) {$args[0]=$binary;break;}
    }
    if (!function_exists('proc_open')) {
        if (!function_exists('exec')) return ['code'=>127,'out'=>'','err'=>'PHP tillader hverken proc_open eller exec.'];
        $timer=is_executable('/usr/bin/timeout')?'/usr/bin/timeout':(is_executable('/bin/timeout')?'/bin/timeout':'');
        if ($timer==='') return ['code'=>127,'out'=>'','err'=>'Kommandoen timeout mangler.'];
        // Every argument is quoted separately; only our fixed redirection is shell syntax.
        $command=implode(' ',array_map('escapeshellarg',array_merge([$timer,'--signal=KILL',sprintf('%.3fs',max(.001,$timeout))],$args)));
        $lines=[];$code=127;exec($command.' 2>&1',$lines,$code);$out=implode("\n",$lines);
        return ['code'=>$code===137?124:$code,'out'=>substr($out,0,1048576),'err'=>$code===0?'':'Kommando fejlede (kode '.$code.').'];
    }
    // proc_open receives an argument array: user input is never parsed by a shell.
    $p=@proc_open($args,[0=>['pipe','r'],1=>['pipe','w'],2=>['pipe','w']],$pipes);
    if (!is_resource($p)) return ['code'=>127,'out'=>'','err'=>'Kommando kunne ikke startes.'];
    fclose($pipes[0]); stream_set_blocking($pipes[1],false); stream_set_blocking($pipes[2],false);
    $start=microtime(true);$out='';$err='';$code=-1;
    while (true) {
        $out.=stream_get_contents($pipes[1]);$err.=stream_get_contents($pipes[2]);
        if (strlen($out)>1048576 || strlen($err)>65536) { proc_terminate($p,9);$code=125;break; }
        $st=proc_get_status($p);
        if (!$st['running']) { $code=$st['exitcode'];break; }
        if (microtime(true)-$start>$timeout) { proc_terminate($p,9);$code=124;break; }
        usleep(10000);
    }
    $out.=stream_get_contents($pipes[1]);$err.=stream_get_contents($pipes[2]);
    fclose($pipes[1]);fclose($pipes[2]);$closed=proc_close($p);
    return ['code'=>$code<0?$closed:$code,'out'=>$out,'err'=>$err];
}
function pm_docker_request(string $path): array {
    // Docker reads use the same local Unix socket as Unraid's Docker Manager.
    // No TCP daemon access, redirects, credentials or user-selected socket.
    $socket='/var/run/docker.sock';
    if (!file_exists($socket)) return ['code'=>0,'data'=>null,'error'=>'Dockers lokale forbindelse mangler.'];
    if (!function_exists('curl_init') || !defined('CURLOPT_UNIX_SOCKET_PATH'))
        return ['code'=>0,'data'=>null,'error'=>'PHP cURL understøtter ikke Dockers lokale forbindelse.'];
    $h=curl_init('http://localhost'.$path);$body='';
    curl_setopt_array($h,[CURLOPT_UNIX_SOCKET_PATH=>$socket,CURLOPT_PROXY=>'',CURLOPT_CONNECTTIMEOUT_MS=>1000,
        CURLOPT_TIMEOUT_MS=>3000,CURLOPT_FOLLOWLOCATION=>false,CURLOPT_PROTOCOLS=>CURLPROTO_HTTP,
        CURLOPT_WRITEFUNCTION=>function($h,$chunk)use(&$body){if(strlen($body)+strlen($chunk)>4194304)return 0;$body.=$chunk;return strlen($chunk);}]);
    curl_exec($h);$error=curl_errno($h);$code=(int)curl_getinfo($h,CURLINFO_RESPONSE_CODE);curl_close($h);
    if ($error) return ['code'=>0,'data'=>null,'error'=>$error===28?'Docker svarede ikke inden for 3 sekunder.':'Pluginet kunne ikke åbne Dockers lokale forbindelse.'];
    $data=json_decode($body,true);
    return ['code'=>$code,'data'=>$data,'error'=>$code===200 && is_array($data)?'':'Docker svarede med HTTP '.$code.' eller et ugyldigt svar.'];
}
function pm_containers(): array {
    $socket=pm_docker_request('/containers/json?all=1');
    $list=[];
    if ($socket['error']==='' && is_array($socket['data']) && array_is_list($socket['data'])) {
        foreach ($socket['data'] as $v) if (is_array($v)) {
            $name=ltrim((string)($v['Names'][0]??''),'/');if($name==='')continue;
            $list[]=['name'=>$name,'image'=>$v['Image']??'','state'=>$v['State']??''];
        }
    } else {
        // Also supports installations where socket reads are unavailable.
        $r=pm_exec(['docker','ps','-a','--format','{{json .}}']);
        if ($r['code']!==0) throw new PMException('Containerlisten kunne ikke hentes. '.$socket['error'].' Docker-kommandoen fejlede (kode '.$r['code'].'). Kontrollér Settings → Docker i Unraid.');
        foreach (explode("\n",trim($r['out'])) as $line) {
            if ($line==='')continue;
            $v=json_decode($line,true);
            if (!is_array($v) || empty($v['Names'])) throw new PMException('Docker returnerede en ugyldig containerliste.');
            $list[]=['name'=>$v['Names'],'image'=>$v['Image']??'','state'=>$v['State']??''];
        }
    }
    foreach ($list as &$v) $v['suggested']=(bool)preg_match('~newt|pangolin-cli~i',$v['name'].' '.$v['image']);unset($v);
    usort($list,fn($a,$b)=>($b['suggested']<=>$a['suggested'])?:strcasecmp($a['name'],$b['name']));return $list;
}
function pm_redact(string $text, array $secrets=[]): string {
    foreach ($secrets as $s) if (is_string($s) && strlen($s)>=4) $text=str_replace($s,'[skjult]',$text);
    $text=preg_replace('/(Bearer\s+)[^\s,;"\']+/i','$1[skjult]',$text);
    $text=preg_replace('/((?:NEWT_SECRET|SITE_SECRET|secret|token|api[_-]?key|password|authorization)["\']?\s*[:=]\s*["\']?)[^\s,;"\'}]+/i','$1[skjult]',$text);
    return preg_replace('~(https?://[^\s?#]+\?)[^\s]+~i','$1[skjult]',$text);
}
function pm_check(string $state,string $label,string $detail='',array $more=[]): array {
    return array_merge(['state'=>$state,'label'=>$label,'detail'=>$detail],$more);
}
function pm_http(string $url, bool $body=false, array $headers=[]): array {
    if (!function_exists('curl_init')) return ['code'=>0,'error'=>'PHP cURL mangler.','body'=>'','ms'=>0];
    $h=curl_init($url);$data='';
    curl_setopt_array($h,[CURLOPT_CONNECTTIMEOUT_MS=>1500,CURLOPT_TIMEOUT_MS=>2500,
        CURLOPT_FOLLOWLOCATION=>false,CURLOPT_SSL_VERIFYPEER=>true,CURLOPT_SSL_VERIFYHOST=>2,
        CURLOPT_PROTOCOLS=>CURLPROTO_HTTP|CURLPROTO_HTTPS,CURLOPT_HTTPHEADER=>$headers,
        CURLOPT_USERAGENT=>'Unraid-Pangolin-Manager/'.PM_VERSION,
        CURLOPT_WRITEFUNCTION=>function($h,$chunk)use(&$data,$body){ if ($body) { if (strlen($data)+strlen($chunk)>1048576)return 0; $data.=$chunk; } return strlen($chunk); }]);
    curl_exec($h);$err=curl_errno($h);$ms=round(curl_getinfo($h,CURLINFO_TOTAL_TIME)*1000);
    $code=(int)curl_getinfo($h,CURLINFO_RESPONSE_CODE);curl_close($h);
    $errors=[6=>'DNS-opslag fejlede.',7=>'Forbindelse kunne ikke oprettes.',28=>'Kontrollen fik timeout.',35=>'TLS-forbindelse fejlede.',60=>'TLS-certifikatet kunne ikke verificeres.'];
    return ['code'=>$code,'error'=>$err?($errors[$err]??'Netværkskontrol fejlede (kode '.$err.').'):'','body'=>$data,'ms'=>$ms];
}
function pm_http_check(array $r,string $mode='http'): array {
    if ($r['error']==='PHP cURL mangler.') return pm_check('unknown','Kontrol utilgængelig',$r['error']);
    if ($r['error']!=='') return pm_check('down','Ingen forbindelse',$r['error'],['ms'=>$r['ms']]);
    $code=$r['code'];
    if ($code>=200 && $code<400) return pm_check('up','Svarer','HTTP '.$code,['ms'=>$r['ms']]);
    if (in_array($code,[401,403],true)) return pm_check($mode==='reachable'?'up':'unknown','Kræver adgang',
        'HTTP '.$code.'. Serveren svarer, men tjenestens sundhed kan ikke bekræftes uden adgang.',['ms'=>$r['ms']]);
    if ($code===0) return pm_check('unknown','Ukendt','Intet HTTP-resultat.');
    return pm_check($mode==='reachable'?'up':'down',$mode==='reachable'?'Server svarer':'HTTP-fejl','HTTP '.$code,['ms'=>$r['ms']]);
}
function pm_site_state(array $response,string $id): array {
    // Only explicit booleans/known enums are accepted. A changed API schema stays unknown.
    $data=$response['data']??$response;
    if (!is_array($data)) return pm_check('unknown','Ukendt','API-formatet genkendes ikke.');
    if (isset($data['site']) && is_array($data['site'])) $data=$data['site'];
    if (isset($data['sites']) && is_array($data['sites'])) $data=$data['sites'];
    if (array_is_list($data)) {
        $found=null;
        foreach ($data as $site) if (is_array($site) && (string)($site['siteId']??$site['id']??'')===$id) {$found=$site;break;}
        if ($found===null) return pm_check('unknown','Site ikke fundet','Kontrollér site-ID og API-rettigheder.');
        $data=$found;
    }
    if (!is_array($data)) return pm_check('unknown','Ukendt','API-formatet genkendes ikke.');
    $online=$data['online']??null;
    if (!is_bool($online)) {
        $status=$data['status']??null;
        $online=in_array($status,['online','connected'],true)?true:(in_array($status,['offline','disconnected'],true)?false:null);
    }
    return $online===null?pm_check('unknown','Ukendt','API-svaret indeholder ingen understøttet forbindelsesstatus.'):
        pm_check($online?'up':'down',$online?'Forbundet':'Afbrudt','Status fra Pangolins API.');
}
function pm_inspect(string $name): ?array {
    if ($name==='') return null;
    $socket=pm_docker_request('/containers/'.rawurlencode($name).'/json');
    if ($socket['code']===404) return null;
    if ($socket['error']==='' && is_array($socket['data']) && isset($socket['data']['Id'])) return $socket['data'];
    $r=pm_exec(['docker','inspect','--type','container',$name]);
    if ($r['code']!==0) return null;
    $a=json_decode($r['out'],true);return is_array($a)&&isset($a[0])?$a[0]:null;
}
function pm_collect(array $c): array {
    $result=['version'=>PM_VERSION,'checked_at'=>time(),'configured'=>$c['container']!=='',
        'container'=>pm_check('unknown','Vælg Newt-container','Åbn indstillinger for at komme i gang.'),
        'tunnel'=>pm_check('unknown','Ukendt','Tilføj healthcheck eller API for at måle tunnellen.'),
        'endpoint'=>pm_check('unknown','Ikke konfigureret'),'services'=>[], 'endpoint_url'=>$c['endpoint']];
    $ins=pm_inspect($c['container']);$env=[];
    foreach ($ins['Config']['Env']??[] as $line) { $parts=explode('=',$line,2);if(count($parts)===2)$env[$parts[0]]=$parts[1]; }
    if ($c['container']!=='' && !$ins) $result['container']=pm_check('down','Ikke fundet','Containeren mangler, eller Docker svarer ikke.');
    if ($ins) {
        $running=($ins['State']['Running']??false)===true && !($ins['State']['Paused']??false) && !($ins['State']['Restarting']??false);
        $result['container']=pm_check($running?'up':'down',$running?'Kører':'Stoppet / genstarter',
            'Container: '.$c['container'],['name'=>$c['container'],'restarts'=>(int)($ins['RestartCount']??0),'started_at'=>$ins['State']['StartedAt']??'']);
        if (!$running) $result['tunnel']=pm_check('down','Afbrudt','Newt-containeren kører ikke normalt.');
        else {
            $health=$c['health_file']?:($env['HEALTH_FILE']??'');
            if ($health!=='' && preg_match('~^/[a-zA-Z0-9_./-]{1,200}$~D',$health)) {
                $r=pm_exec(['docker','exec',$ins['Id'],'test','-f',$health]);
                $result['tunnel']=$r['code']===0?pm_check('up','Forbundet','Newts forbindelsesfil findes.'):
                    ($r['code']===1?pm_check('down','Afbrudt','Newts forbindelsesfil mangler.'):
                    pm_check('unknown','Ukendt','Healthcheck kunne ikke køres. Brug API, eller kontrollér om containeren har kommandoen test.'));
            }
        }
    }
    if ($result['tunnel']['state']==='unknown' && $c['api_url']!=='' && $c['api_key']!=='' && $c['org_id']!=='' && $c['site_id']!=='') {
        $r=pm_http($c['api_url'].'/org/'.rawurlencode($c['org_id']).'/sites',true,['Authorization: Bearer '.$c['api_key']]);
        if ($r['error']!=='' || $r['code']!==200) $result['tunnel']=pm_check('unknown','API utilgængeligt',
            $r['error']?:'API svarede HTTP '.$r['code'].'. Kontrollér adresse og rettigheder.');
        else { $j=json_decode($r['body'],true);$result['tunnel']=is_array($j)?pm_site_state($j,$c['site_id']):pm_check('unknown','Ukendt','API svarede ikke med JSON.'); }
    }
    $endpoint=$c['endpoint']?:($env['PANGOLIN_ENDPOINT']??'');
    try { if ($endpoint!=='') {pm_url($endpoint);$result['endpoint']=pm_http_check(pm_http($endpoint),'reachable');$result['endpoint_url']=$endpoint;} }
    catch (InvalidArgumentException $e) {$result['endpoint']=pm_check('unknown','Ugyldig adresse');}
    $probes=pm_http_many(array_column($c['services'],'url'));
    foreach ($c['services'] as $i=>$s) {
        $check=pm_http_check($probes[$i],$s['mode']);
        $result['services'][]=array_merge($s,$check,['scope'=>'Kontrolleret fra Unraid']);
    }
    $result['checked_at']=time();$result['summary']=pm_summary($result);return $result;
}
function pm_http_many(array $urls): array {
    if (!$urls) return [];
    if (!function_exists('curl_multi_init')) return array_map(fn($url)=>['code'=>0,'error'=>'PHP cURL mangler.','body'=>'','ms'=>0],$urls);
    $multi=curl_multi_init();$handles=[];$results=[];
    try {
        foreach ($urls as $i=>$url) {
            $h=curl_init($url);
            curl_setopt_array($h,[CURLOPT_CONNECTTIMEOUT_MS=>1500,CURLOPT_TIMEOUT_MS=>2500,
                CURLOPT_FOLLOWLOCATION=>false,CURLOPT_SSL_VERIFYPEER=>true,CURLOPT_SSL_VERIFYHOST=>2,
                CURLOPT_PROTOCOLS=>CURLPROTO_HTTP|CURLPROTO_HTTPS,CURLOPT_USERAGENT=>'Unraid-Pangolin-Manager/'.PM_VERSION,
                CURLOPT_WRITEFUNCTION=>fn($h,$chunk)=>strlen($chunk)]);
            $handles[$i]=$h;curl_multi_add_handle($multi,$h);
        }
        $deadline=microtime(true)+4;
        do {
            $code=curl_multi_exec($multi,$running);
            if ($running && $code===CURLM_OK) { if (curl_multi_select($multi,.1)===-1)usleep(10000); }
        } while ($running && $code===CURLM_OK && microtime(true)<$deadline);
        foreach ($handles as $i=>$h) {
            $err=curl_errno($h);$http=(int)curl_getinfo($h,CURLINFO_RESPONSE_CODE);
            $errors=[6=>'DNS-opslag fejlede.',7=>'Forbindelse kunne ikke oprettes.',28=>'Kontrollen fik timeout.',35=>'TLS-forbindelse fejlede.',60=>'TLS-certifikatet kunne ikke verificeres.'];
            $results[$i]=['code'=>$http,'error'=>$running?'Kontrollen fik timeout.':($err?($errors[$err]??'Netværkskontrol fejlede (kode '.$err.').'):''),
                'body'=>'','ms'=>round(curl_getinfo($h,CURLINFO_TOTAL_TIME)*1000)];
        }
    } finally {foreach($handles as $h){curl_multi_remove_handle($multi,$h);curl_close($h);}curl_multi_close($multi);}
    return $results;
}
function pm_summary(array $s): string {
    if (!$s['configured']) return 'Vælg din Newt-container i indstillingerne.';
    if ($s['container']['state']==='down') return 'Newt-containeren kører ikke normalt. Kontrollér Docker og containerens log.';
    if ($s['tunnel']['state']==='down') return 'Newt-forbindelsen er afbrudt. Kontrollér Pangolin-serveren og Newt-loggen.';
    foreach ($s['services'] as $svc) if ($svc['state']==='down') return 'Den lokale kontrol af '.$svc['name'].' fejler. Kontrollér adresse, port og container.';
    if ($s['endpoint']['state']==='down') return 'Pangolin-adressen svarer ikke fra Unraid. Kontrollér DNS, TLS og netværk.';
    if ($s['tunnel']['state']==='unknown') return 'Containerstatus alene bekræfter ikke tunnellen. Aktivér en forbindelseskontrol i indstillingerne.';
    return 'Ingen fejl fundet i de konfigurerede kontroller. Lokale tjenestetests bekræfter ikke ekstern adgang.';
}
function pm_get_status(): array {
    $p=pm_paths();$f=$p['runtime'].'/status.json';
    $s=is_file($f)?json_decode((string)file_get_contents($f),true):null;
    if (!is_array($s)) return ['checked_at'=>0,'configured'=>false,'stale'=>true,'summary'=>'Ingen måling endnu. Åbn panelet og vælg Test forbindelse.'];
    $s['stale']=time()-(int)$s['checked_at']>90;
    if ($s['stale']) {
        foreach (['container','tunnel','endpoint'] as $key) $s[$key]=pm_check('unknown','Forældet måling','Status er over 90 sekunder gammel.');
        foreach ($s['services'] as &$service) { $service['state']='unknown';$service['label']='Forældet måling'; }unset($service);
        $s['summary']='Målingerne er for gamle. Test forbindelsen, og kontrollér at pluginets baggrundskontrol kører.';
    }
    return $s;
}
function pm_save_config(array $c): void {
    // Serialize against polling: a worker may not publish old settings after a save.
    $p=pm_paths();if (!is_dir($p['runtime']) && !mkdir($p['runtime'],0700,true) && !is_dir($p['runtime']))
        throw new PMException('Statusmappen kunne ikke oprettes.');
    $lock=fopen($p['runtime'].'/collect.lock','c');
    if (!$lock)throw new PMException('Statuslåsen kunne ikke oprettes.');
    $deadline=microtime(true)+15;
    try {
        while (!flock($lock,LOCK_EX|LOCK_NB)) {
            if (microtime(true)>$deadline)throw new PMException('En kontrol er stadig i gang. Prøv at gemme igen.');
            usleep(50000);
        }
        pm_write($p['config'],$c);
        @unlink($p['runtime'].'/notifications.json');@unlink($p['runtime'].'/status.json');
    }finally{flock($lock,LOCK_UN);fclose($lock);}
}
function pm_notification_transition(array $status,array $prev,int $now): array {
    $checks=['container'=>$status['container'],'tunnel'=>$status['tunnel']];
    if (($status['endpoint']['label']??'')!=='Ikke konfigureret') $checks['endpoint']=$status['endpoint'];
    foreach ($status['services'] as $i=>$svc) $checks['service-'.$i]=$svc;
    $faults=[];$unknown=false;
    foreach ($checks as $k=>$v) {if ($v['state']==='down')$faults[]=$k; if ($v['state']==='unknown')$unknown=true;}
    $state=$prev+['since'=>0,'notified'=>false];$event=null;
    if ($faults) {
        if (!$state['since'])$state['since']=$now;
        if (!$state['notified'] && $now-$state['since']>=120) {$event='down';$state['notified']=true;}
    } elseif (!$unknown) {
        if ($state['notified'])$event='recovered';
        $state=['since'=>0,'notified'=>false];
    } elseif (!$state['notified']) { $state['since']=0; }
    return [$state,$event];
}
function pm_poll(bool $notify=true): array {
    $p=pm_paths();if (!is_dir($p['runtime']))mkdir($p['runtime'],0700,true);
    $lock=fopen($p['runtime'].'/collect.lock','c');
    if (!$lock || !flock($lock,LOCK_EX|LOCK_NB)) return pm_get_status();
    try {
        $c=pm_config();$s=pm_collect($c);pm_write($p['runtime'].'/status.json',$s);
        if ($notify && $c['notifications'] && $s['configured']) {
            $f=$p['runtime'].'/notifications.json';$prev=is_file($f)?json_decode((string)file_get_contents($f),true):[];
            [$state,$event]=pm_notification_transition($s,is_array($prev)?$prev:[],time());
            if ($event && is_executable($p['notify'])) {
                $r=pm_exec([$p['notify'],'-e','Pangolin Manager','-s',$event==='down'?'Pangolin: vedvarende fejl':'Pangolin: forbindelsen er tilbage',
                    '-d',$event==='down'?$s['summary']:'Alle konfigurerede kontroller svarer igen.','-i',$event==='down'?'warning':'normal','-l','/Tools/PangolinManager'],10);
                if ($r['code']!==0) $state['notified']=$prev['notified']??false;
            }
            pm_write($f,$state);
        }
        return $s;
    } finally {flock($lock,LOCK_UN);fclose($lock);}
}
function pm_logs(array $c): string {
    if ($c['container']==='') return 'Vælg en Newt-container først.';
    $ins=pm_inspect($c['container']); if (!$ins) return 'Containeren kunne ikke læses.';
    $secrets=[$c['api_key']];
    foreach ($ins['Config']['Env']??[] as $e) { $pair=explode('=',$e,2);if(count($pair)===2&&preg_match('/secret|token|key|pass/i',$pair[0]))$secrets[]=$pair[1]; }
    $r=pm_exec(['docker','logs','--tail','120','--since','24h',$ins['Id']]);
    return pm_redact(substr($r['out']."\n".$r['err'],-48000),$secrets);
}
function pm_csrf_valid(string $provided): bool {
    $vars=@parse_ini_file(pm_paths()['vars']);$expected=$vars['csrf_token']??'';
    return is_string($expected)&&$expected!==''&&$provided!==''&&hash_equals($expected,$provided);
}
