from django.conf import settings
from django.contrib.auth.models import Group
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .models import Profile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile(sender, instance, created, **kwargs):
    """Every new user gets a Profile; superusers are Admins, everyone else a Patient."""
    if created:
        role = Profile.Role.ADMIN if instance.is_superuser else Profile.Role.PATIENT
        Profile.objects.get_or_create(user=instance, defaults={'role': role})


@receiver(post_migrate)
def create_role_groups(sender, **kwargs):
    """Make sure one Group exists per role after migrations."""
    if sender.name != 'accounts':
        return
    for _, label in Profile.Role.choices:
        Group.objects.get_or_create(name=label)
