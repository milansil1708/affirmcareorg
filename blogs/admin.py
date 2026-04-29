from django import forms
from django.contrib import admin
from tinymce.widgets import TinyMCE

from .models import Blog, BlogCategory


@admin.register(BlogCategory)
class BlogCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "updated_at")
    readonly_fields = ("slug",)
    search_fields = ("name",)
    ordering = ("name",)


class BlogAdminForm(forms.ModelForm):
    description = forms.CharField(widget=TinyMCE())

    class Meta:
        model = Blog
        fields = "__all__"


@admin.register(Blog)
class BlogAdmin(admin.ModelAdmin):
    form = BlogAdminForm
    list_display = ("name", "is_published", "published_at", "updated_at")
    list_filter = ("is_published", "published_at", "categories")
    search_fields = ("name", "description")
    autocomplete_fields = ("categories",)
    readonly_fields = ("slug", "created_at", "updated_at")
    fieldsets = (
        ("Content", {"fields": ("name", "slug", "description", "main_image", "categories")}),
        ("Publishing", {"fields": ("is_published", "published_at", "likes_count")}),
        ("Dates", {"fields": ("created_at", "updated_at")}),
    )
