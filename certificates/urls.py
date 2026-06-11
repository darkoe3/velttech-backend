from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import CertificateViewSet, CertificateEligibilityListView

router = DefaultRouter()
router.register(r'certificates', CertificateViewSet, basename='certificate')

urlpatterns = [
    path('', include(router.urls)),
    path('certificates/eligible/', CertificateEligibilityListView.as_view(), name='certificate-eligible'),
]
