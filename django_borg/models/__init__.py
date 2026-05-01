"""Concrete models are imported here so Django's app loader sees them."""

from django_borg.models.voters import Voter

__all__ = ["Voter"]
