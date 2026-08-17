from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('certificates', '0005_certificate_certificate_email_sent_at'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='certificate',
            name='unique_student_course_certificate',
        ),
    ]
