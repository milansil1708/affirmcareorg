from django.urls import path

from . import views

urlpatterns = [
    path("", views.blogs_view, name="blogs"),
    path("<slug:slug>/", views.blog_detail_view, name="blog_detail"),
]
