from __future__ import annotations


class OutboxDeliveryError(Exception):
    """Base delivery failure; never embed secrets in messages."""

    def __init__(self, code: str, *, permanent: bool = False) -> None:
        self.code = code
        self.permanent = permanent
        super().__init__(code)


class OutboxRetryableError(OutboxDeliveryError):
    def __init__(self, code: str, *, retry_after_seconds: int | None = None) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(code, permanent=False)