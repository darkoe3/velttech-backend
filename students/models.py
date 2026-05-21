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
    LEARNER_CHILD = 'child'
    LEARNER_ADULT = 'adult'
    PROGRAMME_FULLSTACK = 'Fullstack Web Development'
    PROGRAMME_AI_PRODUCTIVITY = 'AI Productivity & Digital Skills'
    PROGRAMME_DIGITAL_LITERACY = 'General Adult Digital Literacy'
    PROGRAMME_KIDS_CODING = 'Coding & Robotics for Kids & Teens'
    PROGRAMME_IT_SUPPORT = 'Information Technology Support (IT Support)'
    PROGRAMME_EXCEL_ANALYTICS = 'Advanced Excel & Data Analytics'
    PROGRAMME_WORDPRESS = 'Website Design with WordPress'
    PROGRAMME_PYTHON = 'Python Programming'
    PROGRAMME_CLOUD = 'Cloud Computing'
    PROGRAMME_DIGITAL_MARKETING = 'Digital Marketing & Social Media'
    PROGRAMME_VIDEO_EDITING = 'Video Editing & Content Creation'
    PROGRAMME_TEACHERS_ICT = 'ICT Integration for Teachers'
    PROGRAMME_FREELANCING = 'Freelancing & Tech Entrepreneurship'

    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'

    LEARNER_TYPE_CHOICES = [
        (LEARNER_CHILD, 'Child learner'),
        (LEARNER_ADULT, 'Adult learner'),
    ]

    PROGRAMME_CHOICES = [
        (PROGRAMME_FULLSTACK, PROGRAMME_FULLSTACK),
        (PROGRAMME_AI_PRODUCTIVITY, PROGRAMME_AI_PRODUCTIVITY),
        (PROGRAMME_DIGITAL_LITERACY, PROGRAMME_DIGITAL_LITERACY),
        (PROGRAMME_KIDS_CODING, PROGRAMME_KIDS_CODING),
        (PROGRAMME_IT_SUPPORT, PROGRAMME_IT_SUPPORT),
        (PROGRAMME_EXCEL_ANALYTICS, PROGRAMME_EXCEL_ANALYTICS),
        (PROGRAMME_WORDPRESS, PROGRAMME_WORDPRESS),
        (PROGRAMME_PYTHON, PROGRAMME_PYTHON),
        (PROGRAMME_CLOUD, PROGRAMME_CLOUD),
        (PROGRAMME_DIGITAL_MARKETING, PROGRAMME_DIGITAL_MARKETING),
        (PROGRAMME_VIDEO_EDITING, PROGRAMME_VIDEO_EDITING),
        (PROGRAMME_TEACHERS_ICT, PROGRAMME_TEACHERS_ICT),
        (PROGRAMME_FREELANCING, PROGRAMME_FREELANCING),
    ]

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
    learner_type = models.CharField(
        max_length=20,
        choices=LEARNER_TYPE_CHOICES,
        default=LEARNER_CHILD,
    )
    programme_of_interest = models.CharField(
        max_length=150,
        choices=PROGRAMME_CHOICES,
        blank=True,
    )
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
