from django.apps import AppConfig


class BorgConfig(AppConfig):
    name = "django_borg"
    verbose_name = "Borg"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from django_borg import signals  # noqa: F401, PLC0415  -- registers post_save handlers
