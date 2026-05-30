from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Payment
from .notifications import (
    log_payment_event,
    send_invoice_email,
    send_payment_confirmation_email,
)


@receiver(pre_save, sender=Payment)
def remember_previous_payment_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_status = None
        return
    instance._previous_status = sender.objects.filter(pk=instance.pk).values_list('status', flat=True).first()


@receiver(post_save, sender=Payment)
def notify_payment_changes(sender, instance, created, **kwargs):
    if created:
        log_payment_event(
            'payment_created',
            f'Payment created for {instance.enrollment.student} in {instance.enrollment.course}: {instance.receipt_number}.',
        )
        transaction.on_commit(lambda: send_invoice_email(instance))

    previous_status = getattr(instance, '_previous_status', None)
    became_paid = instance.status == Payment.STATUS_PAID and previous_status != Payment.STATUS_PAID
    if became_paid:
        transaction.on_commit(lambda: send_payment_confirmation_email(instance))
