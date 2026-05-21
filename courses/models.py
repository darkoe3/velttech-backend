from django.db import models


class Course(models.Model):
    title = models.CharField(max_length=150)
    description = models.TextField()
    duration_months = models.PositiveIntegerField()
    monthly_fee = models.DecimalField(max_digits=10, decimal_places=2)
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['title']

    def __str__(self):
        return self.title
