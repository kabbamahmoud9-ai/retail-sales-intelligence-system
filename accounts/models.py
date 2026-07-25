from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('staff', 'Staff'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='staff')
    profile_picture = models.ImageField(upload_to='staff_avatars/', null=True, blank=True)

    def __str__(self):
        return f"{self.username} ({self.role})"