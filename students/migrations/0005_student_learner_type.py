from django.db import migrations, models


def populate_learner_type(apps, schema_editor):
    Student = apps.get_model('students', 'Student')
    Student.objects.filter(parent__isnull=False).update(learner_type='child')
    Student.objects.filter(parent__isnull=True, user__isnull=False).update(learner_type='adult')


class Migration(migrations.Migration):
    dependencies = [
        ('students', '0004_rename_status_student_approval_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='learner_type',
            field=models.CharField(
                choices=[('child', 'Child learner'), ('adult', 'Adult learner')],
                default='child',
                max_length=20,
            ),
        ),
        migrations.RunPython(populate_learner_type, migrations.RunPython.noop),
    ]
