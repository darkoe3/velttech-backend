from django.core.management.base import BaseCommand
from django.db import transaction

from enrollments.models import Assignment, AssignmentSubmission, AssessmentResult, Enrollment


class Command(BaseCommand):
    help = 'Create missing AssessmentResult rows for historical active/completed enrollments.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would be created without writing rows.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        counters = {
            'examined': 0,
            'created': 0,
            'existing': 0,
            'skipped': 0,
            'errors': 0,
            'objective_quiz_available_for_import': 0,
        }

        enrollments = Enrollment.objects.select_related(
            'student',
            'course',
            'instructor',
        ).filter(
            status__in=[Enrollment.STATUS_ACTIVE, Enrollment.STATUS_COMPLETED],
        ).order_by('id')

        for enrollment in enrollments:
            counters['examined'] += 1
            try:
                if AssessmentResult.objects.filter(enrollment=enrollment).exists():
                    counters['existing'] += 1
                    continue

                quiz_submissions = AssignmentSubmission.objects.filter(
                    student=enrollment.student,
                    assignment__course=enrollment.course,
                    assignment__submission_type=Assignment.ASSESSMENT_QUIZ,
                    status=AssignmentSubmission.STATUS_GRADED,
                    score__isnull=False,
                )
                if quiz_submissions.count() == 1:
                    counters['objective_quiz_available_for_import'] += 1

                if dry_run:
                    counters['skipped'] += 1
                    continue

                with transaction.atomic():
                    _result, created = AssessmentResult.objects.get_or_create(enrollment=enrollment)
                if created:
                    counters['created'] += 1
                else:
                    counters['existing'] += 1
            except Exception as exc:
                counters['errors'] += 1
                self.stderr.write(
                    f'Enrollment {enrollment.id}: {exc.__class__.__name__}: {exc}'
                )

        prefix = 'Dry run complete.' if dry_run else 'Reconciliation complete.'
        self.stdout.write(prefix)
        self.stdout.write(f"Enrollments examined: {counters['examined']}")
        self.stdout.write(f"AssessmentResults created: {counters['created']}")
        self.stdout.write(f"Already existing: {counters['existing']}")
        self.stdout.write(f"Skipped: {counters['skipped']}")
        self.stdout.write(f"Errors: {counters['errors']}")
        self.stdout.write(
            'Objective quiz submissions available for explicit import: '
            f"{counters['objective_quiz_available_for_import']}"
        )
