from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    name = "notifications"

    def ready(self) -> None:
        import notifications.signals  # noqa: F401
