from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('payments', '0006_payment_method_pending_default'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='payment_period',
            field=models.CharField(blank=True, max_length=80),
        ),
    ]
