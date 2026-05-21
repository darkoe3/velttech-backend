from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('payments', '0005_add_paystack_payment_method'),
    ]

    operations = [
        migrations.AlterField(
            model_name='payment',
            name='payment_method',
            field=models.CharField(
                blank=True,
                choices=[
                    ('pending', 'Pending'),
                    ('cash', 'Cash'),
                    ('mobile_money', 'Mobile Money'),
                    ('card', 'Card'),
                    ('bank_transfer', 'Bank Transfer'),
                    ('paystack', 'Paystack'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
    ]
