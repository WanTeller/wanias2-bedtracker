from django.conf import settings

# App branding, kept in one place.
APP_NAME = "WaniaS2 BedTracker"
APP_SUBTITLE = "Surgical Unit 2"


def flags(request):
    return {
        "simple_login": settings.SIMPLE_LOGIN,
        "app_name": APP_NAME,
        "app_subtitle": APP_SUBTITLE,
    }
