from django.apps import AppConfig


class CrawlLogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'crawl_log'
    
    def ready(self):
        # Import signal handlers when the app is ready
        import crawl_log.signal_handlers  # noqa

