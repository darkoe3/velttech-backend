from django.db import models


class Parent(models.Model):
    user = models.OneToOneField(
        'users.User',
        on_delete=models.CASCADE,
        related_name='parent_profile',
        blank=True,
        null=True,
    )
    first_name = models.CharField(max_length=100)
    other_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20)
    address = models.TextField(blank=True)
    occupation = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['last_name', 'first_name']

    def __str__(self):
        names = [self.first_name, self.other_name, self.last_name]
        return ' '.join(name for name in names if name)


class Student(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    parent = models.ForeignKey(
        Parent,
        on_delete=models.CASCADE,
        related_name='students',
        blank=True,
        null=True,
    )
    user = models.OneToOneField(
        'users.User',
        on_delete=models.CASCADE,
        related_name='student_profile',
        blank=True,
        null=True,
    )
    first_name = models.CharField(max_length=100)
    other_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(blank=True, null=True)
    school_name = models.CharField(max_length=150, blank=True)
    emergency_contact = models.CharField(max_length=20, blank=True)
    approval_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['last_name', 'first_name']

    def __str__(self):
        names = [self.first_name, self.other_name, self.last_name]
        return ' '.join(name for name in names if name)

# Create your models here.
