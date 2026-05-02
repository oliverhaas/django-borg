SECRET_KEY = "test-secret-key"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "django_borg",
    "testapp",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}

MIGRATION_MODULES = {"testapp": None}

STATIC_URL = "/static/"

USE_TZ = True

ROOT_URLCONF = "settings.urls"

BORG_MIN_WEIGHT = 5
BORG_MIN_CONFIDENCE = 0.9
BORG_AI_VOTER_IDENTIFIER = "ai"
BORG_AI_VOTER_WEIGHT = 1
BORG_REVIEWER_VOTER_WEIGHT = 100
