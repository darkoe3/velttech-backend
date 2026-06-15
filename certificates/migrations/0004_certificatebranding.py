from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('certificates', '0003_production_certificate_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='CertificateBranding',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('academy_logo', models.ImageField(blank=True, help_text='Optional logo used on generated certificate PDFs.', null=True, upload_to='certificates/branding/')),
                ('director_signature', models.ImageField(blank=True, help_text='Optional Academy Director signature used on generated certificate PDFs.', null=True, upload_to='certificates/branding/')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Certificate branding',
                'verbose_name_plural': 'Certificate branding',
            },
        ),
    ]
