import hashlib
import hmac
from decimal import Decimal
from secrets import token_hex

import requests
from django.conf import settings
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Payment
from .serializers import PaymentSerializer
from users.permissions import IsAdminOrReadOnly


PAYSTACK_BASE_URL = 'https://api.paystack.co/transaction'
PAYSTACK_CURRENCY = 'GHS'


def user_can_access_payment(user, payment):
    if getattr(user, 'approval_status', 'approved') != 'approved':
        return False
    if user.role == 'admin':
        return True
    if user.role == 'parent':
        return payment.enrollment.student.parent and payment.enrollment.student.parent.user_id == user.id
    if user.role == 'student':
        return payment.enrollment.student.user_id == user.id
    return False


def payment_email(payment):
    parent = payment.enrollment.student.parent
    if parent and parent.email:
        return parent.email
    if parent and parent.user and parent.user.email:
        return parent.user.email
    student_user = payment.enrollment.student.user
    if student_user and student_user.email:
        return student_user.email
    return ''


def build_transaction_reference(payment):
    today = timezone.localdate().strftime('%Y%m%d')
    return f'VTA-PAY-{today}-{payment.id}-{token_hex(4).upper()}'


def paystack_headers():
    if not settings.PAYSTACK_SECRET_KEY:
        raise ValidationError({'detail': 'Paystack secret key is not configured.'})
    return {
        'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
        'Content-Type': 'application/json',
    }


def parse_paystack_json(response):
    try:
        return response.json()
    except ValueError:
        return {}


def expected_paystack_amount(payment):
    return int(payment.amount * Decimal('100'))


def paystack_charge_matches_payment(payment, paystack_data):
    metadata = paystack_data.get('metadata') or {}
    metadata_payment_id = metadata.get('payment_id')
    if metadata_payment_id and str(metadata_payment_id) != str(payment.id):
        return False
    return (
        paystack_data.get('reference') == payment.transaction_reference
        and paystack_data.get('currency') == PAYSTACK_CURRENCY
        and int(paystack_data.get('amount') or 0) == expected_paystack_amount(payment)
    )


def mark_payment_paid(payment):
    payment.status = Payment.STATUS_PAID
    payment.payment_method = Payment.METHOD_PAYSTACK
    payment.paid_at = payment.paid_at or timezone.now()
    payment.payment_date = payment.payment_date or timezone.localdate()
    payment.save(update_fields=[
        'status',
        'payment_method',
        'paid_at',
        'payment_date',
        'receipt_number',
        'updated_at',
    ])
    return payment


def mark_payment_failed(payment):
    payment.status = Payment.STATUS_FAILED
    payment.save(update_fields=['status', 'updated_at'])
    return payment


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.select_related(
        'enrollment',
        'enrollment__student',
        'enrollment__student__parent',
        'enrollment__course',
    )
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if user.role == 'admin':
            return queryset
        if user.role == 'parent':
            return queryset.filter(enrollment__student__parent__user=user)
        if user.role == 'student':
            return queryset.filter(enrollment__student__user=user)
        return queryset.none()

    def perform_create(self, serializer):
        payment = serializer.save()
        from users.views import log_admin_action
        if self.request.user.role == 'admin':
            log_admin_action(self.request, 'payment_created', f'Created payment {payment.receipt_number}.')

    def perform_update(self, serializer):
        payment = serializer.save()
        from users.views import log_admin_action
        if self.request.user.role == 'admin':
            log_admin_action(self.request, 'payment_updated', f'Updated payment {payment.receipt_number}.')


class PaystackInitializePaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        payment_id = request.data.get('payment_id')
        if not payment_id:
            raise ValidationError({'payment_id': 'This field is required.'})

        payment = Payment.objects.select_related(
            'enrollment',
            'enrollment__student',
            'enrollment__student__parent',
            'enrollment__student__parent__user',
            'enrollment__student__user',
            'enrollment__course',
        ).filter(pk=payment_id).first()
        if not payment:
            raise ValidationError({'payment_id': 'Payment not found.'})
        if not user_can_access_payment(request.user, payment):
            raise PermissionDenied('You do not have access to this payment.')
        if payment.status == Payment.STATUS_PAID:
            raise ValidationError({'detail': 'This payment has already been paid.'})
        if payment.amount <= 0:
            raise ValidationError({'detail': 'Online payment requires a positive invoice amount.'})

        email = payment_email(payment)
        if not email:
            raise ValidationError({'detail': 'A parent or student email is required before online payment.'})

        payment.transaction_reference = build_transaction_reference(payment)
        payment.status = Payment.STATUS_PENDING
        payment.save(update_fields=['transaction_reference', 'status', 'updated_at'])

        callback_url = f'{settings.FRONTEND_URL.rstrip("/")}/payments/verify?reference={payment.transaction_reference}'
        payload = {
            'email': email,
            'amount': int(payment.amount * Decimal('100')),
            'currency': PAYSTACK_CURRENCY,
            'reference': payment.transaction_reference,
            'callback_url': callback_url,
            'metadata': {
                'payment_id': payment.id,
                'student_name': str(payment.enrollment.student),
                'course_name': payment.enrollment.course.title,
                'parent_email': email,
            },
        }
        response = requests.post(
            f'{PAYSTACK_BASE_URL}/initialize',
            json=payload,
            headers=paystack_headers(),
            timeout=20,
        )
        body = parse_paystack_json(response)
        if not response.ok or not body.get('status'):
            mark_payment_failed(payment)
            return Response(
                {'detail': body.get('message', 'Unable to initialize Paystack payment.')},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        data = body.get('data', {})
        return Response({
            'authorization_url': data.get('authorization_url'),
            'access_code': data.get('access_code'),
            'reference': data.get('reference') or payment.transaction_reference,
        })


class PaystackVerifyPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        reference = request.query_params.get('reference')
        if not reference:
            raise ValidationError({'reference': 'This query parameter is required.'})

        payment = Payment.objects.select_related(
            'enrollment',
            'enrollment__student',
            'enrollment__student__parent',
            'enrollment__course',
        ).filter(transaction_reference=reference).first()
        if not payment:
            raise ValidationError({'reference': 'Payment reference not found.'})
        if not user_can_access_payment(request.user, payment):
            raise PermissionDenied('You do not have access to this payment.')

        response = requests.get(
            f'{PAYSTACK_BASE_URL}/verify/{reference}',
            headers=paystack_headers(),
            timeout=20,
        )
        body = parse_paystack_json(response)
        paystack_data = body.get('data', {})
        if (
            response.ok
            and body.get('status')
            and paystack_data.get('status') == 'success'
            and paystack_charge_matches_payment(payment, paystack_data)
        ):
            mark_payment_paid(payment)
        elif response.ok and paystack_data.get('status') in ['failed', 'abandoned']:
            mark_payment_failed(payment)

        return Response({
            'paystack_status': paystack_data.get('status') or 'unknown',
            'payment': PaymentSerializer(payment).data,
            'receipt': {
                'receipt_number': payment.receipt_number,
                'transaction_reference': payment.transaction_reference,
                'paid_at': payment.paid_at,
                'status': payment.status,
            },
        })


class PaystackWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        signature = request.headers.get('x-paystack-signature', '')
        expected_signature = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode(),
            request.body,
            hashlib.sha512,
        ).hexdigest()
        if not settings.PAYSTACK_SECRET_KEY or not hmac.compare_digest(signature, expected_signature):
            return Response({'detail': 'Invalid signature.'}, status=status.HTTP_400_BAD_REQUEST)

        event = request.data.get('event')
        data = request.data.get('data') or {}
        reference = data.get('reference')
        if event == 'charge.success' and reference:
            payment = Payment.objects.select_related(
                'enrollment',
                'enrollment__student',
                'enrollment__student__parent',
                'enrollment__course',
            ).filter(transaction_reference=reference).first()
            if payment and paystack_charge_matches_payment(payment, data):
                mark_payment_paid(payment)

        return Response({'detail': 'ok'})
