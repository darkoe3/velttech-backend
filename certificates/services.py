from certificates.models import Certificate
from enrollments.models import AssessmentResult, Enrollment
from payments.models import Payment


def check_combined_result_certificate_eligibility(enrollment):
    result = getattr(enrollment, 'assessment_result', None)
    certificate_exists = Certificate.objects.filter(
        enrollment=enrollment,
        status__in=[Certificate.STATUS_ACTIVE, Certificate.STATUS_LEGACY_ISSUED],
    ).exists()
    payments_settled = not Payment.objects.filter(
        enrollment=enrollment,
        status=Payment.STATUS_PENDING,
    ).exists()
    enrollment_completed = enrollment.status == Enrollment.STATUS_COMPLETED
    student_approved = enrollment.student.approval_status == enrollment.student.STATUS_APPROVED
    assessment_complete = bool(result and result.is_complete)
    result_approved = bool(result and result.is_approved)
    pass_mark = enrollment.course.certificate_pass_mark
    percentage = result.percentage if result else None
    meets_pass_mark = bool(result and result.percentage >= pass_mark)

    checks = [
        (enrollment_completed, 'Enrollment is not completed.'),
        (student_approved, 'Student is not approved.'),
        (payments_settled, 'Payments are not settled.'),
        (assessment_complete, 'Combined assessment result is incomplete.'),
        (result_approved, 'Combined assessment result is not approved.'),
        (meets_pass_mark, 'Combined assessment result is below the course pass mark.'),
        (not certificate_exists, 'A valid certificate already exists for this enrollment.'),
    ]
    reasons = [reason for passed, reason in checks if not passed]

    return {
        'eligible': not reasons,
        'reasons': reasons,
        'assessment_complete': assessment_complete,
        'result_approved': result_approved,
        'percentage': percentage,
        'pass_mark': pass_mark,
        'payments_settled': payments_settled,
        'enrollment_completed': enrollment_completed,
        'certificate_exists': certificate_exists,
    }


def ensure_assessment_result(enrollment):
    result, _created = AssessmentResult.objects.get_or_create(enrollment=enrollment)
    return result
