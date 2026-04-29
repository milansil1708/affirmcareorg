from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.dateparse import parse_datetime

from blogs.models import Blog, BlogCategory
from blogs.seed_data import SEED_DATA


class Command(BaseCommand):
    help = "Seed blog demo data without creating duplicates. Safe to run multiple times."

    def _parse_dt(self, value):
        if not value:
            return None
        return parse_datetime(value)

    @transaction.atomic
    def handle(self, *args, **options):
        created_counts = {
            "BlogCategory": 0,
            "Blog": 0,
        }

        categories = {}
        for item in SEED_DATA.get("BlogCategory", []):
            obj, created = BlogCategory.objects.get_or_create(name=item["name"])
            if created:
                created_counts["BlogCategory"] += 1
            categories[obj.slug] = obj

        for item in SEED_DATA.get("Blog", []):
            defaults = {
                "description": item["description"],
                "likes_count": item.get("likes_count", 0),
                "is_published": item.get("is_published", True),
                "published_at": self._parse_dt(item.get("published_at")),
            }
            obj, created = Blog.objects.get_or_create(name=item["name"], defaults=defaults)
            if created:
                created_counts["Blog"] += 1

            category_slugs = item.get("categories", [])
            category_objs = [categories[slug] for slug in category_slugs if slug in categories]
            if category_objs:
                obj.categories.set(category_objs)

        summary = ", ".join(
            f"{model}: {count} created" for model, count in created_counts.items()
        )
        self.stdout.write(self.style.SUCCESS(f"Seed complete. {summary}."))
