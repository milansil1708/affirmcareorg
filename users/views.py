from django.contrib import messages
from django.contrib.auth import login, logout
from django.views.decorators.http import require_POST
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import LoginForm, ProviderRegistrationForm


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    form = LoginForm(request=request, data=request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            login(request, form.get_user())
            next_url = request.POST.get("next") or request.GET.get("next")
            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect("home")
        messages.error(request, "Login failed. Please check the form and try again.")

    return render(request, "users/login.html", {"form": form})


def register_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    form = ProviderRegistrationForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Registration successful. You can now log in.",
            )
            return redirect("users:login")
        messages.error(
            request,
            "Registration failed. Please correct the errors below.",
        )

    return render(request, "users/register.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("home")

