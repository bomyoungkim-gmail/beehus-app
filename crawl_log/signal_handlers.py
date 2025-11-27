"""
Signal handlers para capturar metadados de tasks no django-celery-results.

Isso garante que task_name, worker, periodic_task_name, etc sejam salvos no TaskResult.
"""
from celery.signals import task_prerun, task_postrun
from django_celery_results.models import TaskResult
from django_celery_beat.models import PeriodicTask


@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kw):
    """Handler executado antes da task rodar"""
    pass


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **kw):
    """Handler executado após a task rodar - garante que metadados são salvos"""
    try:
        # Atualizar o TaskResult com metadados que podem não ter sido capturados
        tr = TaskResult.objects.filter(task_id=task_id).first()
        if tr:
            updated = False
            
            if not tr.task_name and task:
                tr.task_name = task.name
                updated = True
                
            if not tr.worker and sender:
                # sender é a instância da task - tenta pegar hostname do request
                request = getattr(sender, 'request', None)
                if request:
                    tr.worker = getattr(request, 'hostname', 'unknown')
                    updated = True
            
            # Tentar preencher periodic_task_name se não foi preenchido
            if not tr.periodic_task_name and tr.task_name:
                # Procurar PeriodicTask que corresponde a esta task
                try:
                    pt = PeriodicTask.objects.filter(task=tr.task_name).first()
                    if pt:
                        tr.periodic_task_name = pt.name
                        updated = True
                except Exception:
                    pass
            
            if updated:
                tr.save(update_fields=['task_name', 'worker', 'periodic_task_name'])
    except Exception as e:
        print(f"Erro ao atualizar TaskResult metadados: {e}")
