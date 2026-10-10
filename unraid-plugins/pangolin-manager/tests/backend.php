<?php
// Meaningful regression tests. Run with PHP 8.1+ and cURL. No Unraid changes.
declare(strict_types=1);
require dirname(__DIR__).'/src/lib.php';
$n=0;
function check(bool $condition,string $what): void {global $n;if(!$condition)throw new RuntimeException($what);$n++;}
function invalid(array $patch): bool {try{pm_validate(array_replace(pm_defaults(),$patch),pm_defaults());return false;}catch(InvalidArgumentException $e){return true;}}
check(invalid(['container'=>'newt; touch /tmp/unsafe']),'Reject shell metacharacters in container name');
check(invalid(['container'=>'--help']),'Reject option injection');
check(invalid(['endpoint'=>'file:///etc/passwd']),'Reject file URLs');
check(invalid(['endpoint'=>'http://user:secret@example.com']),'Reject embedded credentials');
check(invalid(['api_url'=>'http://example.com/v1']),'Do not send API token over HTTP');
check(invalid(['api_url'=>'https://example.com/v1?token=x']),'Reject query in API base address');
check(invalid(['api_url'=>'https://example.com']),'Require explicit API version base');
check(invalid(['services'=>[['name'=>['x'],'url'=>'http://example.com']]]),'Reject invalid service field types');
check(invalid(['health_file'=>'/tmp/healthy;id']),'Reject invalid health path');
check(invalid(['api_key'=>"token\r\nInjected: header"]),'Reject header injection');
$old=pm_defaults();$old['api_key']='saved-secret';
$c=pm_validate(pm_defaults(),$old);check($c['api_key']==='saved-secret','Blank key preserves saved key');
$c=pm_validate(array_replace(pm_defaults(),['clear_api_key'=>true]),$old);check($c['api_key']==='','Explicit clear removes key');
check(!array_key_exists('api_key',pm_public_config($old)),'Public settings never expose key');
$m=pm_exec([PHP_BINARY,'-n','-r','echo $argv[1];','$(touch /tmp/pm-test-unsafe); & echo bad']);
check($m['code']===0 && $m['out']==='$(touch /tmp/pm-test-unsafe); & echo bad','Commands bypass shell interpretation');
$t=microtime(true);$m=pm_exec([PHP_BINARY,'-n','-r','sleep(2);'],.1);
check($m['code']===124 && microtime(true)-$t<1,'Bound stalled subprocesses');
check(pm_http_check(['code'=>200,'error'=>'','ms'=>1])['state']==='up','Successful HTTP check');
check(pm_http_check(['code'=>403,'error'=>'','ms'=>1])['state']==='unknown','Protected endpoint does not prove health');
check(pm_http_check(['code'=>403,'error'=>'','ms'=>1],'reachable')['state']==='up','Protected server reachability');
check(pm_http_check(['code'=>500,'error'=>'','ms'=>1])['state']==='down','HTTP 500 is not healthy');
check(pm_http_check(['code'=>0,'error'=>'PHP cURL mangler.','ms'=>0])['state']==='unknown','Missing measurement support is unknown');
check(pm_site_state(['data'=>['sites'=>[['siteId'=>42,'online'=>true]]]],'42')['state']==='up','Read site list with explicit online flag');
check(pm_site_state(['data'=>['sites'=>[['siteId'=>42,'online'=>'true']]]],'42')['state']==='unknown','Do not trust string boolean');
check(pm_site_state(['data'=>['online'=>false]],'42')['state']==='down','Explicit offline flag');
check(pm_site_state(['data'=>['unexpected'=>true]],'42')['state']==='unknown','Unknown API schema stays unknown');
check(pm_site_state(['data'=>'invalid'],'42')['state']==='unknown','Invalid API payload stays unknown');
check(pm_site_state(['data'=>['sites'=>[['siteId'=>41,'online'=>true]]]],'42')['state']==='unknown','Missing site stays unknown');
$text=pm_redact('secret=some-secret api_key="token-123" Authorization: Bearer secret-token secret-in-env https://a.test/x?token=hello',['secret-in-env']);
foreach(['some-secret','token-123','secret-token','secret-in-env','token=hello'] as $secret)check(!str_contains($text,$secret),'Redact '.$secret);
$status=['container'=>pm_check('up','Kører'),'tunnel'=>pm_check('down','Afbrudt'),'endpoint'=>pm_check('unknown','Ikke konfigureret'),'services'=>[]];
[$state,$event]=pm_notification_transition($status,[],1000);check($event===null,'Do not alert on transient fault');
[$state,$event]=pm_notification_transition($status,$state,1119);check($event===null,'Wait full two minutes');
[$state,$event]=pm_notification_transition($status,$state,1120);check($event==='down','Alert on sustained fault');
[$state,$event]=pm_notification_transition($status,$state,1180);check($event===null,'Do not repeat same outage notification');
$status['tunnel']=pm_check('unknown','Ukendt');[$state,$event]=pm_notification_transition($status,$state,1210);check($event===null && $state['notified'],'Unknown is not recovery');
$status['tunnel']=pm_check('up','Forbundet');[$state,$event]=pm_notification_transition($status,$state,1240);check($event==='recovered','Confirmed recovery produces one notification');
[$state,$event]=pm_notification_transition($status,$state,1270);check($event===null,'Do not repeat recovery');
check(!pm_csrf_valid(''),'Empty token fails closed');
$file=sys_get_temp_dir().'/pm-test-config-'.getmypid().'.json';pm_write($file,['x'=>'y']);check(json_decode((string)file_get_contents($file),true)['x']==='y','Atomic config write');unlink($file);
echo "PASS: $n backend checks\n";
