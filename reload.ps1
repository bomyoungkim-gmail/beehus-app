#!/usr/bin/env pwsh
# Script para recarregar serviços sem rebuild completo

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("web", "celery", "celery-beat", "all")]
    [string]$Service = "all"
)

Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "🔄 Recarregando serviços Celery/Django (sem rebuild)" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan

if ($Service -eq "all" -or $Service -eq "web") {
    Write-Host "`n📦 Reiniciando Django Web..." -ForegroundColor Green
    docker-compose restart web
}

if ($Service -eq "all" -or $Service -eq "celery") {
    Write-Host "`n⚙️  Reiniciando Celery Worker..." -ForegroundColor Green
    docker-compose restart celery
}

if ($Service -eq "all" -or $Service -eq "celery-beat") {
    Write-Host "`n⏰ Reiniciando Celery Beat..." -ForegroundColor Green
    docker-compose restart celery-beat
}

Write-Host "`n✅ Serviços reiniciados!" -ForegroundColor Green
Write-Host "`n💡 Dica: Mudanças em arquivos Python são sincronizadas automaticamente." -ForegroundColor Cyan
Write-Host "   Se adicionar dependências, execute: docker-compose up -d --build" -ForegroundColor Cyan
