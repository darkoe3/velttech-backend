from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'enrollment',
        'amount',
        'payment_method',
        'status',
        'transaction_reference',
        'month',
        'year',
        'payment_date',
        'paid_at',
    )
    list_filter = ('payment_method', 'status', 'month', 'year')
    search_fields = (
        'transaction_reference',
        'enrollment__student__first_name',
        'enrollment__student__last_name',
        'enrollment__course__title',
    )

# Register your models here.
