from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Users must have an email address.')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', User.ROLE_ADMIN)
        extra_fields.setdefault('approval_status', User.APPROVAL_APPROVED)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_ADMIN = 'admin'
    ROLE_PARENT = 'parent'
    ROLE_STUDENT = 'student'
    ROLE_INSTRUCTOR = 'instructor'
    ACCOUNT_PARENT_REGISTERING_CHILD = 'parent_registering_child'
    ACCOUNT_ADULT_LEARNER = 'adult_learner'
    APPROVAL_PENDING = 'pending'
    APPROVAL_APPROVED = 'approved'
    APPROVAL_REJECTED = 'rejected'

    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Admin'),
        (ROLE_PARENT, 'Parent'),
        (ROLE_STUDENT, 'Student'),
        (ROLE_INSTRUCTOR, 'Instructor'),
    ]

    ACCOUNT_TYPE_CHOICES = [
        (ACCOUNT_PARENT_REGISTERING_CHILD, 'Parent registering child'),
        (ACCOUNT_ADULT_LEARNER, 'Adult learner'),
    ]

    APPROVAL_STATUS_CHOICES = [
        (APPROVAL_PENDING, 'Pending'),
        (APPROVAL_APPROVED, 'Approved'),
        (APPROVAL_REJECTED, 'Rejected'),
    ]

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    account_type = models.CharField(
        max_length=40,
        choices=ACCOUNT_TYPE_CHOICES,
        blank=True,
        default='',
    )
    approval_status = models.CharField(
        max_length=20,
        choices=APPROVAL_STATUS_CHOICES,
        default=APPROVAL_PENDING,
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name', 'role']

    class Meta:
        ordering = ['email']

    def __str__(self):
        return self.email


class ActivityLog(models.Model):
    user = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        related_name='activity_logs',
        blank=True,
        null=True,
    )
    action = models.CharField(max_length=120)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    role = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.action} - {self.created_at}'
