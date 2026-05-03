"""Re-run AI inference on graduated mappings to detect drift.

Run::

    python manage.py borg_drift
    python manage.py borg_drift --source acme --limit 50
"""

from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand

from catalog.inferencer import DEMO_AI
from catalog.models import Product
from django_borg import DriftRunner


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--source", help="Restrict to one supplier name.")
        parser.add_argument(
            "--older-than-days",
            type=int,
            help="Skip mappings whose latest AI vote is younger than N days.",
        )
        parser.add_argument("--limit", type=int, help="Cap total iterations.")

    def handle(self, *args: Any, **options: Any) -> None:
        runner = DriftRunner(target_schema=Product, ai=DEMO_AI)
        older_than = (
            timedelta(days=options["older_than_days"])
            if options["older_than_days"] is not None
            else None
        )
        result = runner.run(
            source=options["source"],
            older_than=older_than,
            limit=options["limit"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"field_revoted={result.field_mappings_revoted}"
                f" value_revoted={result.value_mappings_revoted}"
                f" skipped_recent={result.skipped_recent}"
                f" skipped_ai_failure={result.skipped_ai_failure}",
            ),
        )
