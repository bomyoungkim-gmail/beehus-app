celery -A beehus_app worker --loglevel=info --pool=solo


# Django
python manage.py runserver
# Painel do Django admin
# http://localhost:8000/admin/


DJANGO
USER beehus
PASS admin@123


python manage.py migrate


docker-compose up db --build
docker-compose up rabbitmq --build

docker-compose up