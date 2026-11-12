from django.apps import AppConfig


class DuesConfig(AppConfig):
    name = "dues"

    def ready(self):
        import dues.receivers  # noqa: F401
