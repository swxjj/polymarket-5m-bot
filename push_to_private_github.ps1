Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "  Subir Bot de Polymarket a Repositorio Privado en GitHub" -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Cyan

gh auth status 2>&1 | Out-Null
if ( -ne 0) {
    Write-Host "No has iniciado sesion en GitHub CLI." -ForegroundColor Yellow
    Write-Host "Iniciando 'gh auth login'..." -ForegroundColor Cyan
    gh auth login
}

$repoName = Read-Host "Nombre del repositorio privado [default: polymarket-5m-bot]"
if ([string]::IsNullOrWhiteSpace($repoName)) {
    $repoName = "polymarket-5m-bot"
}

Write-Host "Creando repositorio privado '' y subiendo codigo..." -ForegroundColor Cyan
gh repo create $repoName --private --source=. --remote=origin --push

if ( -eq 0) {
    Write-Host "
Repositorio privado creado y pusheado exitosamente!" -ForegroundColor Green
} else {
    Write-Host "
Si ya existe el repo en tu GitHub, vinculalo con:" -ForegroundColor Yellow
    Write-Host "  git remote set-url origin https://github.com/TU_USUARIO/$repoName.git" -ForegroundColor Gray
    Write-Host "  git push -u origin main" -ForegroundColor Gray
}
