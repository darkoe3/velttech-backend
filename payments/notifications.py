import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from users.models import ActivityLog

from .models import Payment


logger = logging.getLogger(__name__)

MONTH_NAMES = [
    '',
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
]


def log_payment_event(action, description):
    try:
        ActivityLog.objects.create(action=action, description=description, role='system')
    except Exception:
        logger.exception('Could not log payment event: %s', action)


def payment_period(payment):
    if payment.payment_period:
        return payment.payment_period
    payment_day = payment.payment_date or (
        payment.paid_at.date() if payment.paid_at else payment.created_at.date()
    )
    month = payment.month or payment_day.month
    year = payment.year or payment_day.year
    if month and year and 1 <= month <= 12:
        return f'{MONTH_NAMES[month]} {year}'
    return str(year) if year else ''


def parent_recipient(payment):
    parent = payment.enrollment.student.parent
    if not parent:
        return '', ''
    email = parent.email or (parent.user.email if parent.user else '')
    return str(parent), email


def money(value):
    return f'GH₵{value:,.2f}'


def send_invoice_email(payment):
    payment = Payment.objects.select_related(
        'enrollment',
        'enrollment__student',
        'enrollment__student__parent',
        'enrollment__student__parent__user',
        'enrollment__course',
    ).get(pk=payment.pk)
    if payment.invoice_email_sent_at:
        return False

    parent_name, email = parent_recipient(payment)
    if not email:
        log_payment_event(
            'invoice_email_missing_recipient',
            f'Invoice email not sent for payment {payment.pk}: no parent email found.',
        )
        return False

    try:
        send_mail(
            subject='New Payment Notice - Velttech Academy',
            message=(
                f'Dear {parent_name},\n\n'
                'A new payment has been added to your Velttech Academy account.\n\n'
                'Student:\n'
                f'{payment.enrollment.student}\n\n'
                'Programme:\n'
                f'{payment.enrollment.course.title}\n\n'
                'Payment Period:\n'
                f'{payment_period(payment)}\n\n'
                'Amount Due:\n'
                f'{money(payment.amount)}\n\n'
                'Status:\n'
                f'{payment.status.title()}\n\n'
                'Please log in to your parent portal to complete payment.\n\n'
                'Login:\n'
                f'{settings.FRONTEND_URL.rstrip("/")}/login\n\n'
                'Thank you.\n\n'
                'Velttech Academy\n'
                'info@velttech.org\n'
                '0555106820\n'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception:
        logger.exception('Could not send invoice email for payment %s.', payment.pk)
        log_payment_event(
            'invoice_email_failed',
            f'Invoice email failed for payment {payment.pk} ({payment.receipt_number}).',
        )
        return False

    Payment.objects.filter(pk=payment.pk, invoice_email_sent_at__isnull=True).update(
        invoice_email_sent_at=timezone.now(),
    )
    log_payment_event(
        'invoice_email_sent',
        f'Invoice email sent for payment {payment.pk} ({payment.receipt_number}) to {email}.',
    )
    return True


def send_payment_confirmation_email(payment):
    payment = Payment.objects.select_related(
        'enrollment',
        'enrollment__student',
        'enrollment__student__parent',
        'enrollment__student__parent__user',
        'enrollment__course',
    ).get(pk=payment.pk)
    if payment.confirmation_email_sent_at:
        return False

    parent_name, email = parent_recipient(payment)
    if not email:
        log_payment_event(
            'confirmation_email_missing_recipient',
            f'Payment confirmation email not sent for payment {payment.pk}: no parent email found.',
        )
        return False

    try:
        send_mail(
            subject='Payment Confirmation - Velttech Academy',
            message=(
                f'Dear {parent_name},\n\n'
                'Thank you for your payment to Velttech Academy.\n\n'
                'Student:\n'
                f'{payment.enrollment.student}\n\n'
                'Programme:\n'
                f'{payment.enrollment.course.title}\n\n'
                'Amount Paid:\n'
                f'{money(payment.amount)}\n\n'
                'Payment Period:\n'
                f'{payment_period(payment)}\n\n'
                'Receipt Number:\n'
                f'{payment.receipt_number}\n\n'
                'Transaction Reference:\n'
                f'{payment.transaction_reference or "Not provided"}\n\n'
                'You can view and print your receipt from your dashboard.\n\n'
                'Velttech Academy\n'
                'info@velttech.org\n'
                '0555106820\n'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception:
        logger.exception('Could not send payment confirmation email for payment %s.', payment.pk)
        log_payment_event(
            'confirmation_email_failed',
            f'Payment confirmation email failed for payment {payment.pk} ({payment.receipt_number}).',
        )
        return False

    Payment.objects.filter(pk=payment.pk, confirmation_email_sent_at__isnull=True).update(
        confirmation_email_sent_at=timezone.now(),
    )
    log_payment_event(
        'payment_confirmation_email_sent',
        f'Payment confirmation email sent for payment {payment.pk} ({payment.receipt_number}) to {email}.',
    )
    return True
