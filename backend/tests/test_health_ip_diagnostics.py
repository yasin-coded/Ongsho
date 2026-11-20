import logging

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

DIAG_HEADER = "HTTP_X_IP_DIAGNOSTICS_TOKEN"
HEALTH_URL = "/api/health/"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def ip_diag_caplog(caplog):
    with caplog.at_level(logging.INFO, logger="ongsho.ip_diag"):
        yield caplog


def test_health_ip_diagnostics_disabled_by_default(client, ip_diag_caplog, settings):
    settings.IP_DIAGNOSTICS_TOKEN = ""
    response = client.get(
        HEALTH_URL,
        **{DIAG_HEADER: "any-token"},
        REMOTE_ADDR="203.0.113.10",
        HTTP_X_FORWARDED_FOR="198.51.100.1, 203.0.113.10",
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert not any("health_ip_diag" in r.message for r in ip_diag_caplog.records)


def test_health_ip_diagnostics_requires_matching_token(client, ip_diag_caplog, settings):
    settings.IP_DIAGNOSTICS_TOKEN = "diag-secret"
    response = client.get(
        HEALTH_URL,
        **{DIAG_HEADER: "wrong-token"},
        REMOTE_ADDR="203.0.113.10",
    )
    assert response.status_code == 200
    assert not any("health_ip_diag" in r.message for r in ip_diag_caplog.records)


def test_health_ip_diagnostics_logs_when_token_matches(client, ip_diag_caplog, settings):
    settings.IP_DIAGNOSTICS_TOKEN = "diag-secret"
    settings.NUM_PROXIES = 1
    response = client.get(
        HEALTH_URL,
        **{
            DIAG_HEADER: "diag-secret",
            "REMOTE_ADDR": "203.0.113.10",
            "HTTP_X_FORWARDED_FOR": "198.51.100.1, 203.0.113.10",
            "HTTP_X_REAL_IP": "198.51.100.2",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    diag_records = [r for r in ip_diag_caplog.records if "health_ip_diag" in r.message]
    assert len(diag_records) == 1
    message = diag_records[0].getMessage()
    assert "remote_addr=203.0.113.10" in message
    assert "http_x_forwarded_for=198.51.100.1, 203.0.113.10" in message
    assert "http_x_real_ip=198.51.100.2" in message
    assert "xff_entry_count=2" in message
    assert "num_proxies=1" in message
    # NUM_PROXIES=1 with two XFF hops selects index 1 (matches client_ip() today).
    assert "client_ip=203.0.113.10" in message
    assert "diag-secret" not in message


def test_health_ip_diagnostics_never_in_response_body(client, settings):
    settings.IP_DIAGNOSTICS_TOKEN = "diag-secret"
    response = client.get(
        HEALTH_URL,
        **{
            DIAG_HEADER: "diag-secret",
            "REMOTE_ADDR": "203.0.113.10",
            "HTTP_X_FORWARDED_FOR": "198.51.100.1, 203.0.113.10",
            "HTTP_X_REAL_IP": "198.51.100.2",
        },
    )
    body_text = response.content.decode()
    assert body_text == '{"status":"ok"}'
    for fragment in ("203.0.113.10", "198.51.100.1", "198.51.100.2", "diag-secret", "xff_entry_count"):
        assert fragment not in body_text