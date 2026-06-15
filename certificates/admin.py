from django.contrib import admin

from .models import Certificate, CertificateBranding


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = [
        'certificate_number',
        'student',
        'course',
        'status',
        'issued_at',
        'created_at',
    ]
    list_filter = ['status', 'issued_at', 'created_at', 'course']
    search_fields = ['certificate_number', 'student__first_name', 'student__last_name']
    readonly_fields = [
        'certificate_number',
        'verification_code',
        'issued_at',
        'created_at',
        'updated_at',
    ]
    fieldsets = (
        ('Certificate Information', {
            'fields': ('certificate_number', 'verification_code', 'status')
        }),
        ('Student & Course', {
            'fields': ('student', 'enrollment', 'course')
        }),
        ('Issuance Details', {
            'fields': ('issued_by', 'issued_at', 'completion_date')
        }),
        ('Revocation', {
            'fields': ('revoked_at', 'revoke_reason'),
            'classes': ('collapse',)
        }),
        ('File', {
            'fields': ('certificate_file',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        if not change:  # New object
            obj.issued_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(CertificateBranding)
class CertificateBrandingAdmin(admin.ModelAdmin):
    fields = ('academy_logo', 'director_signature', 'updated_at')
    readonly_fields = ('updated_at',)

    def has_add_permission(self, request):
        return not CertificateBranding.objects.exists()
