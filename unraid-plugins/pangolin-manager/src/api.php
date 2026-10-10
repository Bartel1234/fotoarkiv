<?php
declare(strict_types=1);
require_once __DIR__.'/lib.php';
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');header('X-Content-Type-Options: nosniff');
function pm_response(array $data,int $code=200): never {
    http_response_code($code);echo json_encode($data,JSON_UNESCAPED_UNICODE|JSON_INVALID_UTF8_SUBSTITUTE);exit;
}
try {
    $method=$_SERVER['REQUEST_METHOD']??'GET';$action=$method==='POST'?($_POST['action']??''):($_GET['action']??'status');
    if ($method==='GET') {
        if ($action==='status') pm_response(['ok'=>true,'status'=>pm_get_status()]);
        if ($action==='settings') pm_response(['ok'=>true,'settings'=>pm_public_config(pm_config())]);
        if ($action==='containers') pm_response(['ok'=>true,'containers'=>pm_containers()]);
        pm_response(['ok'=>false,'error'=>'Ukendt handling.'],404);
    }
    if ($method!=='POST') pm_response(['ok'=>false,'error'=>'Metoden understøttes ikke.'],405);
    if (!pm_csrf_valid((string)($_POST['csrf_token']??''))) pm_response(['ok'=>false,'error'=>'Sessionen er udløbet. Genindlæs siden.'],403);
    if ($action==='save') {
        if (strlen((string)($_POST['payload']??''))>24000) throw new InvalidArgumentException('Indstillingerne er for store.');
        $input=json_decode((string)($_POST['payload']??''),true);
        if (!is_array($input)) throw new InvalidArgumentException('Ugyldige indstillinger.');
        $c=pm_validate($input,pm_config());pm_save_config($c);
        pm_response(['ok'=>true,'settings'=>pm_public_config($c)]);
    }
    if ($action==='test') pm_response(['ok'=>true,'status'=>pm_poll(false)]);
    if ($action==='logs') pm_response(['ok'=>true,'logs'=>pm_logs(pm_config())]);
    if ($action==='restart') {
        if (($_POST['confirm']??'')!=='restart-newt') throw new InvalidArgumentException('Genstart skal bekræftes.');
        $c=pm_config();$ins=pm_inspect($c['container']);if (!$ins) throw new RuntimeException('Newt-containeren kunne ikke findes.');
        $r=pm_exec(['docker','restart','--time','10',$ins['Id']],18);
        if ($r['code']!==0) throw new RuntimeException('Genstart kunne ikke bekræftes. Kontrollér Docker.');
        @unlink(pm_paths()['runtime'].'/status.json');
        pm_response(['ok'=>true,'message'=>'Newt er genstartet. Vent på næste kontrol.']);
    }
    pm_response(['ok'=>false,'error'=>'Ukendt handling.'],404);
} catch (InvalidArgumentException $e) {pm_response(['ok'=>false,'error'=>$e->getMessage()],400);}
catch (Throwable $e) {pm_response(['ok'=>false,'error'=>'Handlingen kunne ikke gennemføres. Kontrollér Docker, pluginets indstillinger og Unraid-loggen.'],500);}
