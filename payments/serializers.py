from rest_framework import serializers

from enrollments.serializers import EnrollmentSerializer

from .models import Payment


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


def course_fee(course):
    fee = getattr(course, 'fee', None)
    if fee:
        return fee
    return course.monthly_fee


class PaymentSerializer(serializers.ModelSerializer):
    enrollment_detail = EnrollmentSerializer(source='enrollment', read_only=True)
    student_name = serializers.SerializerMethodField()
    parent_name = serializers.SerializerMethodField()
    parent_email = serializers.SerializerMethodField()
    course_title = serializers.CharField(source='enrollment.course.title', read_only=True)
    reference = serializers.CharField(source='transaction_reference', read_only=True)
    balance = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    payment_period_display = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            'id',
            'enrollment',
            'enrollment_detail',
            'amount',
            'student_name',
            'parent_name',
            'parent_email',
            'course_title',
            'payment_method',
            'status',
            'payment_status',
            'transaction_reference',
            'reference',
            'month',
            'year',
            'payment_period',
            'payment_period_display',
            'payment_date',
            'balance',
            'receipt_number',
            'invoice_email_sent_at',
            'confirmation_email_sent_at',
            'notes',
            'paid_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_student_name(self, obj):
        return str(obj.enrollment.student)

    def get_parent_name(self, obj):
        return str(obj.enrollment.student.parent) if obj.enrollment.student.parent else ''

    def get_parent_email(self, obj):
        parent = obj.enrollment.student.parent
        return parent.email if parent else ''

    def get_balance(self, obj):
        paid_amount = obj.amount if obj.status == Payment.STATUS_PAID else 0
        return max(course_fee(obj.enrollment.course) - paid_amount, 0)

    def get_payment_status(self, obj):
        if obj.status in [Payment.STATUS_PENDING, Payment.STATUS_FAILED]:
            return obj.status
        expected = course_fee(obj.enrollment.course)
        if obj.amount >= expected:
            return 'paid'
        if obj.amount > 0:
            return 'partial'
        return 'unpaid'

    def get_payment_period_display(self, obj):
        if obj.payment_period:
            return obj.payment_period
        if obj.month and obj.year and 1 <= obj.month <= 12:
            return f'{MONTH_NAMES[obj.month]} {obj.year}'
        if obj.year:
            return str(obj.year)
        return ''


class PaymentHistorySerializer(serializers.Serializer):
    id = serializers.IntegerField(allow_null=True)
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    parent_name = serializers.CharField(allow_blank=True)
    parent_phone = serializers.CharField(allow_blank=True)
    course_title = serializers.CharField()
    month = serializers.IntegerField()
    year = serializers.IntegerField()
    payment_period = serializers.CharField(allow_blank=True)
    expected_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = serializers.DecimalField(max_digits=10, decimal_places=2)
    balance = serializers.DecimalField(max_digits=10, decimal_places=2)
    payment_status = serializers.CharField()
    payment_method = serializers.CharField(allow_blank=True)
    reference = serializers.CharField(allow_blank=True)
    payment_date = serializers.DateField(allow_null=True)
    paid_at = serializers.DateTimeField(allow_null=True)
    receipt_number = serializers.CharField(allow_blank=True)
