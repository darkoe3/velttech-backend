from django.db import migrations, models


def normalize_certificate_numbers_and_status(apps, schema_editor):
    Certificate = apps.get_model('certificates', 'Certificate')
    for certificate in Certificate.objects.order_by('created_at', 'id'):
        changed = False
        if certificate.status == 'issued':
            certificate.status = 'active'
            changed = True

        if not certificate.certificate_number.startswith('VTC-'):
            year = (
                certificate.issue_date.year
                if certificate.issue_date
                else certificate.completion_date.year
            )
            prefix = f'VTC-{year}-'
            existing = Certificate.objects.filter(
                certificate_number__startswith=prefix,
            ).exclude(pk=certificate.pk).order_by('-certificate_number').first()
            sequence = int(existing.certificate_number.split('-')[-1]) if existing else 0
            certificate.certificate_number = f'{prefix}{sequence + 1:06d}'
            changed = True

        if changed:
            certificate.save(update_fields=['status', 'certificate_number'])


class Migration(migrations.Migration):

    dependencies = [
        ('certificates', '0002_certificate_metadata'),
    ]

    operations = [
        migrations.AddField(
            model_name='certificate',
            name='pdf_file',
            field=models.FileField(blank=True, null=True, upload_to='certificates/'),
        ),
        migrations.AddField(
            model_name='certificate',
            name='qr_code',
            field=models.ImageField(blank=True, null=True, upload_to='certificates/qr/'),
        ),
        migrations.AddField(
            model_name='certificate',
            name='skills_covered',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name='certificate',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Draft'),
                    ('active', 'Active'),
                    ('issued', 'Issued (legacy)'),
                    ('revoked', 'Revoked'),
                ],
                default='draft',
                max_length=20,
            ),
        ),
        migrations.RunPython(normalize_certificate_numbers_and_status, migrations.RunPython.noop),
    ]
