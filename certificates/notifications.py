import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from notifications.models import Notification
from students.models import Student
from users.models import ActivityLog

from .models import Certificate
from .serializers import CERTIFICATE_PROGRAMME_NAME


logger = logging.getLogger(__name__)

SUPPORT_EMAIL = 'info@velttech.org'
SUPPORT_PHONE = '+233 55 510 6820'


def _student_name(student):
    names = [student.first_name, student.other_name, student.last_name]
    return ' '.join(name for name in names if name)


def _user_name(user):
    names = [getattr(user, 'first_name', ''), getattr(user, 'last_name', '')]
    return ' '.join(name for name in names if name).strip() or getattr(user, 'email', '')


def _parent_name(parent):
    names = [parent.first_name, parent.other_name, parent.last_name]
    return ' '.join(name for name in names if name)


def _completion_date(certificate):
    if certificate.completion_date:
        return certificate.completion_date.strftime('%d %B %Y')
    if certificate.issue_date:
        return certificate.issue_date.strftime('%d %B %Y')
    return 'Not recorded'


def _notification_recipient(certificate):
    student = certificate.student
    if student.learner_type == Student.LEARNER_CHILD and student.parent:
        parent = student.parent
        recipient = parent.user
        email = parent.email or (parent.user.email if parent.user else '')
        return {
            'kind': 'parent',
            'recipient': recipient,
            'email': email,
            'name': _parent_name(parent),
        }

    user = student.user
    return {
        'kind': 'student',
        'recipient': user,
        'email': (user.email if user else '') or student.email or '',
        'name': _user_name(user) if user else _student_name(student),
    }


def _log_certificate_notification(action, description):
    try:
        ActivityLog.objects.create(action=action, description=description, role='system')
    except Exception:
        logger.exception('Could not log certificate notification event: %s', action)


def _parent_email_body(certificate, recipient_info):
    student_name = _student_name(certificate.student)
    login_url = f'{settings.FRONTEND_URL.rstrip("/")}/login'
    return (
        f'Dear {recipient_info["name"]},\n\n'
        f'Congratulations! {student_name} has completed {CERTIFICATE_PROGRAMME_NAME}.\n\n'
        f'Student/Child Name:\n{student_name}\n\n'
        f'Programme:\n{CERTIFICATE_PROGRAMME_NAME}\n\n'
        f'Specialization:\n{certificate.course.title}\n\n'
        f'Completion Date:\n{_completion_date(certificate)}\n\n'
        f'Certificate Number:\n{certificate.certificate_number}\n\n'
        'A certificate has been issued and is now available in your Velttech Academy parent portal.\n\n'
        'Please log in to view and download the certificate:\n'
        f'{login_url}\n\n'
        'For support, contact:\n'
        f'{SUPPORT_EMAIL}\n'
        f'{SUPPORT_PHONE}\n\n'
        'Velttech Academy\n'
    )


def _student_email_body(certificate, recipient_info):
    login_url = f'{settings.FRONTEND_URL.rstrip("/")}/login'
    return (
        f'Dear {recipient_info["name"]},\n\n'
        f'Your Velttech Academy certificate has been issued.\n\n'
        f'Learner Name:\n{_student_name(certificate.student)}\n\n'
        f'Programme:\n{CERTIFICATE_PROGRAMME_NAME}\n\n'
        f'Specialization:\n{certificate.course.title}\n\n'
        f'Completion Date:\n{_completion_date(certificate)}\n\n'
        f'Certificate Number:\n{certificate.certificate_number}\n\n'
        'Your certificate has been issued and is now available in your Velttech Academy student dashboard.\n\n'
        'Please log in to view and download the certificate:\n'
        f'{login_url}\n\n'
        'For support, contact:\n'
        f'{SUPPORT_EMAIL}\n'
        f'{SUPPORT_PHONE}\n\n'
        'Velttech Academy\n'
    )


def send_certificate_issued_notification(certificate, force=False):
    certificate = Certificate.objects.select_related(
        'student',
        'student__parent',
        'student__parent__user',
        'student__user',
        'course',
    ).get(pk=certificate.pk)

    if not certificate.is_active():
        return False
    if certificate.certificate_email_sent_at and not force:
        return False

    recipient_info = _notification_recipient(certificate)
    student_name = _student_name(certificate.student)
    if recipient_info['kind'] == 'parent':
        title = 'Certificate Issued'
        message = f'A certificate has been issued for {student_name}.'
        audience = Notification.AUDIENCE_PARENTS
        subject = f'Congratulations! {student_name} has completed {CERTIFICATE_PROGRAMME_NAME}'
        body = _parent_email_body(certificate, recipient_info)
    else:
        title = 'Certificate Ready'
        message = f'Your certificate for {CERTIFICATE_PROGRAMME_NAME} is now available.'
        audience = Notification.AUDIENCE_STUDENTS
        subject = 'Your Velttech Academy Certificate Is Ready'
        body = _student_email_body(certificate, recipient_info)

    if recipient_info['recipient']:
        Notification.objects.create(
            title=title,
            message=message,
            audience=audience,
            recipient=recipient_info['recipient'],
        )
    else:
        _log_certificate_notification(
            'certificate_dashboard_notification_missing_recipient',
            f'Dashboard notification not created for {certificate.certificate_number}: no recipient user found.',
        )

    if not recipient_info['email']:
        _log_certificate_notification(
            'certificate_email_missing_recipient',
            f'Certificate email not sent for {certificate.certificate_number}: no recipient email found.',
        )
        return False

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_info['email']],
            fail_silently=False,
        )
    except Exception:
        logger.exception('Could not send certificate issued email for certificate %s.', certificate.pk)
        _log_certificate_notification(
            'certificate_email_failed',
            f'Certificate email failed for {certificate.certificate_number}.',
        )
        return False

    Certificate.objects.filter(pk=certificate.pk).update(certificate_email_sent_at=timezone.now())
    _log_certificate_notification(
        'certificate_email_sent',
        f'Certificate email sent for {certificate.certificate_number} to {recipient_info["email"]}.',
    )
    return True
