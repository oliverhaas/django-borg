from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django_borg.models.mappings import Mapping


def recompute_confidence(mapping: "Mapping") -> None:
    """Recompute denormalised confidence fields on a mapping from its vote log."""
    weights: dict[str, int] = defaultdict(int)
    for vote in mapping.votes.select_related("voter").all():
        weights[vote.agreed_target] += vote.voter.weight

    if not weights:
        mapping.current_target = ""
        mapping.confidence = 0.0
        mapping.total_weight = 0
    else:
        top_target, top_weight = max(weights.items(), key=lambda kv: kv[1])
        total = sum(weights.values())
        mapping.current_target = top_target
        mapping.confidence = top_weight / total
        mapping.total_weight = total

    mapping.save(update_fields=["current_target", "confidence", "total_weight", "updated_at"])
