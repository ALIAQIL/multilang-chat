from django.db import models
from datetime import datetime

class Room(models.Model):
    name = models.CharField(max_length=1000)

class Message(models.Model):
    value = models.CharField(max_length=10000)
    user = models.CharField(max_length=255)
    room = models.CharField(max_length=255)
    date = models.DateTimeField(default=datetime.now, blank=True)
    language = models.CharField(max_length=50, default='English')
    is_original = models.BooleanField(default=True)  # Flag for original messages
    original_id = models.IntegerField(null=True, blank=True)  # Reference to original message