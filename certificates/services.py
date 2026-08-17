from certificates.models import Certificate
from enrollments.models import AssessmentResult, Enrollment
from payments.models import Payment


def check_combined_result_certificate_eligibility(enrollment):
    result = getattr(enrollment, 'assessment_result', None)
    existing_certificate = Certificate.objects.filter(enrollment=enrollment).first()
    certificate_exists = bool(existing_certificate and existing_certificate.is_active())
    certificate_revoked = bool(
        existing_certificate
        and existing_certificate.status == Certificate.STATUS_REVOKED
    )
    payments_settled = not Payment.objects.filter(
        enrollment=enrollment,
        status=Payment.STATUS_PENDING,
    ).exists()
    enrollment_completed = enrollment.status == Enrollment.STATUS_COMPLETED
    student_approved = enrollment.student.approval_status == enrollment.student.STATUS_APPROVED
    missing_components = []
    if result:
        if result.practical_score is None:
            missing_components.append('Practical score missing.')
        if result.final_project_score is None:
            missing_components.append('Final Project score missing.')
        if result.objective_quiz_score is None:
            missing_components.append('Objective Quiz score missing.')
    assessment_complete = bool(result and result.is_complete)
    result_approved = bool(result and result.is_approved)
    pass_mark = enrollment.course.certificate_pass_mark
    percentage = result.percentage if result else None
    meets_pass_mark = bool(result and result.percentage >= pass_mark)

    checks = [
        (enrollment_completed, 'Enrollment is not completed.'),
        (student_approved, 'Student is not approved.'),
        (payments_settled, 'Payments are not settled.'),
        (bool(result), 'Assessment result not created.'),
        (not missing_components, missing_components),
        (result_approved, 'Combined assessment result is not approved.'),
        (meets_pass_mark, 'Combined assessment result is below the course pass mark.'),
        (not certificate_exists, 'Certificate already issued.'),
        (not certificate_revoked, 'Certificate revoked — use Reissue.'),
    ]
    reasons = []
    for passed, reason in checks:
        if passed:
            continue
        if isinstance(reason, list):
            reasons.extend(reason)
        else:
            reasons.append(reason)

    return {
        'eligible': not reasons,
        'reasons': reasons,
        'assessment_complete': assessment_complete,
        'missing_components': missing_components,
        'result_approved': result_approved,
        'percentage': percentage,
        'pass_mark': pass_mark,
        'payments_settled': payments_settled,
        'enrollment_completed': enrollment_completed,
        'certificate_exists': certificate_exists,
        'certificate_revoked': certificate_revoked,
        'certificate_id': existing_certificate.id if existing_certificate else None,
        'certificate_number': existing_certificate.certificate_number if existing_certificate else '',
        'certificate_status': existing_certificate.status if existing_certificate else '',
        'recommended_action': 'reissue' if certificate_revoked else '',
    }


def ensure_assessment_result(enrollment):
    result, _created = AssessmentResult.objects.get_or_create(enrollment=enrollment)
    return result
