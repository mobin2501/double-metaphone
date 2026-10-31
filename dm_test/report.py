"""Render the PDF report from the run summary and per-case results."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from dm_test.charts import (
    AXIS,
    GRID,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    build_charts,
    false_positive_rate,
)
from dm_test.data import NEGATIVE_VARIANTS
from dm_test.matcher import NO_MAX_LENGTH
from dm_test.metrics import FN, FP, CaseResult

REPORT_FILE = "artifact 3.pdf"

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 18 * mm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

MAX_LISTED = 4  # candidates / codes shown per failure row before "+N more"

_base = getSampleStyleSheet()
STYLES = {
    "title": ParagraphStyle("title", parent=_base["Title"], alignment=TA_LEFT, fontSize=20,
                            leading=24, textColor=colors.HexColor(TEXT_PRIMARY), spaceAfter=4),
    "subtitle": ParagraphStyle("subtitle", parent=_base["Normal"], fontSize=9, leading=12,
                               textColor=colors.HexColor(TEXT_SECONDARY)),
    "h2": ParagraphStyle("h2", parent=_base["Heading2"], fontSize=13, leading=16,
                         textColor=colors.HexColor(TEXT_PRIMARY), spaceBefore=12, spaceAfter=6),
    "body": ParagraphStyle("body", parent=_base["Normal"], fontSize=9.5, leading=13.5,
                           textColor=colors.HexColor(TEXT_PRIMARY), spaceAfter=6),
    "bullet": ParagraphStyle("bullet", parent=_base["Normal"], fontSize=9.5, leading=13.5,
                             leftIndent=10, bulletIndent=0, textColor=colors.HexColor(TEXT_PRIMARY)),
    "cell": ParagraphStyle("cell", parent=_base["Normal"], fontSize=7.5, leading=9.5,
                           textColor=colors.HexColor(TEXT_PRIMARY)),
    "tile_label": ParagraphStyle("tile_label", parent=_base["Normal"], fontSize=8, leading=10,
                                 textColor=colors.HexColor(TEXT_SECONDARY)),
    "tile_value": ParagraphStyle("tile_value", parent=_base["Normal"], fontName="Helvetica-Bold",
                                 fontSize=18, leading=22, textColor=colors.HexColor(TEXT_PRIMARY)),
}

TABLE_STYLE = TableStyle([
    ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(TEXT_PRIMARY)),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(TEXT_SECONDARY)),
    ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor(AXIS)),
    ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor(GRID)),
    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 3),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
])


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _listed(items, limit: int = MAX_LISTED) -> str:
    items = list(items)
    if not items:
        return "(none)"
    shown = ", ".join(items[:limit])
    return shown if len(items) <= limit else f"{shown} +{len(items) - limit} more"


def _p(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, STYLES[style])


def _bullet(text: str) -> Paragraph:
    return Paragraph(text, STYLES["bullet"], bulletText="\u2022")


def _cell(text: str) -> Paragraph:
    return Paragraph(escape(text), STYLES["cell"])


def length_ranges(lengths) -> str:
    """Compress lengths into ranges, e.g. [2, 3, 4, 7] -> "2-4, 7", so gaps are never hidden."""
    runs: list[list[int]] = []
    for n in sorted(lengths):
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in runs) or "n/a"


def _lengths_phrase(lengths: list[int]) -> str:
    if len(lengths) == 1:
        return f"length {lengths[0]}"
    *rest, last = sorted(lengths)
    return f"lengths {', '.join(map(str, rest))} and {last}"


def max_length_phrase(max_length: int) -> str:
    if max_length == NO_MAX_LENGTH:
        return "max_length -1 (no limit, the library default)"
    return f"max_length {max_length}"


def _table(rows: list[list], col_widths: list[float], left_align_cols: int = 1) -> Table:
    table = Table(rows, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    style = TableStyle(TABLE_STYLE.getCommands())
    style.add("ALIGN", (0, 0), (left_align_cols - 1, -1), "LEFT")
    table.setStyle(style)
    return table


# --- sections ----------------------------------------------------------------

def takeaway(summary: dict) -> str:
    """Plain-English headline built only from the run's numbers."""
    o = summary["overall"]
    positives, negatives = o["tp"] + o["fn"], o["fp"] + o["tn"]
    parts = []
    if positives:
        found = f"<b>{o['tp']} of {positives}</b>"
        parts.append(f"Double Metaphone found the intended name for {found} positive queries "
                     f"(recall {pct(o['recall'])}).")
    if negatives:
        matched = f"<b>{o['fp']} of {negatives}</b>"
        parts.append(f"{matched} negative queries matched at least one name "
                     f"(false-positive rate {pct(false_positive_rate(o['specificity']))}).")
    parts.append(f"Each query returned {num(o['mean_candidates'])} names on average.")

    by_length = summary["by_length"]
    # Ties are all named, so the sentence holds for every length it lists.
    scored = {int(k): s["recall"] for k, s in by_length.items() if s["recall"] is not None}
    if scored:
        worst_recall = min(scored.values())
        worst = [k for k, v in scored.items() if v == worst_recall]
        parts.append(f"Recall was lowest at {_lengths_phrase(worst)} ({pct(worst_recall)}).")
    fprs = {int(k): false_positive_rate(s["specificity"]) for k, s in by_length.items()
            if s["specificity"] is not None}
    if fprs:
        worst_fpr = max(fprs.values())
        if worst_fpr > 0:
            peaks = [k for k, v in fprs.items() if v == worst_fpr]
            parts.append(f"False positives peaked at {_lengths_phrase(peaks)} ({pct(worst_fpr)}).")
    return " ".join(parts)


def _kpi_tiles(overall: dict) -> Table:
    tiles = [
        ("Recall", overall["recall"]),
        ("Precision", overall["precision"]),
        ("F1", overall["f1"]),
        ("Specificity", overall["specificity"]),
        ("Accuracy", overall["accuracy"]),
    ]
    row = [[_p(label, "tile_label"), _p(pct(value), "tile_value")] for label, value in tiles]
    table = Table([row], colWidths=[CONTENT_WIDTH / len(tiles)] * len(tiles), hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(GRID)),
        ("LINEAFTER", (0, 0), (-2, -1), 0.6, colors.HexColor(GRID)),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _dataset_section(summary: dict, results: list[CaseResult]) -> list:
    d = summary["dataset"]
    variants = Counter((r.case_type, r.variant_type) for r in results)
    rows = [["Case type", "Variant type", "Cases"]]
    rows += [[ct, vt, str(n)] for (ct, vt), n in sorted(variants.items())]
    span = length_ranges(int(k) for k in summary["by_length"])
    return [
        _p("Dataset", "h2"),
        _p(f"{d['names']} reference names; {d['cases']} test queries ({d['positives']} positive, "
           f"{d['negatives']} negative) across query lengths {span}."),
        _table(rows, [40 * mm, 50 * mm, 20 * mm], left_align_cols=2),
    ]


def _confusion_section(overall: dict) -> list:
    rows = [
        ["", "Matched", "Not matched"],
        ["Positive (should match)", f"TP {overall['tp']}", f"FN {overall['fn']}"],
        ["Negative (should not match)", f"FP {overall['fp']}", f"TN {overall['tn']}"],
    ]
    return [
        _p("Confusion matrix", "h2"),
        _p("A positive counts as matched only if its <i>intended</i> name is among the results. "
           "A negative counts as matched if <i>any</i> name is returned."),
        _table(rows, [55 * mm, 30 * mm, 30 * mm]),
    ]


def _summary_rows(label_header: str, groups: dict) -> list[list[str]]:
    rows = [[label_header, "N", "TP", "FN", "FP", "TN", "Recall", "FPR", "Precision", "F1", "Avg names"]]
    for label, s in groups.items():
        rows.append([
            str(label), str(s["n"]), str(s["tp"]), str(s["fn"]), str(s["fp"]), str(s["tn"]),
            pct(s["recall"]), pct(false_positive_rate(s["specificity"])), pct(s["precision"]),
            pct(s["f1"]), num(s["mean_candidates"]),
        ])
    return rows


SUMMARY_COL_WIDTHS = [30 * mm] + [11 * mm] * 5 + [17 * mm] * 3 + [14 * mm, 21 * mm]


def _chart(path: Path) -> Image:
    width = CONTENT_WIDTH
    return Image(str(path), width=width, height=width * 3.2 / 7.0)


def noise_note(summary: dict) -> str:
    """Explain how much one case moves a per-length rate, from the actual bucket sizes."""
    splits = {(s["tp"] + s["fn"], s["fp"] + s["tn"]) for s in summary["by_length"].values()}
    if len(splits) == 1:
        positives, negatives = splits.pop()
        if positives and negatives:
            return (f"Each length has {positives + negatives} queries ({positives} positive, {negatives} negative), "
                    f"so a single case moves recall by ~{100 / positives:.0f} points and the false-positive "
                    f"rate by ~{100 / negatives:.0f} points. Read the trend, not individual points.")
    sizes = [s["n"] for s in summary["by_length"].values()]
    return (f"Lengths have between {min(sizes, default=0)} and {max(sizes, default=0)} queries, so per-length "
            "rates are noisy. Read the trend, not individual points.")


def _length_section(summary: dict, chart: Path) -> list:
    return [
        _p("Accuracy by query length", "h2"),
        _p(noise_note(summary)),
        _chart(chart),
        Spacer(1, 4),
        _table(_summary_rows("Length", summary["by_length"]), SUMMARY_COL_WIDTHS),
    ]


def _overmatch_section(summary: dict, chart: Path) -> list:
    o = summary["overall"]
    return [
        _p("Over-matching", "h2"),
        _p(f"Matching returns every list name that shares a Double Metaphone code with the query. "
           f"Across all queries it returned {num(o['mean_candidates'])} names on average. "
           f"When the intended name was found, it made up {pct(o['candidate_precision'])} of the returned "
           f"names on average (candidate precision; 100% means it was the only match)."),
        _chart(chart),
    ]


def _variant_section(summary: dict) -> list:
    negatives = sorted(v for v in summary["by_variant"] if v in NEGATIVE_VARIANTS)
    scope = f" ({', '.join(negatives)})" if negatives else ""
    return [
        _p("Accuracy by variant type", "h2"),
        _p(f"Recall applies to positive variant types; FPR applies to negative ones{scope}."),
        _table(_summary_rows("Variant", summary["by_variant"]), SUMMARY_COL_WIDTHS),
    ]


def _failure_section(results: list[CaseResult], encode: Callable[[str], frozenset[str]]) -> list:
    misses = [r for r in results if r.outcome == FN]
    false_hits = [r for r in results if r.outcome == FP]
    out = [_p("Failures", "h2")]

    out.append(_p(f"<b>False negatives ({len(misses)})</b>: the intended name was not returned. "
                  "Codes show why: a match needs at least one shared code."))
    if misses:
        rows = [["Case", "Query", "Expected", "Returned instead", "Query codes", "Expected codes"]]
        for r in misses:
            rows.append([
                _cell(r.case_id), _cell(r.query), _cell(r.expected_match or ""),
                _cell(_listed(r.candidates)),
                _cell(_listed(sorted(encode(r.query)))),
                _cell(_listed(sorted(encode(r.expected_match or "")))),
            ])
        out.append(_table(rows, [15 * mm, 27 * mm, 27 * mm, 34 * mm, 35 * mm, 35 * mm], left_align_cols=6))
    out.append(Spacer(1, 8))

    out.append(_p(f"<b>False positives ({len(false_hits)})</b>: a query that should match nothing "
                  "returned one or more names."))
    if false_hits:
        rows = [["Case", "Query", "Variant", "Names returned", "Count"]]
        for r in false_hits:
            rows.append([
                _cell(r.case_id), _cell(r.query), _cell(r.variant_type),
                _cell(_listed(r.candidates, limit=8)), str(len(r.candidates)),
            ])
        out.append(_table(rows, [15 * mm, 35 * mm, 25 * mm, 85 * mm, 14 * mm], left_align_cols=4))
    return out


def _bucket_sizes(summary: dict) -> str:
    sizes = sorted({s["n"] for s in summary["by_length"].values()})
    if len(sizes) <= 1:
        return f"{sizes[0] if sizes else 0} queries"
    return f"{sizes[0]} to {sizes[-1]} queries"


def _method_section(summary: dict) -> list:
    config = summary["config"]
    max_length = config["max_length"]
    truncation = (
        "Codes were not truncated."
        if max_length == NO_MAX_LENGTH else
        f"Codes were cut to {max_length} characters, so two names whose codes share their first "
        f"{max_length} characters match even when the rest of the names differ."
    )
    bullets = [
        f"Implementation: abydos {escape(config['abydos_version'])} DoubleMetaphone, "
        f"{max_length_phrase(max_length)}.",
        "Match rule: each name has a primary code and, when the algorithm finds a second plausible "
        "pronunciation, an alternate code. A query matches a list name when their code sets share at "
        "least one code. Each query is compared against all reference names.",
        "Each name was encoded as one string. Spaces and hyphens add no code, so multi-word and "
        f"hyphenated names are matched on the code of the whole name, not word by word. {truncation}",
        "Outcomes are counted per case. Extra names returned on a positive case are not false positives; "
        "they are reported as over-matching instead.",
    ]
    limitations = [
        "Ground truth labels are a judgement call: whether two names 'sound alike' is subjective, so "
        "some failures may be labeling errors. Every failure is listed above for review.",
        "Keyboard typos were deliberately excluded. Double Metaphone encodes pronunciation, so these "
        "results do not describe typo tolerance.",
        f"Per-length rates rest on {_bucket_sizes(summary)} each and are noisy. Overall figures "
        f"({summary['dataset']['cases']} queries) are more reliable.",
        "Results depend on the reference list: a larger or denser list raises the chance that a "
        "negative query shares a code with some name.",
    ]
    return [
        _p("Methodology", "h2"),
        *[_bullet(b) for b in bullets],
        _p("Limitations", "h2"),
        *[_bullet(b) for b in limitations],
    ]


def _warnings_section(warnings: list[str]) -> list:
    if not warnings:
        return []
    return [
        _p("Appendix: validation warnings", "h2"),
        *[_bullet(escape(w)) for w in warnings],
    ]


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor(TEXT_MUTED))
    canvas.drawString(MARGIN, 10 * mm, "Double Metaphone accuracy report")
    canvas.drawRightString(PAGE_WIDTH - MARGIN, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_report(
    out_dir: Path,
    summary: dict,
    results: list[CaseResult],
    encode: Callable[[str], frozenset[str]],
) -> Path:
    """Write charts and the PDF report into ``out_dir``; return the PDF path."""
    out_dir = Path(out_dir)
    charts = build_charts(summary, out_dir)
    config = summary["config"]

    story = [
        _p("Double Metaphone: accuracy report", "title"),
        _p(f"Run {escape(config['run_at'])} &middot; abydos {escape(config['abydos_version'])} &middot; "
           f"{max_length_phrase(config['max_length'])}", "subtitle"),
        Spacer(1, 10),
        _p("Summary", "h2"),
        _kpi_tiles(summary["overall"]),
        Spacer(1, 8),
        _p(takeaway(summary)),
        *_dataset_section(summary, results),
        KeepTogether(_confusion_section(summary["overall"])),
        PageBreak(),
        *_length_section(summary, charts["recall_fpr"]),
        PageBreak(),
        *_overmatch_section(summary, charts["candidates"]),
        *_variant_section(summary),
        PageBreak(),
        *_failure_section(results, encode),
        PageBreak(),
        *_method_section(summary),
        *_warnings_section(summary["warnings"]),
    ]

    path = out_dir / REPORT_FILE
    doc = SimpleDocTemplate(
        str(path), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN + 4 * mm,
        title="Double Metaphone accuracy report", author="dm_test",
    )
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return path
