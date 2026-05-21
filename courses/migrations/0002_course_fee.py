from django.db import migrations, models


def copy_monthly_fee_to_fee(apps, schema_editor):
    Course = apps.get_model('courses', 'Course')
    for course in Course.objects.all():
        course.fee = course.monthly_fee
        course.save(update_fields=['fee'])


class Migration(migrations.Migration):
    dependencies = [
        ('courses', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='fee',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.RunPython(copy_monthly_fee_to_fee, migrations.RunPython.noop),
    ]
