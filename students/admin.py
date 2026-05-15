from django.contrib import admin

from .models import Parent, Student


@admin.register(Parent)
class ParentAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'other_name', 'last_name', 'email', 'phone_number')
    search_fields = ('first_name', 'other_name', 'last_name', 'email', 'phone_number')


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'other_name', 'last_name', 'parent', 'approval_status', 'email', 'phone_number')
    list_filter = ('approval_status', 'school_name')
    list_editable = ('approval_status',)
    search_fields = (
        'first_name',
        'other_name',
        'last_name',
        'email',
        'phone_number',
        'parent__first_name',
        'parent__other_name',
        'parent__last_name',
    )
    actions = ('approve_children',)

    @admin.action(description='Approve selected children')
    def approve_children(self, request, queryset):
        queryset.update(approval_status=Student.STATUS_APPROVED)

# Register your models here.
