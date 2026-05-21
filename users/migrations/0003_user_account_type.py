from django.db import migrations, models


def populate_account_type(apps, schema_editor):
    User = apps.get_model('users', 'User')
    User.objects.filter(role='parent', account_type='').update(
        account_type='parent_registering_child',
    )
    User.objects.filter(role='student', account_type='').update(
        account_type='adult_learner',
    )


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0002_activitylog'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='account_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('parent_registering_child', 'Parent registering child'),
                    ('adult_learner', 'Adult learner'),
                ],
                default='',
                max_length=40,
            ),
        ),
        migrations.RunPython(populate_account_type, migrations.RunPython.noop),
    ]
