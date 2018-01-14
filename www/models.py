from __future__ import unicode_literals

from django.db import models

# Create your models here.

class OneTimePin(models.Model):
    address = models.CharField(max_length=20,null=True)
    pin = models.CharField(max_length=10)
    created = models.DateTimeField(auto_now=True)
    active = models.BooleanField(default=False, blank=True)

    def __unicode__(self):
        return self.pin        
