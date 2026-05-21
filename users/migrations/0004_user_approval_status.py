from django.db import migrations, models


def approve_existing_users(apps, schema_editor):
    User = apps.get_model('users', 'User')
    User.objects.filter(approval_status='pending').update(approval_status='approved')


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0003_user_account_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='approval_status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('approved', 'Approved'),
                    ('rejected', 'Rejected'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.RunPython(approve_existing_users, migrations.RunPython.noop),
    ]
