from django.db import models
from django.utils import timezone


class Payment(models.Model):
    METHOD_CASH = 'cash'
    METHOD_MOBILE_MONEY = 'mobile_money'
    METHOD_CARD = 'card'
    METHOD_BANK_TRANSFER = 'bank_transfer'

    METHOD_CHOICES = [
        (METHOD_CASH, 'Cash'),
        (METHOD_MOBILE_MONEY, 'Mobile Money'),
        (METHOD_CARD, 'Card'),
        (METHOD_BANK_TRANSFER, 'Bank Transfer'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_REFUNDED = 'refunded'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_REFUNDED, 'Refunded'),
    ]

    enrollment = models.ForeignKey(
        'enrollments.Enrollment',
        on_delete=models.CASCADE,
        related_name='payments',
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    transaction_reference = models.CharField(
        max_length=120,
        unique=True,
        blank=True,
        null=True,
    )
    month = models.PositiveSmallIntegerField(blank=True, null=True)
    year = models.PositiveSmallIntegerField(blank=True, null=True)
    payment_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True)
    receipt_number = models.CharField(max_length=20, unique=True, blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.enrollment} - {self.amount}'

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            receipt_year = self.year or (
                self.payment_date.year if self.payment_date else timezone.localdate().year
            )
            prefix = f'VTA-{receipt_year}-'
            last_payment = Payment.objects.filter(
                receipt_number__startswith=prefix,
            ).order_by('-receipt_number').first()
            last_sequence = int(last_payment.receipt_number.split('-')[-1]) if last_payment else 0
            self.receipt_number = f'{prefix}{last_sequence + 1:06d}'
        super().save(*args, **kwargs)

# Create your models here.
