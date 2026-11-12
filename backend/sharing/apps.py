from django.apps import AppConfig


class SharingConfig(AppConfig):
    name = "sharing"

    def ready(self):
        import sharing.receivers  # noqa: F401
