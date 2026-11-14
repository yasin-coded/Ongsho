"""In-memory PDF builders for monthly statements (ReportLab)."""

from __future__ import annotations

import io
from decimal import Decimal
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.money import quantize_money

# Helvetica cannot render the BDT taka sign (৳); amounts use the "BDT 1,200.00" prefix instead.


def _e(text) -> str:
    return xml_escape(str(text if text is not None else ""))


def format_bdt_plain(value) -> str:
    amount = quantize_money(Decimal(str(value)))
    sign = "-" if amount < 0 else ""
    return f"BDT {sign}{abs(amount):,.2f}"


def _money(value) -> str:
    return _e(format_bdt_plain(value))


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "StmtTitle",
            parent=base["Heading1"],
            fontSize=16,
            spaceAfter=6,
        ),
        "meta": ParagraphStyle(
            "StmtMeta",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
        ),
        "body": ParagraphStyle(
            "StmtBody",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
        ),
        "footer": ParagraphStyle(
            "StmtFooter",
            parent=base["Normal"],
            fontSize=8,
            leading=11,
            textColor=colors.grey,
        ),
        "section": ParagraphStyle(
            "StmtSection",
            parent=base["Heading2"],
            fontSize=11,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "page": ParagraphStyle(
            "StmtPage",
            parent=base["Normal"],
            fontSize=8,
            alignment=TA_CENTER,
        ),
    }


def _page_callbacks(compress: bool):
    def on_page(canvas, doc):
        canvas.setPageCompression(1 if compress else 0)
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawCentredString(A4[0] / 2, 12 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return on_page, on_page


def _header_block(data: dict, styles) -> list:
    lines = [
        f"<b>{_e(data['brand'])}</b>",
        f"Statement {_e(data['number'])}",
        f"Plan: {_e(data['plan_name'])}",
        f"Month: {_e(data['month_label'])} ({_e(data['month'])})",
        f"Generated: {_e(data['generated_at'])}",
        f"Prepared for: {_e(data['viewer_name'])}",
    ]
    return [Paragraph("<br/>".join(lines), styles["meta"]), Spacer(1, 6 * mm)]


def _table(data_rows: list[list], col_widths, repeat_rows: int = 1) -> Table:
    tbl = Table(data_rows, colWidths=col_widths, repeatRows=repeat_rows)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
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


def _ious_section(ious: list[dict], styles) -> list:
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
    out.append(_table(rows, [55 * mm, 55 * mm, 35 * mm]))
    return out


def build_owner_statement(data: dict, compress: bool = True) -> bytes:
    styles = _styles()
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
    story.extend(_ious_section(data.get("ious") or [], styles))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(_e(data["footer"]), styles["footer"]))
    first, later = _page_callbacks(compress)
    doc.build(story, onFirstPage=first, onLaterPages=later)
    return buf.getvalue()


def build_member_statement(data: dict, compress: bool = True) -> bytes:
    styles = _styles()
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
        story.append(Paragraph("Your dues this month", styles["section"]))
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
        story.append(_table(rows, [24 * mm, 18 * mm, 22 * mm, 32 * mm, 20 * mm, 42 * mm]))
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
        story.append(_table(rows, [32 * mm, 22 * mm, 18 * mm, 22 * mm, 32 * mm, 20 * mm]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"Total you paid: {_money(data['total_paid'])}", styles["body"]))
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
        story.append(_table(rows, [55 * mm, 35 * mm, 45 * mm]))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(_e(data["footer"]), styles["footer"]))
    first, later = _page_callbacks(compress)
    doc.build(story, onFirstPage=first, onLaterPages=later)
    return buf.getvalue()
