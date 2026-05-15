from django.db import models


class Notification(models.Model):
    AUDIENCE_ALL = 'all'
    AUDIENCE_PARENTS = 'parents'
    AUDIENCE_STUDENTS = 'students'
    AUDIENCE_INSTRUCTORS = 'instructors'

    AUDIENCE_CHOICES = [
        (AUDIENCE_ALL, 'All'),
        (AUDIENCE_PARENTS, 'Parents'),
        (AUDIENCE_STUDENTS, 'Students'),
        (AUDIENCE_INSTRUCTORS, 'Instructors'),
    ]

    title = models.CharField(max_length=180)
    message = models.TextField()
    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default=AUDIENCE_ALL)
    recipient = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='notifications',
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title
