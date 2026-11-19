"""Temporary production diagnostics for X-Forwarded-For verification (remove after NUM_PROXIES is set)."""

from __future__ import annotations

import hmac
import logging

from django.conf import settings

from core.throttles import client_ip

LOGGER = logging.getLogger("ongsho.ip_diag")
# Request header: X-IP-Diagnostics-Token (never logged).
_META_HEADER = "HTTP_X_IP_DIAGNOSTICS_TOKEN"


def _xff_entry_count(xff: str) -> int:
    if not xff:
        return 0
    return len([part for part in xff.split(",") if part.strip()])


def maybe_log_health_ip_diagnostics(request) -> None:
    configured = (getattr(settings, "IP_DIAGNOSTICS_TOKEN", None) or "").strip()
    if not configured:
        return
    provided = (request.META.get(_META_HEADER) or "").strip()
    if not provided or not hmac.compare_digest(provided, configured):
        return

    remote_addr = request.META.get("REMOTE_ADDR", "") or "-"
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "") or "-"
    x_real_ip = request.META.get("HTTP_X_REAL_IP", "") or "-"
    xff_entry_count = _xff_entry_count(request.META.get("HTTP_X_FORWARDED_FOR", "") or "")
    num_proxies = int(getattr(settings, "NUM_PROXIES", 0) or 0)
    resolved_ip = client_ip(request) or "-"

    LOGGER.info(
        "health_ip_diag remote_addr=%s http_x_forwarded_for=%s http_x_real_ip=%s "
        "xff_entry_count=%s num_proxies=%s client_ip=%s",
        remote_addr,
        x_forwarded_for,
        x_real_ip,
        xff_entry_count,
        num_proxies,
        resolved_ip,
    )