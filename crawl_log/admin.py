from django.contrib import admin
from crawl_log.models import CrawlLog

# Register your models here.
@admin.register(CrawlLog)
class CrawlLogAdmin(admin.ModelAdmin):
    list_display = ('url', 'status_code', 'timestamp')
    list_filter = ('status_code', 'timestamp')
    search_fields = ('url',)