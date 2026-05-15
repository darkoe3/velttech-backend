from rest_framework import serializers

from .models import Parent, Student


class ParentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Parent
        fields = [
            'id',
            'user',
            'first_name',
            'other_name',
            'last_name',
            'email',
            'phone_number',
            'address',
            'occupation',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['user', 'created_at', 'updated_at']


class StudentSerializer(serializers.ModelSerializer):
    parent_detail = ParentSerializer(source='parent', read_only=True)

    class Meta:
        model = Student
        fields = [
            'id',
            'parent',
            'user',
            'parent_detail',
            'first_name',
            'other_name',
            'last_name',
            'email',
            'phone_number',
            'date_of_birth',
            'school_name',
            'emergency_contact',
            'approval_status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['user', 'created_at', 'updated_at']


class MyChildSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            'id',
            'full_name',
            'first_name',
            'other_name',
            'last_name',
            'date_of_birth',
            'school_name',
            'phone_number',
            'emergency_contact',
            'approval_status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['approval_status', 'created_at', 'updated_at']

    def get_full_name(self, obj):
        return str(obj)
