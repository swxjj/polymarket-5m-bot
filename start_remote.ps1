# Iniciar Bot de Polymarket + Dashboard Cloudflare Tunnel + Remote Control
Write-Host '=================================================================' -ForegroundColor Cyan
Write-Host '  Iniciando Bot de Polymarket (Paper Trading) + Tunnel Cloudflare' -ForegroundColor Green
Write-Host '=================================================================' -ForegroundColor Cyan

 = 'C:\Users\flia.barros\AppData\Local\Programs\Python\Python311\python.exe'
 = 'C:\Users\flia.barros\poly'
 = 'C:\Users\flia.barros\.gemini\remote-control'

# 1. Start Polymarket Bot & Cloudflare quick tunnel in background
Start-Process -FilePath  -ArgumentList 'run_service.py' -WorkingDirectory  -WindowStyle Hidden

# 2. Start Antigravity Remote Command Center for poly workspace in background
powershell -ExecutionPolicy Bypass -File (Join-Path  'start.ps1') -Cwd  -Background

Write-Host '[SUCCESS] Todo iniciado en segundo plano.' -ForegroundColor Green
Write-Host 'En unos segundos recibirás la notificación en tu iPhone vía ntfy.' -ForegroundColor Yellow
