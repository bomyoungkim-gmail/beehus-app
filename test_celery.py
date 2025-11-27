#!/usr/bin/env python
"""
Script para testar Celery tasks manualmente
Execute: python test_celery.py
Ou dentro do container: docker-compose exec web python test_celery.py
"""

import os
import sys
import django
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'beehus_app.settings')
django.setup()

from celery import Celery
from crawl_log.tasks import hello, login_to_jpmorgan
from dotenv import load_dotenv

print("=" * 60)
print("🧪 TESTADOR DE CELERY TASKS")
print("=" * 60)

# Test 1: Simple hello task
print("\n1️⃣  Testando task 'hello'...")
try:
    result = hello.delay()
    print(f"✅ Task enviada! ID: {result.id}")
    print(f"   Status: {result.status}")
    print(f"   Resultado: {result.get(timeout=10)}")
except Exception as e:
    print(f"❌ Erro: {e}")

# Test 2: Login task (requer credenciais)
print("\n2️⃣  Testando task 'login_to_jpmorgan'...")
load_dotenv()
jp_user = os.getenv("JP_USERID")
jp_pass = os.getenv("JP_PASSWORD")

if jp_user and jp_pass:
    try:
        result = login_to_jpmorgan.delay(jp_user, jp_pass)
        print(f"✅ Task enviada! ID: {result.id}")
        print(f"   Status: {result.status}")
        print(f"   ⏳ Aguardando conclusão (máx 30s)...")
        print(f"   Resultado: {result.get(timeout=30)}")
    except Exception as e:
        print(f"❌ Erro: {e}")
else:
    print("⚠️  Credenciais JP_USERID e JP_PASSWORD não configuradas em .env")

print("\n" + "=" * 60)
print("✅ Teste concluído!")
print("=" * 60)
