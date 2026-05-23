from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0004_user_approval_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='is_suspicious',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='user',
            name='suspicious_reason',
            field=models.TextField(blank=True),
        ),
    ]
