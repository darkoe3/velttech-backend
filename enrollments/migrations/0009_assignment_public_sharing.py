import uuid

from django.db import migrations, models


def populate_share_tokens(apps, schema_editor):
    Assignment = apps.get_model('enrollments', 'Assignment')
    for assignment in Assignment.objects.filter(share_token__isnull=True):
        assignment.share_token = uuid.uuid4()
        assignment.save(update_fields=['share_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('enrollments', '0008_remove_assignmentsubmission_uploaded_file_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='assignment',
            name='is_public',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='assignment',
            name='max_guest_attempts',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='assignment',
            name='share_expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='assignment',
            name='share_token',
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.RunPython(populate_share_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='assignment',
            name='share_token',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
