@echo off
title Polymarket 5m BTC Momentum Bot & Dashboard
echo =================================================================
echo   Iniciando Bot de Polymarket (BTC 5m Momentum Scalper)
echo   Dashboard en vivo: http://localhost:8055
echo =================================================================
echo Abriendo Dashboard en el navegador...
start http://localhost:8055
echo.
python scripts\polymarket_5m_paper_tester.py --verbose
pause
