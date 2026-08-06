from django.contrib import admin

from .models import (
    Assignment,
    AssignmentQuestion,
    AssignmentSubmission,
    AssessmentResult,
    Attendance,
    Enrollment,
    LessonNote,
    ProgressReport,
)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'instructor', 'status', 'enrolled_at', 'start_date')
    list_filter = ('status', 'course', 'instructor')
    search_fields = (
        'student__first_name',
        'student__last_name',
        'course__title',
        'instructor__email',
    )


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('enrollment', 'date', 'status', 'recorded_by', 'created_at')
    list_filter = ('status', 'date')
    search_fields = ('enrollment__student__first_name', 'enrollment__student__last_name')


@admin.register(LessonNote)
class LessonNoteAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'instructor', 'lesson_date', 'created_at')
    list_filter = ('course', 'instructor', 'lesson_date')
    search_fields = ('title', 'course__title', 'instructor__email')


@admin.register(ProgressReport)
class ProgressReportAdmin(admin.ModelAdmin):
    list_display = ('enrollment', 'progress_score', 'created_by', 'created_at')
    list_filter = ('progress_score', 'created_at')
    search_fields = ('enrollment__student__first_name', 'enrollment__student__last_name')


@admin.register(AssessmentResult)
class AssessmentResultAdmin(admin.ModelAdmin):
    list_display = (
        'enrollment',
        'learner',
        'course',
        'practical_score',
        'final_project_score',
        'objective_quiz_score',
        'overall_score',
        'percentage',
        'status',
        'is_approved',
        'approved_by',
        'approved_at',
    )
    list_filter = ('status', 'is_approved', 'enrollment__course')
    search_fields = (
        'enrollment__student__first_name',
        'enrollment__student__last_name',
        'enrollment__course__title',
    )
    readonly_fields = (
        'overall_score',
        'total_max_score',
        'percentage',
        'status',
        'approved_by',
        'approved_at',
        'created_at',
        'updated_at',
    )

    def learner(self, obj):
        return obj.enrollment.student

    def course(self, obj):
        return obj.enrollment.course


class AssignmentQuestionInline(admin.TabularInline):
    model = AssignmentQuestion
    extra = 1


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'instructor', 'submission_type', 'due_date', 'is_active', 'created_at')
    list_filter = ('submission_type', 'course', 'instructor', 'is_active', 'due_date')
    search_fields = ('title', 'course__title', 'instructor__email')
    inlines = [AssignmentQuestionInline]


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'student', 'status', 'score', 'submitted_at')
    list_filter = ('status', 'assignment__course')
    search_fields = (
        'assignment__title',
        'student__first_name',
        'student__last_name',
    )
