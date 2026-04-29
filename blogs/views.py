from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from .models import Blog, BlogCategory


def blogs_view(request):
    category_slug = request.GET.get("category", "").strip()

    blogs = Blog.objects.filter(is_published=True).prefetch_related("categories")
    if category_slug:
        blogs = blogs.filter(categories__slug=category_slug)
    blogs = blogs.distinct()

    categories = BlogCategory.objects.annotate(
        published_count=Count("blogs", filter=Q(blogs__is_published=True))
    ).order_by("name")

    context = {
        "blogs": blogs,
        "categories": categories,
        "selected_category": category_slug,
    }
    return render(request, "pages/blogs.html", context)


def blog_detail_view(request, slug):
    blog = get_object_or_404(
        Blog.objects.filter(is_published=True).prefetch_related("categories"),
        slug=slug,
    )
    categories = BlogCategory.objects.annotate(
        published_count=Count("blogs", filter=Q(blogs__is_published=True))
    ).order_by("name")
    recent_posts = (
        Blog.objects.filter(is_published=True)
        .exclude(id=blog.id)
        .order_by("-published_at", "-created_at")[:5]
    )

    context = {
        "blog": blog,
        "categories": categories,
        "recent_posts": recent_posts,
    }
    return render(request, "pages/blog_detail.html", context)
