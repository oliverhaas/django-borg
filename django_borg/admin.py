from typing import TYPE_CHECKING

from django.contrib import admin
from django.db.models import Q

from django_borg import conf
from django_borg.models import (
    FieldMapping,
    Rule,
    SourceField,
    SourceSchema,
    TargetField,
    TargetSchema,
    ValueMapping,
    Vote,
    Voter,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet
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
    autocomplete_fields = ("target_schema", "target_field")


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


class TargetFieldInline(admin.TabularInline):
    model = TargetField
    extra = 0
    fields = ("name", "is_enum", "description")


@admin.register(TargetSchema)
class TargetSchemaAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)
    inlines = (TargetFieldInline,)


@admin.register(TargetField)
class TargetFieldAdmin(admin.ModelAdmin):
    list_display = ("schema", "name", "is_enum")
    list_filter = ("is_enum", "schema")
    search_fields = ("name",)
    autocomplete_fields = ("schema",)


class SourceFieldInline(admin.TabularInline):
    model = SourceField
    extra = 0
    fields = ("name",)


@admin.register(SourceSchema)
class SourceSchemaAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)
    inlines = (SourceFieldInline,)


@admin.register(SourceField)
class SourceFieldAdmin(admin.ModelAdmin):
    list_display = ("schema", "name")
    list_filter = ("schema",)
    search_fields = ("name",)
    autocomplete_fields = ("schema",)


class NeedsReviewFilter(admin.SimpleListFilter):
    """Mapping has at least one vote but is not yet graduated.

    Mappings with zero votes are *unsurveyed*, not in need of review;
    mappings already above thresholds are *graduated* and don't need review.
    """

    title = "review status"
    parameter_name = "needs_review"

    def lookups(
        self,
        request: "HttpRequest",  # noqa: ARG002
        model_admin: admin.ModelAdmin,  # noqa: ARG002
    ) -> list[tuple[str, str]]:
        return [("yes", "Needs review")]

    def queryset(
        self,
        request: "HttpRequest",  # noqa: ARG002
        qs: "QuerySet",
    ) -> "QuerySet":
        if self.value() != "yes":
            return qs
        min_weight = conf.min_weight()
        min_confidence = conf.min_confidence()
        return qs.exclude(total_weight=0).filter(
            Q(total_weight__lt=min_weight) | Q(confidence__lt=min_confidence),
        )


@admin.register(FieldMapping)
class FieldMappingAdmin(admin.ModelAdmin):
    list_display = (
        "source_schema",
        "source_field",
        "target_schema",
        "current_target",
        "confidence",
        "total_weight",
        "updated_at",
    )
    list_filter = (NeedsReviewFilter, "source_schema", "target_schema")
    search_fields = ("source_field", "current_target")
    readonly_fields = ("current_target", "confidence", "total_weight", "created_at", "updated_at")
    autocomplete_fields = ("source_schema", "target_schema")


@admin.register(ValueMapping)
class ValueMappingAdmin(admin.ModelAdmin):
    list_display = (
        "target_field",
        "source_value",
        "current_target",
        "confidence",
        "total_weight",
        "updated_at",
    )
    list_filter = (NeedsReviewFilter, "target_field__schema")
    search_fields = ("source_value", "current_target")
    readonly_fields = ("current_target", "confidence", "total_weight", "created_at", "updated_at")
    autocomplete_fields = ("target_field",)
