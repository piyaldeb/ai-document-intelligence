"""Rebuild layout-preserving text from positioned words (PDF text layer or OCR boxes).

Plain text extraction loses table structure: cells of one row come out on separate lines.
We regroup words into visual lines by vertical position and place them at a column offset
proportional to their x coordinate, so that:
  * words of one phrase are separated by a single space,
  * table columns are separated by 2+ spaces (the extractors split on r"\\s{2,}"),
  * column starts roughly line up across rows (used for "Bill To" / "From" side-by-side blocks).
"""

from __future__ import annotations

from collections.abc import Iterable
from statistics import median

Word = tuple[float, float, float, float, str]  # x0, y0, x1, y1, text


def words_to_text(words: Iterable[Word]) -> str:
    items = [w for w in words if w[4] and w[4].strip()]
    if not items:
        return ""

    heights = [max(0.1, w[3] - w[1]) for w in items]
    char_widths = [max(0.1, (w[2] - w[0]) / max(1, len(w[4]))) for w in items]
    line_tol = median(heights) * 0.55
    char_w = median(char_widths)

    # Group into lines by vertical centre.
    items.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines: list[list[Word]] = []
    centres: list[float] = []
    for w in items:
        yc = (w[1] + w[3]) / 2
        if lines and abs(yc - centres[-1]) <= line_tol:
            lines[-1].append(w)
            n = len(lines[-1])
            centres[-1] = centres[-1] + (yc - centres[-1]) / n
        else:
            lines.append([w])
            centres.append(yc)

    min_x = min(w[0] for w in items)
    out: list[str] = []
    prev_centre = None
    median_h = median(heights)
    for line, centre in zip(lines, centres):
        # Preserve paragraph breaks (large vertical gaps) as blank lines.
        if prev_centre is not None and centre - prev_centre > median_h * 2.2:
            out.append("")
        prev_centre = centre
        line.sort(key=lambda w: w[0])
        buf = ""
        prev_x1 = None
        for x0, _y0, x1, _y1, text in line:
            text = text.strip()
            if prev_x1 is None:
                col = int(round((x0 - min_x) / char_w))
                buf = " " * max(0, col) + text
            else:
                gap = x0 - prev_x1
                if gap < char_w * 1.5:
                    buf += " " + text
                else:
                    col = int(round((x0 - min_x) / char_w))
                    buf += " " * max(2, col - len(buf)) + text
            prev_x1 = x1
        out.append(buf.rstrip())
    return "\n".join(out).strip("\n")
