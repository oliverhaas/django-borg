from django.db import models

COLOR_CHOICES = [
    ("red", "Red"),
    ("blue", "Blue"),
    ("green", "Green"),
    ("black", "Black"),
    ("white", "White"),
]

SIZE_CHOICES = [
    ("XS", "XS"),
    ("S", "S"),
    ("M", "M"),
    ("L", "L"),
    ("XL", "XL"),
]


class Product(models.Model):
    title = models.CharField(max_length=255)
    color = models.CharField(max_length=32, choices=COLOR_CHOICES, blank=True, default="")
    size = models.CharField(max_length=8, choices=SIZE_CHOICES, blank=True, default="")
    description = models.TextField(blank=True, default="")

    def __str__(self) -> str:
        return self.title
