from pathlib import Path
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import models


ASSIGNMENT_FILE_MAX_SIZE = 10 * 1024 * 1024
ASSIGNMENT_FILE_EXTENSIONS = {
    '.pdf',
    '.doc',
    '.docx',
    '.png',
    '.jpg',
    '.jpeg',
    '.zip',
    '.txt',
    '.html',
    '.css',
    '.js',
    '.py',
}


def validate_assignment_file(uploaded_file):
    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in ASSIGNMENT_FILE_EXTENSIONS:
        raise ValidationError('Unsupported file type.')
    if uploaded_file.size > ASSIGNMENT_FILE_MAX_SIZE:
        raise ValidationError('Assignment files must be 10MB or smaller.')


def assignment_upload_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return f'assignments/submissions/{instance.student_id}/{uuid4().hex}{extension}'


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


class Assignment(models.Model):
    SUBMISSION_TEXT = 'text'
    SUBMISSION_FILE_UPLOAD = 'file_upload'
    SUBMISSION_BOTH = 'both'

    SUBMISSION_TYPE_CHOICES = [
        (SUBMISSION_TEXT, 'Text answer'),
        (SUBMISSION_FILE_UPLOAD, 'File upload'),
        (SUBMISSION_BOTH, 'Text + File upload'),
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
        default=SUBMISSION_TEXT,
    )
    marks = models.PositiveSmallIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['due_date', '-created_at']

    def __str__(self):
        return f'{self.course} - {self.title}'


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
    uploaded_file = models.FileField(
        upload_to=assignment_upload_path,
        validators=[validate_assignment_file],
        blank=True,
        null=True,
    )
    uploaded_file_name = models.CharField(max_length=255, blank=True)
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
