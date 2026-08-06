from rest_framework import serializers

from .models import Course


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = [
            'id',
            'title',
            'description',
            'duration_months',
            'monthly_fee',
            'fee',
            'certificate_pass_mark',
            'is_active',
        ]
