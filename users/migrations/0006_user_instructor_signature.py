from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0005_user_suspicious_registration'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='instructor_signature',
            field=models.ImageField(blank=True, help_text='Optional signature image used on certificates for assigned learners.', null=True, upload_to='instructors/signatures/'),
        ),
    ]
