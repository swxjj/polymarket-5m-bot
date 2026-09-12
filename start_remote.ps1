# Iniciar Bot de Polymarket + Dashboard en controlremoto.tech
Write-Host '=================================================================' -ForegroundColor Cyan
Write-Host '  Iniciando Bot de Polymarket (Paper Trading) + controlremoto.tech' -ForegroundColor Green
Write-Host '=================================================================' -ForegroundColor Cyan

$PythonExe = 'C:\Users\flia.barros\AppData\Local\Programs\Python\Python311\python.exe'
if (-not (Test-Path $PythonExe)) {
    $PythonExe = 'python'
}
$PolyDir = 'C:\Users\flia.barros\poly'
$GatewayDir = 'C:\Users\flia.barros\.gemini\remote-control'

# 1. Start Gateway & Tunnel in background
powershell -ExecutionPolicy Bypass -File (Join-Path $GatewayDir 'start.ps1') -Background

# 2. Start Polymarket Bot & Dashboard
Start-Process -FilePath $PythonExe -ArgumentList 'run_service.py' -WorkingDirectory $PolyDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PolyDir 'run_service.log') -RedirectStandardError (Join-Path $PolyDir 'run_service.err.log')

Write-Host '[SUCCESS] Bot y Gateway iniciados en segundo plano.' -ForegroundColor Green
Write-Host 'Tu dashboard estará disponible en: https://controlremoto.tech' -ForegroundColor Yellow
