import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_config.settings')

import django
django.setup()

# Import Celery app after Django setup
from core.celery_app import app as celery_app

__all__ = ('celery_app',)
