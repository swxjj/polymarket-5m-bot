# Iniciar Bot de Polymarket y Dashboard
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "  Iniciando Bot de Polymarket (BTC 5m Momentum Scalper)" -ForegroundColor Green
Write-Host "  Dashboard en vivo: http://localhost:8055" -ForegroundColor Yellow
Write-Host "=================================================================" -ForegroundColor Cyan

Start-Process "http://localhost:8055"
python scripts\polymarket_5m_paper_tester.py --verbose
