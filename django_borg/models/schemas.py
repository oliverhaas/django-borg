from django.db import models


class TargetSchema(models.Model):
    name = models.CharField(max_length=128, unique=True)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class TargetField(models.Model):
    schema = models.ForeignKey(TargetSchema, on_delete=models.CASCADE, related_name="fields")
    name = models.CharField(max_length=128)
    is_enum = models.BooleanField(default=False)
    description = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["schema", "name"],
                name="borg_targetfield_unique_per_schema",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.schema.name}.{self.name}"


class SourceSchema(models.Model):
    name = models.CharField(max_length=128, unique=True)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class SourceField(models.Model):
    schema = models.ForeignKey(SourceSchema, on_delete=models.CASCADE, related_name="fields")
    name = models.CharField(max_length=128)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["schema", "name"],
                name="borg_sourcefield_unique_per_schema",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.schema.name}.{self.name}"
