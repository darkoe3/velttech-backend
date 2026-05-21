from django.contrib import admin

from .models import Course


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'duration_months', 'monthly_fee', 'fee', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('title', 'description')
