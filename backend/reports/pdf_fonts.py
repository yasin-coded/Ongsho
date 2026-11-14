"""Register Bahnschrift and resolve statement PDF assets (logo, fonts)."""

from __future__ import annotations

import logging
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
LOGO_PNG = REPO_ROOT / "logo red.png"
FONT_WOFF2_DIR = REPO_ROOT / "frontend/webapp/src/assets/fonts/bahnschrift-woff2"
FONT_TTF_ASSETS = Path(__file__).resolve().parent / "assets" / "fonts"

FONT_REGULAR = "Bahnschrift"
FONT_BOLD = "Bahnschrift-Bold"
FALLBACK_REGULAR = "Helvetica"
FALLBACK_BOLD = "Helvetica-Bold"

_WOFF2_FILES = {
    FONT_REGULAR: "Bahnschrift Regular.woff2",
    FONT_BOLD: "Bahnschrift SemiBold.woff2",
}


def _decompress_woff2(raw: bytes) -> bytes:
    from fontTools.ttLib import woff2

    out = BytesIO()
    woff2.decompress(BytesIO(raw), out)
    return out.getvalue()


def _register_ttf_bytes(name: str, sfnt: bytes) -> None:
    buf = BytesIO(sfnt)
    pdfmetrics.registerFont(TTFont(name, buf))


def _try_register_file(name: str, path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        if path.suffix.lower() == ".woff2":
            _register_ttf_bytes(name, _decompress_woff2(path.read_bytes()))
        else:
            pdfmetrics.registerFont(TTFont(name, str(path)))
        return True
    except Exception:
        logger.exception("Could not register PDF font %s from %s", name, path)
        return False


def _try_windows_bahnschrift(name: str) -> bool:
    win = Path(r"C:\Windows\Fonts\bahnschrift.ttf")
    if name != FONT_REGULAR or not win.is_file():
        return False
    return _try_register_file(name, win)


@lru_cache(maxsize=1)
def pdf_font_names() -> tuple[str, str]:
    """Return (regular, bold) PostScript names for ReportLab."""
    for face, filename in _WOFF2_FILES.items():
        _try_register_file(face, FONT_WOFF2_DIR / filename)

    for face in (FONT_REGULAR, FONT_BOLD):
        if face not in pdfmetrics.getRegisteredFontNames():
            ttf = FONT_TTF_ASSETS / (
                "Bahnschrift-Regular.ttf" if face == FONT_REGULAR else "Bahnschrift-SemiBold.ttf"
            )
            _try_register_file(face, ttf)

    if FONT_REGULAR not in pdfmetrics.getRegisteredFontNames():
        _try_windows_bahnschrift(FONT_REGULAR)
        win = Path(r"C:\Windows\Fonts\bahnschrift.ttf")
        if (
            FONT_BOLD not in pdfmetrics.getRegisteredFontNames()
            and FONT_REGULAR in pdfmetrics.getRegisteredFontNames()
            and win.is_file()
        ):
            _try_register_file(FONT_BOLD, win)

    reg = FONT_REGULAR if FONT_REGULAR in pdfmetrics.getRegisteredFontNames() else FALLBACK_REGULAR
    bold = FONT_BOLD if FONT_BOLD in pdfmetrics.getRegisteredFontNames() else FALLBACK_BOLD
    if reg == FALLBACK_REGULAR:
        logger.warning("Bahnschrift unavailable; statement PDF uses Helvetica.")
    return reg, bold


def statement_logo_path() -> Path | None:
    if LOGO_PNG.is_file():
        return LOGO_PNG
    return None