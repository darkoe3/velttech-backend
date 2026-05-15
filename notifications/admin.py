from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'audience', 'is_active', 'created_at')
    list_filter = ('audience', 'is_active')
    search_fields = ('title', 'message')
