from django.conf import settings


def min_weight() -> int:
    return int(getattr(settings, "BORG_MIN_WEIGHT", 5))


def min_confidence() -> float:
    return float(getattr(settings, "BORG_MIN_CONFIDENCE", 0.9))


def ai_voter_identifier() -> str:
    return str(getattr(settings, "BORG_AI_VOTER_IDENTIFIER", "ai"))


def ai_voter_weight() -> int:
    return int(getattr(settings, "BORG_AI_VOTER_WEIGHT", 1))
