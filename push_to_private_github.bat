@echo off
title Push Polymarket Bot to Private GitHub
echo =================================================================
echo   Subir Bot de Polymarket a Repositorio Privado en GitHub
echo =================================================================
echo.
echo Verificando autenticacion con GitHub CLI (gh)...
gh auth status >nul 2>&1
if %errorlevel% neq 0 (
    echo No has iniciado sesion en GitHub CLI.
    echo Iniciando autenticacion interactiva con 'gh auth login'...
    echo (Sigue los pasos en pantalla o en el navegador)
    echo.
    gh auth login
)

echo.
set /p REPO_NAME="Introduce el nombre del repositorio privado en GitHub [default: polymarket-5m-bot]: "
if "%REPO_NAME%"=="" set REPO_NAME=polymarket-5m-bot

echo Creando y pusheando a repositorio privado: %REPO_NAME%...
gh repo create %REPO_NAME% --private --source=. --remote=origin --push

if %errorlevel% equ 0 (
    echo.
    echo =================================================================
    echo   EXITO: Repositorio privado creado y codigo pusheado a GitHub!
    echo =================================================================
) else (
    echo.
    echo Hubo un problema al crear o pushear el repositorio.
    echo Si ya creaste el repositorio manualmente en GitHub, ejecuta:
    echo   git remote set-url origin https://github.com/TU_USUARIO/TU_REPO.git
    echo   git push -u origin main
)
pause
