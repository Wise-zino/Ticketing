import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
# Read any setting prefixed CELERY_ from Django's settings.py
app.config_from_object("django.conf:settings", namespace="CELERY")
# Find tasks.py in every installed app
app.autodiscover_tasks()