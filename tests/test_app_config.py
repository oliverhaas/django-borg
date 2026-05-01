import django
from django.apps import apps


def test_app_is_installed():
    assert apps.is_installed("django_borg")


def test_app_config_name():
    config = apps.get_app_config("django_borg")
    assert config.name == "django_borg"
    assert config.verbose_name == "Borg"


def test_django_version_supported():
    assert django.VERSION >= (5, 2)
