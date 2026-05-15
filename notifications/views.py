from django.db import models
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Notification
from .serializers import NotificationSerializer
from users.permissions import IsAdminOrReadOnly


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if user.role == 'admin':
            return queryset
        audience_map = {
            'parent': Notification.AUDIENCE_PARENTS,
            'student': Notification.AUDIENCE_STUDENTS,
            'instructor': Notification.AUDIENCE_INSTRUCTORS,
        }
        return queryset.filter(
            is_active=True,
            audience__in=[Notification.AUDIENCE_ALL, audience_map.get(user.role)],
        ).filter(models.Q(recipient__isnull=True) | models.Q(recipient=user))

    def perform_create(self, serializer):
        notification = serializer.save()
        from users.views import log_admin_action
        if self.request.user.role == 'admin':
            log_admin_action(self.request, 'notification_created', f'Created notification {notification.title}.')
