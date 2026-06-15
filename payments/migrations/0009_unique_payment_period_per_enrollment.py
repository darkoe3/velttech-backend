from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ('payments', '0008_payment_email_sent_timestamps'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='payment',
            constraint=models.UniqueConstraint(
                fields=('enrollment', 'payment_period'),
                condition=~Q(payment_period=''),
                name='unique_payment_period_per_enrollment',
            ),
        ),
    ]
