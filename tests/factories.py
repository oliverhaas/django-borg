import factory
from django.contrib.auth import get_user_model
from factory.django import DjangoModelFactory

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


class TargetSchemaFactory(DjangoModelFactory):
    class Meta:
        model = TargetSchema
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Schema{n}")


class TargetFieldFactory(DjangoModelFactory):
    class Meta:
        model = TargetField

    schema = factory.SubFactory(TargetSchemaFactory)
    name = factory.Sequence(lambda n: f"field_{n}")
    is_enum = False


class SourceSchemaFactory(DjangoModelFactory):
    class Meta:
        model = SourceSchema
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"supplier{n}")


class SourceFieldFactory(DjangoModelFactory):
    class Meta:
        model = SourceField

    schema = factory.SubFactory(SourceSchemaFactory)
    name = factory.Sequence(lambda n: f"col_{n}")


class VoterFactory(DjangoModelFactory):
    class Meta:
        model = Voter
        django_get_or_create = ("kind", "identifier")

    kind = Voter.Kind.AI
    identifier = factory.Sequence(lambda n: f"voter_{n}")
    weight = 1


class AiVoterFactory(VoterFactory):
    kind = Voter.Kind.AI
    identifier = "ai-test"
    weight = 1


class ReviewerVoterFactory(VoterFactory):
    kind = Voter.Kind.HUMAN
    identifier = "reviewer-test"
    weight = 100


class FieldMappingFactory(DjangoModelFactory):
    class Meta:
        model = FieldMapping

    source_schema = factory.SubFactory(SourceSchemaFactory)
    source_field = factory.Sequence(lambda n: f"src_{n}")
    target_schema = factory.SubFactory(TargetSchemaFactory)


class ValueMappingFactory(DjangoModelFactory):
    class Meta:
        model = ValueMapping

    target_field = factory.SubFactory(TargetFieldFactory)
    source_value = factory.Sequence(lambda n: f"value_{n}")


class VoteFactory(DjangoModelFactory):
    class Meta:
        model = Vote

    voter = factory.SubFactory(AiVoterFactory)
    agreed_target = "color"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        mapping = kwargs.pop("mapping", None)
        instance = model_class(*args, **kwargs)
        if mapping is not None:
            instance.mapping = mapping
        instance.save()
        return instance


class FieldRuleFactory(DjangoModelFactory):
    class Meta:
        model = Rule

    target_schema = factory.SubFactory(TargetSchemaFactory)
    kind = Rule.Kind.FIELD
    polarity = Rule.Polarity.DO
    pattern_type = Rule.PatternType.EXACT
    source_pattern = "Farbe"
    target = "color"


class ValueRuleFactory(DjangoModelFactory):
    class Meta:
        model = Rule

    target_schema = factory.SubFactory(TargetSchemaFactory)
    target_field = factory.SubFactory(TargetFieldFactory)
    kind = Rule.Kind.VALUE
    polarity = Rule.Polarity.DO
    pattern_type = Rule.PatternType.EXACT
    source_pattern = "Rot"
    target = "red"


class UserFactory(DjangoModelFactory):
    class Meta:
        model = get_user_model()
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda u: f"{u.username}@example.test")
    is_staff = True
    is_superuser = True
