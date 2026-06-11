# Generated migration for certificates app

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('courses', '0002_course_fee'),
        ('enrollments', '0005_assignment_assignmentsubmission'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('students', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Certificate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('certificate_number', models.CharField(editable=False, max_length=50, unique=True)),
                ('issued_at', models.DateTimeField(blank=True, null=True)),
                ('completion_date', models.DateField()),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('issued', 'Issued'), ('revoked', 'Revoked')], default='draft', max_length=20)),
                ('verification_code', models.CharField(default=uuid.uuid4, editable=False, max_length=36, unique=True)),
                ('certificate_file', models.FileField(blank=True, null=True, upload_to='certificates/')),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('revoke_reason', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='certificates', to='courses.course')),
                ('enrollment', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='certificate', to='enrollments.enrollment')),
                ('issued_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='issued_certificates', to=settings.AUTH_USER_MODEL)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='certificates', to='students.student')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='certificate',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'issued')), fields=('student', 'course'), name='unique_student_course_certificate'),
        ),
    ]
