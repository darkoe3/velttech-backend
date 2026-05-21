from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('students', '0005_student_learner_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='programme_of_interest',
            field=models.CharField(
                blank=True,
                choices=[
                    ('Fullstack Web Development', 'Fullstack Web Development'),
                    ('AI Productivity & Digital Skills', 'AI Productivity & Digital Skills'),
                    ('General Adult Digital Literacy', 'General Adult Digital Literacy'),
                    ('Coding & Robotics for Kids & Teens', 'Coding & Robotics for Kids & Teens'),
                    ('Information Technology Support (IT Support)', 'Information Technology Support (IT Support)'),
                    ('Advanced Excel & Data Analytics', 'Advanced Excel & Data Analytics'),
                    ('Website Design with WordPress', 'Website Design with WordPress'),
                    ('Python Programming', 'Python Programming'),
                    ('Cloud Computing', 'Cloud Computing'),
                    ('Digital Marketing & Social Media', 'Digital Marketing & Social Media'),
                    ('Video Editing & Content Creation', 'Video Editing & Content Creation'),
                    ('ICT Integration for Teachers', 'ICT Integration for Teachers'),
                    ('Freelancing & Tech Entrepreneurship', 'Freelancing & Tech Entrepreneurship'),
                ],
                max_length=150,
            ),
        ),
    ]
