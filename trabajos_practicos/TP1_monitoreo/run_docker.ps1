$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker no esta instalado o no esta en PATH." -ForegroundColor Red
    Write-Host "Instala Docker Desktop y volve a ejecutar:" -ForegroundColor Yellow
    Write-Host "  docker compose up --build"
    exit 1
}

docker compose up --build
