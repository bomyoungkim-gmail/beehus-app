from django.db import models

# Create your models here.
class CrawlLog(models.Model):
    url = models.URLField()
    status_code = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.url} - {self.status_code} at {self.timestamp}"