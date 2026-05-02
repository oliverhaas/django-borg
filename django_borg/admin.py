from typing import TYPE_CHECKING

from django.contrib import admin

from django_borg.models import Rule, Vote, Voter

if TYPE_CHECKING:
    from django.http import HttpRequest


@admin.register(Voter)
class VoterAdmin(admin.ModelAdmin):
    list_display = ("identifier", "kind", "weight")
    list_filter = ("kind",)
    search_fields = ("identifier",)


@admin.register(Rule)
class RuleAdmin(admin.ModelAdmin):
    list_display = (
        "target_schema",
        "kind",
        "polarity",
        "pattern_type",
        "source_pattern",
        "target",
    )
    list_filter = ("kind", "polarity", "pattern_type", "target_schema")
    search_fields = ("source_pattern", "target")


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ("voter", "agreed_target", "content_type", "object_id", "created_at")
    list_filter = ("voter__kind", "content_type")
    search_fields = ("agreed_target", "voter__identifier")
    readonly_fields = ("voter", "agreed_target", "content_type", "object_id", "created_at")
    date_hierarchy = "created_at"

    def has_change_permission(
        self,
        request: "HttpRequest",  # noqa: ARG002
        obj: object | None = None,  # noqa: ARG002
    ) -> bool:
        return False

    def has_delete_permission(
        self,
        request: "HttpRequest",  # noqa: ARG002
        obj: object | None = None,  # noqa: ARG002
    ) -> bool:
        return False
