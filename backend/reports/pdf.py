"""In-memory PDF builders for monthly statements (ReportLab)."""

from __future__ import annotations

import io
from decimal import Decimal
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.money import quantize_money
from reports.pdf_fonts import pdf_font_names, statement_logo_path

# Helvetica cannot render the BDT taka sign (৳); amounts use the "BDT 1,200.00" prefix instead.

LOGO_ASPECT = 200.06 / 784.9  # Logo_red.svg viewBox
BRAND_RED = colors.HexColor("#be2126")


def _e(text) -> str:
    return xml_escape(str(text if text is not None else ""))


def format_bdt_plain(value) -> str:
    amount = quantize_money(Decimal(str(value)))
    sign = "-" if amount < 0 else ""
    return f"BDT {sign}{abs(amount):,.2f}"


def _money(value) -> str:
    return _e(format_bdt_plain(value))


def _styles():
    reg, bold = pdf_font_names()
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "StmtTitle",
            parent=base["Heading1"],
            fontName=bold,
            fontSize=16,
            spaceAfter=6,
        ),
        "meta": ParagraphStyle(
            "StmtMeta",
            parent=base["Normal"],
            fontName=reg,
            fontSize=10,
            leading=14,
        ),
        "meta_header": ParagraphStyle(
            "StmtMetaHeader",
            parent=base["Normal"],
            fontName=reg,
            fontSize=10,
            leading=14,
            alignment=TA_RIGHT,
        ),
        "body": ParagraphStyle(
            "StmtBody",
            parent=base["Normal"],
            fontName=reg,
            fontSize=9,
            leading=12,
        ),
        "footer": ParagraphStyle(
            "StmtFooter",
            parent=base["Normal"],
            fontName=reg,
            fontSize=8,
            leading=11,
            textColor=colors.grey,
        ),
        "section": ParagraphStyle(
            "StmtSection",
            parent=base["Heading2"],
            fontName=bold,
            fontSize=11,
            spaceBefore=8,
            spaceAfter=4,
            textColor=BRAND_RED,
        ),
        "page": ParagraphStyle(
            "StmtPage",
            parent=base["Normal"],
            fontName=reg,
            fontSize=8,
            alignment=TA_CENTER,
        ),
    }, reg, bold


def _page_callbacks(compress: bool, font_regular: str):
    def on_page(canvas, doc):
        canvas.setPageCompression(1 if compress else 0)
        canvas.saveState()
        canvas.setFont(font_regular, 8)
        canvas.drawCentredString(A4[0] / 2, 12 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return on_page, on_page


def _logo_flowable() -> Image | None:
    path = statement_logo_path()
    if path is None:
        return None
    width = 48 * mm
    height = width * LOGO_ASPECT
    return Image(str(path), width=width, height=height)


def _header_block(data: dict, styles) -> list:
    meta_lines = [
        f"<b>Statement number</b> {_e(data['number'])}",
        f"<b>Plan:</b> {_e(data['plan_name'])}",
        f"<b>Month:</b> {_e(data['month_label'])} ({_e(data['month'])})",
        f"<b>Generated:</b> {_e(data['generated_at'])}",
        f"<b>Prepared for:</b> {_e(data['viewer_name'])}",
    ]
    meta = Paragraph("<br/>".join(meta_lines), styles["meta_header"])
    logo = _logo_flowable()
    if logo is None:
        return [meta, Spacer(1, 6 * mm)]

    content_width = A4[0] - 36 * mm
    logo_col = 48 * mm
    meta_col = content_width - logo_col
    tbl = Table(
        [[logo, meta]],
        colWidths=[logo_col, meta_col],
        hAlign="LEFT",
    )
    tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
                ("LEFTPADDING", (1, 0), (1, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return [tbl, Spacer(1, 6 * mm)]


def _table(data_rows: list[list], col_widths, repeat_rows: int = 1, *, font_bold: str, font_regular: str) -> Table:
    tbl = Table(data_rows, colWidths=col_widths, repeatRows=repeat_rows)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("FONTNAME", (0, 0), (-1, 0), font_bold),
                ("FONTNAME", (0, 1), (-1, -1), font_regular),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return tbl


def _ious_section(ious: list[dict], styles, *, font_bold: str, font_regular: str) -> list:
    if not ious:
        return []
    out = [Paragraph("IOUs at end of month", styles["section"])]
    rows = [["Debtor", "Creditor", "Amount"]]
    for row in ious:
        rows.append(
            [
                Paragraph(_e(row["debtor"]["name"]), styles["body"]),
                Paragraph(_e(row["creditor"]["name"]), styles["body"]),
                Paragraph(_money(row["amount"]), styles["body"]),
            ]
        )
    out.append(_table(rows, [55 * mm, 55 * mm, 35 * mm], font_bold=font_bold, font_regular=font_regular))
    return out


def build_owner_statement(data: dict, compress: bool = True) -> bytes:
    styles, font_regular, font_bold = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title=f"Ongsho statement {data.get('number', '')}",
    )
    story = _header_block(data, styles)
    story.append(Paragraph("Dues this month", styles["section"]))
    header = [
        "Member",
        "Amount",
        "Status",
        "Method",
        "Transaction ID",
        "Paid",
        "Notes",
    ]
    rows = [header]
    for row in data["rows"]:
        rows.append(
            [
                Paragraph(_e(row["member_name"]), styles["body"]),
                Paragraph(_money(row["amount"]), styles["body"]),
                Paragraph(_e(row["status"]), styles["body"]),
                Paragraph(_e(row["method"]), styles["body"]),
                Paragraph(_e(row["transaction_id"]), styles["body"]),
                Paragraph(_e(row["paid_on"]), styles["body"]),
                Paragraph(_e(row["notes"]), styles["body"]),
            ]
        )
    story.append(
        _table(
            rows,
            [32 * mm, 22 * mm, 16 * mm, 20 * mm, 28 * mm, 18 * mm, 30 * mm],
            font_bold=font_bold,
            font_regular=font_regular,
        )
    )
    totals = data["totals"]
    story.append(Spacer(1, 4 * mm))
    story.append(
        Paragraph(
            " | ".join(
                f"{key.capitalize()}: {_money(totals[key])}"
                for key in ("paid", "pending", "due", "waived", "all")
            ),
            styles["body"],
        )
    )
    story.extend(_ious_section(data.get("ious") or [], styles, font_bold=font_bold, font_regular=font_regular))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(_e(data["footer"]), styles["footer"]))
    first, later = _page_callbacks(compress, font_regular)
    doc.build(story, onFirstPage=first, onLaterPages=later)
    return buf.getvalue()


def build_member_statement(data: dict, compress: bool = True) -> bytes:
    styles, font_regular, font_bold = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title=f"Ongsho statement {data.get('number', '')}",
    )
    story = _header_block(data, styles)
    if data.get("own_rows"):
        story.append(Paragraph("Your Dues this month", styles["section"]))
        rows = [["Amount", "Status", "Method", "Transaction ID", "Paid", "Notes"]]
        for row in data["own_rows"]:
            rows.append(
                [
                    Paragraph(_money(row["amount"]), styles["body"]),
                    Paragraph(_e(row["status"]), styles["body"]),
                    Paragraph(_e(row["method"]), styles["body"]),
                    Paragraph(_e(row["transaction_id"]), styles["body"]),
                    Paragraph(_e(row["paid_on"]), styles["body"]),
                    Paragraph(_e(row["notes"]), styles["body"]),
                ]
            )
        story.append(
            _table(
                rows,
                [24 * mm, 18 * mm, 22 * mm, 32 * mm, 20 * mm, 42 * mm],
                font_bold=font_bold,
                font_regular=font_regular,
            )
        )
    if data.get("cover_rows"):
        story.append(Paragraph("Payments you made for others", styles["section"]))
        rows = [["Member", "Amount", "Status", "Method", "Transaction ID", "Paid"]]
        for row in data["cover_rows"]:
            rows.append(
                [
                    Paragraph(_e(row["member_name"]), styles["body"]),
                    Paragraph(_money(row["amount"]), styles["body"]),
                    Paragraph(_e(row["status"]), styles["body"]),
                    Paragraph(_e(row["method"]), styles["body"]),
                    Paragraph(_e(row["transaction_id"]), styles["body"]),
                    Paragraph(_e(row["paid_on"]), styles["body"]),
                ]
            )
        story.append(
            _table(
                rows,
                [32 * mm, 22 * mm, 18 * mm, 22 * mm, 32 * mm, 20 * mm],
                font_bold=font_bold,
                font_regular=font_regular,
            )
        )
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"<b>Total you paid:</b> {_money(data['total_paid'])}", styles["body"]))
    member_ious = data.get("ious") or []
    if member_ious:
        story.append(Paragraph("Your IOUs", styles["section"]))
        rows = [["Other", "Amount", "Direction"]]
        for row in member_ious:
            direction = "You owe" if row["you_owe"] else "They owe you"
            rows.append(
                [
                    Paragraph(_e(row["other"]["name"]), styles["body"]),
                    Paragraph(_money(row["amount"]), styles["body"]),
                    Paragraph(_e(direction), styles["body"]),
                ]
            )
        story.append(
            _table(
                rows,
                [55 * mm, 35 * mm, 45 * mm],
                font_bold=font_bold,
                font_regular=font_regular,
            )
        )
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(_e(data["footer"]), styles["footer"]))
    first, later = _page_callbacks(compress, font_regular)
    doc.build(story, onFirstPage=first, onLaterPages=later)
    return buf.getvalue()