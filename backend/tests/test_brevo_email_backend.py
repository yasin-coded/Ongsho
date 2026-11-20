import base64
import json
import ssl
import urllib.error
from io import BytesIO
from unittest import mock

import pytest
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.test import override_settings

from config.settings import _brevo_api_timeout
from core.email_backends.brevo import (
    BrevoEmailBackend,
    BrevoEmailError,
    build_brevo_payload,
)

pytestmark = pytest.mark.django_db

FAKE_KEY = "xkeysib-test-key-not-real-abc12345"


class _FakeResponse:
    def __init__(self, status: int):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def brevo_settings():
    with override_settings(
        BREVO_API_KEY=FAKE_KEY,
        BREVO_API_TIMEOUT=10,
        DEFAULT_FROM_EMAIL="Ongsho <sender@example.com>",
    ):
        yield


def _last_request_body(mock_urlopen):
    call = mock_urlopen.call_args
    request = call[0][0]
    return json.loads(request.data.decode("utf-8"))


def test_successful_submission(brevo_settings):
    with mock.patch("core.email_backends.brevo.urlopen", return_value=_FakeResponse(201)) as mocked:
        backend = BrevoEmailBackend()
        msg = EmailMultiAlternatives(
            subject="Verify",
            body="plain",
            from_email="Ongsho <sender@example.com>",
            to=["one@example.com", "two@example.com"],
        )
        assert backend.send_messages([msg]) == 1

    request = mocked.call_args[0][0]
    assert request.full_url == "https://api.brevo.com/v3/smtp/email"
    assert request.get_method() == "POST"
    headers = {k.lower(): v for k, v in request.header_items()}
    assert headers["api-key"] == FAKE_KEY
    assert headers["content-type"] == "application/json"

    body = _last_request_body(mocked)
    assert body["subject"] == "Verify"
    assert body["textContent"] == "plain"
    assert body["sender"] == {"email": "sender@example.com", "name": "Ongsho"}
    assert len(body["to"]) == 2
    assert {r["email"] for r in body["to"]} == {"one@example.com", "two@example.com"}


def test_html_alternative(brevo_settings):
    with mock.patch("core.email_backends.brevo.urlopen", return_value=_FakeResponse(201)) as mocked:
        backend = BrevoEmailBackend()
        msg = EmailMultiAlternatives(
            subject="Hi",
            body="text",
            from_email="sender@example.com",
            to=["a@example.com"],
        )
        msg.attach_alternative("<p>html</p>", "text/html")
        assert backend.send_messages([msg]) == 1

    body = _last_request_body(mocked)
    assert body["textContent"] == "text"
    assert body["htmlContent"] == "<p>html</p>"


def test_cc_bcc_reply_to(brevo_settings):
    with mock.patch("core.email_backends.brevo.urlopen", return_value=_FakeResponse(201)) as mocked:
        backend = BrevoEmailBackend()
        msg = EmailMultiAlternatives(
            subject="Hi",
            body="text",
            from_email="sender@example.com",
            to=["a@example.com"],
            cc=["cc@example.com"],
            bcc=["bcc@example.com"],
            reply_to=["reply@example.com"],
        )
        assert backend.send_messages([msg]) == 1

    body = _last_request_body(mocked)
    assert body["cc"][0]["email"] == "cc@example.com"
    assert body["bcc"][0]["email"] == "bcc@example.com"
    assert body["replyTo"]["email"] == "reply@example.com"


def test_attachment_tuple(brevo_settings):
    with mock.patch("core.email_backends.brevo.urlopen", return_value=_FakeResponse(201)) as mocked:
        backend = BrevoEmailBackend()
        msg = EmailMultiAlternatives(
            subject="File",
            body="see attached",
            from_email="sender@example.com",
            to=["a@example.com"],
        )
        msg.attach("hello.txt", b"hello world", "text/plain")
        assert backend.send_messages([msg]) == 1

    body = _last_request_body(mocked)
    assert body["attachment"][0]["name"] == "hello.txt"
    assert "content" in body["attachment"][0]


def test_missing_api_key_fail_silent_false(brevo_settings):
    with override_settings(BREVO_API_KEY=""):
        backend = BrevoEmailBackend(fail_silently=False)
        msg = EmailMultiAlternatives(
            subject="Hi",
            body="text",
            from_email="sender@example.com",
            to=["a@example.com"],
        )
        with pytest.raises(BrevoEmailError, match="API key"):
            backend.send_messages([msg])


def test_missing_api_key_fail_silent_true(brevo_settings):
    with override_settings(BREVO_API_KEY=""):
        backend = BrevoEmailBackend(fail_silently=True)
        msg = EmailMultiAlternatives(
            subject="Hi",
            body="text",
            from_email="sender@example.com",
            to=["a@example.com"],
        )
        assert backend.send_messages([msg]) == 0


def test_brevo_http_error(brevo_settings):
    err = urllib.error.HTTPError(
        url="https://api.brevo.com/v3/smtp/email",
        code=400,
        msg="Bad Request",
        hdrs=None,
        fp=BytesIO(b'{"message":"bad"}'),
    )

    def _raise(_request, timeout=0):
        raise err

    with mock.patch("core.email_backends.brevo.urlopen", side_effect=_raise):
        backend = BrevoEmailBackend(fail_silently=False)
        msg = EmailMultiAlternatives(
            subject="Hi",
            body="text",
            from_email="sender@example.com",
            to=["a@example.com"],
        )
        with pytest.raises(BrevoEmailError, match="HTTP 400"):
            backend.send_messages([msg])


def test_network_timeout_fail_silent(brevo_settings):
    with mock.patch("core.email_backends.brevo.urlopen", side_effect=urllib.error.URLError("timed out")):
        backend = BrevoEmailBackend(fail_silently=True)
        msg = EmailMultiAlternatives(
            subject="Hi",
            body="text",
            from_email="sender@example.com",
            to=["a@example.com"],
        )
        assert backend.send_messages([msg]) == 0


def test_network_timeout_fail_loud(brevo_settings):
    with mock.patch("core.email_backends.brevo.urlopen", side_effect=urllib.error.URLError("timed out")):
        backend = BrevoEmailBackend(fail_silently=False)
        msg = EmailMultiAlternatives(
            subject="Hi",
            body="text",
            from_email="sender@example.com",
            to=["a@example.com"],
        )
        with pytest.raises(BrevoEmailError, match="request failed"):
            backend.send_messages([msg])


def test_no_api_key_leak_in_exception(brevo_settings):
    secret = "xkeysib-supersecret-should-not-appear"
    with override_settings(BREVO_API_KEY=secret):
        backend = BrevoEmailBackend(fail_silently=False)
        msg = EmailMultiAlternatives(
            subject="Hi",
            body="text",
            from_email="sender@example.com",
            to=["a@example.com"],
        )
        with mock.patch("core.email_backends.brevo.urlopen", side_effect=urllib.error.URLError("down")):
            with pytest.raises(BrevoEmailError) as exc:
                backend.send_messages([msg])
        assert secret not in str(exc.value)
        assert "xkeysib" not in str(exc.value)


def test_build_payload_uses_default_from():
    msg = EmailMultiAlternatives(subject="S", body="B", to=["t@example.com"])
    payload = build_brevo_payload(msg)
    assert "@" in payload["sender"]["email"]


def test_file_path_attachment_not_supported():
    msg = EmailMultiAlternatives(
        subject="S",
        body="B",
        from_email="a@example.com",
        to=["t@example.com"],
    )
    msg.attachments = ["doc.pdf"]
    with pytest.raises(ValueError, match="File-path"):
        build_brevo_payload(msg)


def test_send_messages_empty_list(brevo_settings):
    backend = BrevoEmailBackend()
    assert backend.send_messages([]) == 0


def test_plain_text_only_payload():
    payload = build_brevo_payload(
        EmailMultiAlternatives(
            subject="S",
            body="plain only",
            from_email="a@example.com",
            to=["t@example.com"],
        )
    )
    assert payload["textContent"] == "plain only"
    assert "htmlContent" not in payload


def test_html_only_email_message():
    msg = EmailMessage(subject="S", body="<p>hi</p>", to=["t@example.com"])
    msg.content_subtype = "html"
    payload = build_brevo_payload(msg)
    assert payload["htmlContent"] == "<p>hi</p>"
    assert "textContent" not in payload


def test_multiple_html_alternatives_uses_first():
    msg = EmailMultiAlternatives(
        subject="S",
        body="plain",
        from_email="a@example.com",
        to=["t@example.com"],
    )
    msg.attach_alternative("<p>one</p>", "text/html")
    msg.attach_alternative("<p>two</p>", "text/html")
    payload = build_brevo_payload(msg)
    assert payload["htmlContent"] == "<p>one</p>"
    assert payload["textContent"] == "plain"


def test_ignores_non_html_alternatives():
    msg = EmailMultiAlternatives(
        subject="S",
        body="plain",
        from_email="a@example.com",
        to=["t@example.com"],
    )
    msg.attach_alternative("BEGIN:VCALENDAR", "text/calendar")
    payload = build_brevo_payload(msg)
    assert payload["textContent"] == "plain"
    assert "htmlContent" not in payload


def test_empty_body_raises():
    msg = EmailMultiAlternatives(
        subject="S",
        body="",
        from_email="a@example.com",
        to=["t@example.com"],
    )
    with pytest.raises(ValueError, match="no text or HTML"):
        build_brevo_payload(msg)


def test_reply_to_uses_first_address_only():
    msg = EmailMultiAlternatives(
        subject="S",
        body="b",
        from_email="a@example.com",
        to=["t@example.com"],
        reply_to=["first@example.com", "second@example.com"],
    )
    payload = build_brevo_payload(msg)
    assert payload["replyTo"]["email"] == "first@example.com"


def test_attachment_base64_roundtrip():
    raw = b"binary\xff"
    msg = EmailMultiAlternatives(
        subject="S",
        body="b",
        from_email="a@example.com",
        to=["t@example.com"],
    )
    msg.attach("bin.dat", raw, "application/octet-stream")
    payload = build_brevo_payload(msg)
    assert base64.b64decode(payload["attachment"][0]["content"]) == raw


def test_attachment_invalid_content_type():
    msg = EmailMultiAlternatives(
        subject="S",
        body="b",
        from_email="a@example.com",
        to=["t@example.com"],
    )
    msg.attachments = [("x.bin", object(), "application/octet-stream")]
    with pytest.raises(ValueError, match="bytes or text"):
        build_brevo_payload(msg)


def test_attachment_missing_filename():
    msg = EmailMultiAlternatives(
        subject="S",
        body="b",
        from_email="a@example.com",
        to=["t@example.com"],
    )
    msg.attachments = [("", b"x", "application/octet-stream")]
    with pytest.raises(ValueError, match="filename"):
        build_brevo_payload(msg)


@pytest.mark.parametrize("value", ["-1", "0", "nan", "inf"])
def test_brevo_api_timeout_rejects_invalid(monkeypatch, value):
    monkeypatch.setenv("BREVO_API_TIMEOUT", value)
    with pytest.raises(RuntimeError, match="positive finite"):
        _brevo_api_timeout()


def test_brevo_api_timeout_accepts_positive(monkeypatch):
    monkeypatch.setenv("BREVO_API_TIMEOUT", "15.5")
    assert _brevo_api_timeout() == 15.5


def test_ssl_error_fail_silent(brevo_settings):
    with mock.patch("core.email_backends.brevo.urlopen", side_effect=ssl.SSLError("tls failed")):
        backend = BrevoEmailBackend(fail_silently=True)
        msg = EmailMultiAlternatives(
            subject="Hi",
            body="text",
            from_email="sender@example.com",
            to=["a@example.com"],
        )
        assert backend.send_messages([msg]) == 0


def test_connection_error_raises_generic(brevo_settings):
    with mock.patch("core.email_backends.brevo.urlopen", side_effect=ConnectionResetError("reset")):
        backend = BrevoEmailBackend(fail_silently=False)
        msg = EmailMultiAlternatives(
            subject="Hi",
            body="text",
            from_email="sender@example.com",
            to=["a@example.com"],
        )
        with pytest.raises(BrevoEmailError) as exc:
            backend.send_messages([msg])
        assert "request failed" in str(exc.value)
        assert "reset" not in str(exc.value).lower()