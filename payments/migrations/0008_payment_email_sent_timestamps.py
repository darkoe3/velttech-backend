from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('payments', '0007_payment_payment_period'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='confirmation_email_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='payment',
            name='invoice_email_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
