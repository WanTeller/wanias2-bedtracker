"""
Developer-only user registry. Everything here is behind /admin/, which is
staff-only - ordinary ward users never see it.
"""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import LoginEvent

User = get_user_model()


class LoginEventInline(admin.TabularInline):
    model = LoginEvent
    extra = 0
    can_delete = False
    readonly_fields = ["at", "ip_address", "user_agent"]
    ordering = ["-at"]

    def has_add_permission(self, request, obj=None):
        return False


admin.site.unregister(User)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ["email", "first_name", "is_active", "is_staff",
                    "last_login", "date_joined", "login_count"]
    list_filter = ["is_active", "is_staff", "is_superuser"]
    search_fields = ["email", "first_name", "username"]
    ordering = ["-date_joined"]
    inlines = [LoginEventInline]

    @admin.display(description="logins")
    def login_count(self, obj):
        return obj.login_events.count()


@admin.register(LoginEvent)
class LoginEventAdmin(admin.ModelAdmin):
    list_display = ["at", "user", "ip_address", "user_agent"]
    list_filter = ["at"]
    search_fields = ["user__email", "user__first_name", "ip_address"]
    readonly_fields = ["user", "at", "ip_address", "user_agent"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
