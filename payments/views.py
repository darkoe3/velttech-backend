from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Payment
from .serializers import PaymentSerializer
from users.permissions import IsAdminOrReadOnly


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
