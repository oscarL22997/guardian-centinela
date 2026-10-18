# Generador de carga para la defensa (Windows PowerShell, sin instalar nada).
#   .\herramientas\generar-carga.ps1 -N 300
# En otra ventana:  docker stats
param([int]$N = 300, [string]$Url = "http://localhost:8080")
$usuarios = Invoke-RestMethod "$Url/api/dominio/usuarios?limit=30"
$lat = @(); $replicas = @{}
for ($i = 0; $i -lt $N; $i++) {
  $u = $usuarios | Get-Random
  $body = @{ usuario_id = $u.usuario_id; dispositivo_id = $u.dispositivo_id; monto = (Get-Random -Minimum 2000 -Maximum 250000);
             moneda = "CLP"; canal = "app"; mcc = "5411"; pais_transaccion = "CL"; intentos_previos_1h = 0 } | ConvertTo-Json
  $sw = [Diagnostics.Stopwatch]::StartNew()
  try { $r = Invoke-RestMethod -Method Post -Uri "$Url/api/dominio/evaluar" -ContentType "application/json" -Body $body
        $replicas[$r.replica_ia] = 1 + [int]$replicas[$r.replica_ia] } catch { $replicas["error"] = 1 + [int]$replicas["error"] }
  $sw.Stop(); $lat += $sw.Elapsed.TotalMilliseconds
}
$o = $lat | Sort-Object
"peticiones: $N   p50: {0:N1} ms   p95: {1:N1} ms   p99: {2:N1} ms" -f $o[[int]($N*0.5)], $o[[int]($N*0.95)], $o[[int]($N*0.99)-1]
"réplicas de IA:"; $replicas
