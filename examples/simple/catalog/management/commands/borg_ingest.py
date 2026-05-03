"""Ingest the bundled sample feed via SchemaAssimilator.

Run::

    python manage.py borg_ingest
    python manage.py borg_ingest --extract  # extracts from free-text descriptions
"""

from typing import Any

from django.core.management.base import BaseCommand

from catalog.inferencer import DEMO_AI
from catalog.models import Product
from catalog.sample_data import ACME_DESCRIPTIONS, ACME_FEED
from django_borg import SchemaAssimilator


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--extract",
            action="store_true",
            help="Use the descriptions feed and extract structured fields from free text.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["extract"]:
            self._ingest_with_extraction()
        else:
            self._ingest_direct()

    def _ingest_direct(self) -> None:
        borg = SchemaAssimilator(target_schema=Product, ai=DEMO_AI)
        for raw in ACME_FEED:
            result = borg.assimilate(raw, source="acme")
            result.product.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"saved {result.product!s:30s}"
                    f" ai_calls={result.cost.ai_calls}"
                    f" deterministic={result.cost.deterministic_hits}"
                    f" unresolved={result.unresolved}",
                ),
            )

    def _ingest_with_extraction(self) -> None:
        borg = SchemaAssimilator(
            target_schema=Product,
            ai=DEMO_AI,
            extract_from=["Beschreibung"],
        )
        for raw in ACME_DESCRIPTIONS:
            result = borg.assimilate(raw, source="acme")
            result.product.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"saved {result.product!s:30s}"
                    f" ai_calls={result.cost.ai_calls}"
                    f" extractions={result.cost.extraction_calls}"
                    f" color={result.product.color!r}"
                    f" size={result.product.size!r}",
                ),
            )
