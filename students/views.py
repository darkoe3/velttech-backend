from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from .models import Parent, Student
from .serializers import ParentSerializer, StudentSerializer
from users.permissions import IsAdminOrReadOnly


class ParentViewSet(viewsets.ModelViewSet):
    queryset = Parent.objects.all()
    serializer_class = ParentSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return super().get_queryset()
        if user.role == 'parent':
            return super().get_queryset().filter(user=user)
        return super().get_queryset().none()


class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.select_related('parent').prefetch_related('enrollments__course')
    serializer_class = StudentSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if user.role == 'admin':
            search = self.request.query_params.get('search')
            approval_status = self.request.query_params.get('approval_status')
            parent = self.request.query_params.get('parent')
            school = self.request.query_params.get('school')
            if search:
                queryset = queryset.filter(
                    Q(first_name__icontains=search)
                    | Q(other_name__icontains=search)
                    | Q(last_name__icontains=search)
                    | Q(email__icontains=search)
                    | Q(parent__email__icontains=search)
                )
            if approval_status:
                queryset = queryset.filter(approval_status=approval_status)
            if parent:
                queryset = queryset.filter(parent_id=parent)
            if school:
                queryset = queryset.filter(school_name__icontains=school)
            return queryset
        if user.role == 'parent':
            return queryset.filter(parent__user=user)
        if user.role == 'student':
            return queryset.filter(user=user)
        return queryset.none()
