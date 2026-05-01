SECRET_KEY = "test-secret-key"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django_borg",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}

MIGRATION_MODULES = {"django_borg": None}

USE_TZ = True

ROOT_URLCONF = "settings.urls"

BORG_MIN_WEIGHT = 5
BORG_MIN_CONFIDENCE = 0.9
BORG_AI_VOTER_IDENTIFIER = "ai"
BORG_AI_VOTER_WEIGHT = 1
