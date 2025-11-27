#!/bin/bash
# Script para recarregar serviços sem rebuild completo (para Linux/Mac)

SERVICE="${1:-all}"

echo "═══════════════════════════════════════════════════════════"
echo "🔄 Recarregando serviços Celery/Django (sem rebuild)"
echo "═══════════════════════════════════════════════════════════"

if [ "$SERVICE" = "all" ] || [ "$SERVICE" = "web" ]; then
    echo -e "\n📦 Reiniciando Django Web..."
    docker-compose restart web
fi

if [ "$SERVICE" = "all" ] || [ "$SERVICE" = "celery" ]; then
    echo -e "\n⚙️  Reiniciando Celery Worker..."
    docker-compose restart celery
fi

if [ "$SERVICE" = "all" ] || [ "$SERVICE" = "celery-beat" ]; then
    echo -e "\n⏰ Reiniciando Celery Beat..."
    docker-compose restart celery-beat
fi

echo -e "\n✅ Serviços reiniciados!"
echo -e "\n💡 Dica: Mudanças em arquivos Python são sincronizadas automaticamente."
echo "   Se adicionar dependências, execute: docker-compose up -d --build"
