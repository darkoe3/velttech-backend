from rest_framework import serializers

from enrollments.serializers import EnrollmentSerializer

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    enrollment_detail = EnrollmentSerializer(source='enrollment', read_only=True)
    student_name = serializers.SerializerMethodField()
    parent_name = serializers.SerializerMethodField()
    parent_email = serializers.SerializerMethodField()
    course_title = serializers.CharField(source='enrollment.course.title', read_only=True)
    reference = serializers.CharField(source='transaction_reference', read_only=True)
    balance = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()

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
            'payment_date',
            'balance',
            'receipt_number',
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
        return max(obj.enrollment.course.monthly_fee - obj.amount, 0)

    def get_payment_status(self, obj):
        expected = obj.enrollment.course.monthly_fee
        if obj.amount >= expected:
            return 'paid'
        if obj.amount > 0:
            return 'partial'
        return 'unpaid'


class PaymentHistorySerializer(serializers.Serializer):
    id = serializers.IntegerField(allow_null=True)
    student_id = serializers.IntegerField()
    student_name = serializers.CharField()
    parent_name = serializers.CharField(allow_blank=True)
    parent_phone = serializers.CharField(allow_blank=True)
    course_title = serializers.CharField()
    month = serializers.IntegerField()
    year = serializers.IntegerField()
    expected_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = serializers.DecimalField(max_digits=10, decimal_places=2)
    balance = serializers.DecimalField(max_digits=10, decimal_places=2)
    payment_status = serializers.CharField()
    payment_method = serializers.CharField(allow_blank=True)
    reference = serializers.CharField(allow_blank=True)
    payment_date = serializers.DateField(allow_null=True)
    paid_at = serializers.DateTimeField(allow_null=True)
    receipt_number = serializers.CharField(allow_blank=True)
