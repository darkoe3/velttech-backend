from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'title', 'message', 'audience', 'recipient', 'created_at', 'is_active']
        read_only_fields = ['created_at']
