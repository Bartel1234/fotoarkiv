<?php
declare(strict_types=1);
if (PHP_SAPI!=='cli') {http_response_code(404);exit;}
require_once __DIR__.'/lib.php';
try {pm_poll(true);} catch (Throwable $e) {error_log('Pangolin Manager: baggrundskontrol fejlede.');exit(1);}
