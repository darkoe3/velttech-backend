from decimal import Decimal

from django.core import mail
from django.test import TestCase, override_settings

from courses.models import Course
from enrollments.models import Enrollment
from students.models import Parent, Student
from users.models import ActivityLog

from .models import Payment


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='Velttech <noreply@velttech.org>',
    FRONTEND_URL='https://velttech.org',
)
class PaymentNotificationTests(TestCase):
    def setUp(self):
        self.parent = Parent.objects.create(
            first_name='Joyce',
            last_name='Darko',
            email='joyce@example.com',
            phone_number='0555106820',
        )
        self.student = Student.objects.create(
            parent=self.parent,
            first_name='Michaella',
            last_name='Darko',
            email='michaella@example.com',
        )
        self.course = Course.objects.create(
            title='Coding & Robotics for Kids & Teens',
            description='Kids coding',
            duration_months=3,
            monthly_fee=Decimal('250.00'),
        )
        self.enrollment = Enrollment.objects.create(
            student=self.student,
            course=self.course,
        )

    def test_invoice_email_is_sent_once_when_payment_is_created(self):
        with self.captureOnCommitCallbacks(execute=True):
            payment = Payment.objects.create(
                enrollment=self.enrollment,
                amount=Decimal('250.00'),
                month=5,
                year=2026,
            )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'New Payment Notice - Velttech Academy')
        self.assertIn('Dear Joyce Darko', mail.outbox[0].body)
        self.assertIn('Payment Period:\nMay 2026', mail.outbox[0].body)
        self.assertIn('Amount Due:\nGH₵250.00', mail.outbox[0].body)

        payment.refresh_from_db()
        self.assertIsNotNone(payment.invoice_email_sent_at)
        self.assertTrue(ActivityLog.objects.filter(action='payment_created').exists())
        self.assertTrue(ActivityLog.objects.filter(action='invoice_email_sent').exists())

        with self.captureOnCommitCallbacks(execute=True):
            payment.notes = 'Updated without creating a new invoice'
            payment.save(update_fields=['notes', 'updated_at'])

        self.assertEqual(len(mail.outbox), 1)

    def test_confirmation_email_is_sent_once_when_payment_becomes_paid(self):
        with self.captureOnCommitCallbacks(execute=True):
            payment = Payment.objects.create(
                enrollment=self.enrollment,
                amount=Decimal('250.00'),
                month=5,
                year=2026,
                transaction_reference='VTA-PAY-TEST',
            )

        with self.captureOnCommitCallbacks(execute=True):
            payment.status = Payment.STATUS_PAID
            payment.save(update_fields=['status', 'updated_at'])

        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[1].subject, 'Payment Confirmation - Velttech Academy')
        self.assertIn('Amount Paid:\nGH₵250.00', mail.outbox[1].body)
        self.assertIn(f'Receipt Number:\n{payment.receipt_number}', mail.outbox[1].body)
        self.assertIn('Transaction Reference:\nVTA-PAY-TEST', mail.outbox[1].body)

        payment.refresh_from_db()
        self.assertIsNotNone(payment.confirmation_email_sent_at)
        self.assertTrue(ActivityLog.objects.filter(action='payment_confirmation_email_sent').exists())

        with self.captureOnCommitCallbacks(execute=True):
            payment.notes = 'No duplicate confirmation'
            payment.save(update_fields=['notes', 'updated_at'])

        self.assertEqual(len(mail.outbox), 2)
