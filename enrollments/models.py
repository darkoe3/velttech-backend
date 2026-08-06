import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Enrollment(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_ACTIVE = 'active'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='enrollments',
    )
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='enrollments',
    )
    instructor = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        related_name='assigned_enrollments',
        blank=True,
        null=True,
        limit_choices_to={'role': 'instructor'},
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    enrolled_at = models.DateField(auto_now_add=True)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-enrolled_at']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'course'],
                name='unique_student_course_enrollment',
            ),
        ]

    def __str__(self):
        return f'{self.student} - {self.course}'


class Attendance(models.Model):
    STATUS_PRESENT = 'present'
    STATUS_ABSENT = 'absent'
    STATUS_LATE = 'late'
    STATUS_EXCUSED = 'excused'

    STATUS_CHOICES = [
        (STATUS_PRESENT, 'Present'),
        (STATUS_ABSENT, 'Absent'),
        (STATUS_LATE, 'Late'),
        (STATUS_EXCUSED, 'Excused'),
    ]

    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name='attendance_records',
    )
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    remarks = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        related_name='recorded_attendance',
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['enrollment', 'date'],
                name='unique_attendance_per_enrollment_date',
            ),
        ]

    def __str__(self):
        return f'{self.enrollment} - {self.date} ({self.status})'


class LessonNote(models.Model):
    instructor = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='lesson_notes',
    )
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='lesson_notes',
    )
    title = models.CharField(max_length=200)
    content = models.TextField()
    lesson_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-lesson_date', '-created_at']

    def __str__(self):
        return f'{self.course} - {self.title}'


class ProgressReport(models.Model):
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name='progress_reports',
    )
    progress_score = models.PositiveSmallIntegerField()
    strengths = models.TextField(blank=True)
    areas_for_improvement = models.TextField(blank=True)
    instructor_comment = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        related_name='created_progress_reports',
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.enrollment} - {self.progress_score}%'


class AssessmentResult(models.Model):
    STATUS_INCOMPLETE = 'incomplete'
    STATUS_READY_FOR_REVIEW = 'ready_for_review'
    STATUS_APPROVED = 'approved'
    STATUS_BELOW_PASS_MARK = 'below_pass_mark'
    STATUS_CERTIFICATE_ISSUED = 'certificate_issued'

    STATUS_CHOICES = [
        (STATUS_INCOMPLETE, 'Incomplete'),
        (STATUS_READY_FOR_REVIEW, 'Ready for review'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_BELOW_PASS_MARK, 'Below pass mark'),
        (STATUS_CERTIFICATE_ISSUED, 'Certificate issued'),
    ]

    enrollment = models.OneToOneField(
        Enrollment,
        on_delete=models.CASCADE,
        related_name='assessment_result',
    )
    practical_max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=40,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    practical_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal('0'))],
    )
    final_project_max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=40,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    final_project_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal('0'))],
    )
    objective_quiz_max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=20,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    objective_quiz_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal('0'))],
    )
    final_project_feedback = models.TextField(blank=True)
    overall_score = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    total_max_score = models.DecimalField(max_digits=6, decimal_places=2, default=100)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default=STATUS_INCOMPLETE,
    )
    is_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        related_name='approved_assessment_results',
        blank=True,
        null=True,
    )
    approved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-created_at']

    def __str__(self):
        return f'{self.enrollment} assessment result'

    @property
    def is_complete(self):
        return all(
            score is not None
            for score in [
                self.practical_score,
                self.final_project_score,
                self.objective_quiz_score,
            ]
        )

    @property
    def meets_pass_mark(self):
        return self.is_complete and self.percentage >= self.enrollment.course.certificate_pass_mark

    def clean(self):
        super().clean()
        score_pairs = [
            ('practical_score', 'practical_max_score', 'Practical score'),
            ('final_project_score', 'final_project_max_score', 'Final project score'),
            ('objective_quiz_score', 'objective_quiz_max_score', 'Objective quiz score'),
        ]
        for score_field, max_field, label in score_pairs:
            score = getattr(self, score_field)
            max_score = getattr(self, max_field)
            if score is not None and score > max_score:
                raise ValidationError({score_field: f'{label} cannot exceed its maximum score.'})

        if self.is_approved and not self.is_complete:
            raise ValidationError({'is_approved': 'Only complete assessment results can be approved.'})

    def recalculate(self):
        self.total_max_score = (
            self.practical_max_score
            + self.final_project_max_score
            + self.objective_quiz_max_score
        )
        self.overall_score = sum(
            score or Decimal('0')
            for score in [
                self.practical_score,
                self.final_project_score,
                self.objective_quiz_score,
            ]
        )
        self.percentage = Decimal('0.00')
        if self.total_max_score:
            self.percentage = (
                (self.overall_score / self.total_max_score) * Decimal('100')
            ).quantize(Decimal('0.01'))

        if not self.is_complete:
            self.status = self.STATUS_INCOMPLETE
        elif self.percentage < self.enrollment.course.certificate_pass_mark:
            self.status = self.STATUS_BELOW_PASS_MARK
        elif self.status == self.STATUS_CERTIFICATE_ISSUED and self.is_approved:
            self.status = self.STATUS_CERTIFICATE_ISSUED
        elif self.is_approved:
            self.status = self.STATUS_APPROVED
        else:
            self.status = self.STATUS_READY_FOR_REVIEW

    def approve(self, user):
        self.recalculate()
        if not self.is_complete:
            raise ValidationError('All score components are required before approval.')
        if self.percentage < self.enrollment.course.certificate_pass_mark:
            raise ValidationError('Assessment result is below the course certificate pass mark.')
        self.is_approved = True
        self.approved_by = user
        self.approved_at = timezone.now()
        self.recalculate()
        self.save()

    def import_objective_quiz_submission(self, submission):
        if self.status == self.STATUS_CERTIFICATE_ISSUED:
            raise ValidationError('Certified assessment results cannot be changed.')
        if self.is_approved:
            raise ValidationError('Approved assessment results cannot be changed by quiz import.')
        if submission.student_id != self.enrollment.student_id:
            raise ValidationError('Quiz submission does not belong to this learner.')
        if submission.assignment.course_id != self.enrollment.course_id:
            raise ValidationError('Quiz submission does not belong to this course.')
        if submission.assignment.submission_type != Assignment.ASSESSMENT_QUIZ:
            raise ValidationError('Only quiz assessment submissions can be imported.')
        if submission.status != AssignmentSubmission.STATUS_GRADED or submission.score is None:
            raise ValidationError('Only graded quiz submissions with a score can be imported.')

        source_max = Decimal(submission.max_score or submission.assignment.marks or 0)
        if source_max <= 0:
            raise ValidationError('Quiz submission maximum score must be greater than zero.')

        self.objective_quiz_score = (
            (Decimal(submission.score) / source_max) * self.objective_quiz_max_score
        ).quantize(Decimal('0.01'))
        self.save()
        return self

    def save(self, *args, **kwargs):
        self.recalculate()
        self.full_clean()
        super().save(*args, **kwargs)


class Assignment(models.Model):
    ASSESSMENT_QUIZ = 'quiz'
    ASSESSMENT_PRACTICAL = 'practical'

    SUBMISSION_TYPE_CHOICES = [
        (ASSESSMENT_QUIZ, 'Quiz assessment'),
        (ASSESSMENT_PRACTICAL, 'Practical assessment'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='assignments',
    )
    target_student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='targeted_assignments',
        blank=True,
        null=True,
    )
    instructor = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='assignments',
        limit_choices_to={'role': 'instructor'},
    )
    due_date = models.DateField()
    submission_type = models.CharField(
        max_length=20,
        choices=SUBMISSION_TYPE_CHOICES,
        default=ASSESSMENT_QUIZ,
    )
    marks = models.PositiveSmallIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    share_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_public = models.BooleanField(default=False)
    share_expires_at = models.DateTimeField(blank=True, null=True)
    max_guest_attempts = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        ordering = ['due_date', '-created_at']

    def __str__(self):
        return f'{self.course} - {self.title}'


class AssignmentQuestion(models.Model):
    ANSWER_A = 'A'
    ANSWER_B = 'B'
    ANSWER_C = 'C'
    ANSWER_D = 'D'

    ANSWER_CHOICES = [
        (ANSWER_A, 'Option A'),
        (ANSWER_B, 'Option B'),
        (ANSWER_C, 'Option C'),
        (ANSWER_D, 'Option D'),
    ]

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='questions',
    )
    question_text = models.TextField()
    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255)
    option_d = models.CharField(max_length=255)
    correct_answer = models.CharField(max_length=1, choices=ANSWER_CHOICES)
    marks = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.assignment} - {self.question_text[:60]}'


class AssignmentSubmission(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_SUBMITTED = 'submitted'
    STATUS_GRADED = 'graded'
    STATUS_RETURNED = 'returned'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_GRADED, 'Graded'),
        (STATUS_RETURNED, 'Returned'),
    ]

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='submissions',
    )
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='assignment_submissions',
    )
    submission_text = models.TextField(blank=True)
    text_answer = models.TextField(blank=True)
    quiz_answers = models.JSONField(default=dict, blank=True)
    submitted_at = models.DateTimeField(blank=True, null=True)
    score = models.PositiveSmallIntegerField(blank=True, null=True)
    max_score = models.PositiveSmallIntegerField(default=100)
    feedback = models.TextField(blank=True)
    graded_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        related_name='graded_assignment_submissions',
        blank=True,
        null=True,
    )
    graded_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )

    class Meta:
        ordering = ['-submitted_at', 'assignment__due_date']
        constraints = [
            models.UniqueConstraint(
                fields=['assignment', 'student'],
                name='unique_assignment_submission_per_student',
            ),
        ]

    def __str__(self):
        return f'{self.assignment} - {self.student}'

    @property
    def percentage(self):
        if self.score is None:
            return None
        marks = self.assignment.marks or self.max_score
        if not marks:
            return None
        return round((self.score / marks) * 100, 2)

    @property
    def letter_grade(self):
        percentage = self.percentage
        if percentage is None:
            return ''
        if percentage >= 80:
            return 'A'
        if percentage >= 70:
            return 'B'
        if percentage >= 60:
            return 'C'
        if percentage >= 50:
            return 'D'
        return 'F'
