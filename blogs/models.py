from autoslug import AutoSlugField
from django.db import models


class BlogCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = AutoSlugField(populate_from="name", unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Blog categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Blog(models.Model):
    name = models.CharField(max_length=220)
    slug = AutoSlugField(populate_from="name", unique=True)
    description = models.TextField()
    main_image = models.ImageField(upload_to="blogs/", blank=True, null=True)
    categories = models.ManyToManyField(BlogCategory, related_name="blogs", blank=True)
    likes_count = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)
    published_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]

    def __str__(self):
        return self.name
