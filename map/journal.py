#!/usr/bin/env python3
"""The journal as a page of the site: map/journal.md -> journal.html.

    python -m map.journal            # writes site_build/journal.html

map/journal.md is the published text: the notebook one of the leaders kept,
lightly edited, with a few private passages left out. The notebook's full
transcript is not in this repository, and this file is the only part of it
that is.

No Markdown library, because the file only ever uses four things and the build
has no dependency to spare for them: `## ` opens a day, `- ` is a list item,
`> ` is a passage added later, and anything else is a paragraph. Blocks are
separated by blank lines. Text is escaped, and a bare URL becomes a link.
"""
import argparse
import html
import os
import re

from trip import DAYS

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "journal.md")

_URL = re.compile(r"(https?://[^\s<]+?)(?=[.,;:)]*(?:\s|$))")
_DAY = re.compile(r"^(\w+day) (\d{1,2}) (\w+) (\d{4})$")


def slug(label):
    """'Sun 24 Mar' -> 'sun-24-mar'. The page's anchors and the chart's links to
    them are both made from the chart's own day labels, so they cannot drift."""
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def chart_label(heading):
    """The chart's label for a journal heading: 'Sunday 24 March 2024' -> 'Sun 24 Mar'."""
    m = _DAY.match(heading.strip())
    if not m:
        return None
    return f"{m.group(1)[:3]} {int(m.group(2))} {m.group(3)[:3]}"


def _inline(text):
    out, last = [], 0
    for m in _URL.finditer(text):
        out.append(html.escape(text[last:m.start()]))
        url = html.escape(m.group(1), quote=True)
        out.append(f'<a href="{url}" rel="noopener">{url}</a>')
        last = m.end()
    out.append(html.escape(text[last:]))
    return "".join(out)


def parse(text):
    """-> (title, intro_blocks, [(heading, blocks)]). A block is (kind, payload)."""
    title, intro, days, into = None, [], [], None
    for raw in re.split(r"\n\s*\n", text.strip()):
        lines = [l.rstrip() for l in raw.strip().split("\n")]
        first = lines[0]
        if first.startswith("# "):
            title = first[2:].strip()
            continue
        if first.startswith("## "):
            into = []
            days.append((first[3:].strip(), into))
            continue
        if all(l.startswith("- ") for l in lines):
            block = ("list", [l[2:].strip() for l in lines])
        elif all(l.startswith(">") for l in lines):
            block = ("aside", " ".join(l[1:].strip() for l in lines))
        else:
            block = ("p", " ".join(l.strip() for l in lines))
        (intro if into is None else into).append(block)
    return title, intro, days


def _blocks(blocks):
    out = []
    for kind, body in blocks:
        if kind == "list":
            out.append("<ul>" + "".join(f"<li>{_inline(i)}</li>" for i in body) + "</ul>")
        elif kind == "aside":
            out.append(f'<aside><span class="added">Added later</span> {_inline(body)}</aside>')
        else:
            out.append(f"<p>{_inline(body)}</p>")
    return "\n".join(out)


def render(text=None):
    """The whole page, as a string."""
    text = open(SOURCE, encoding="utf-8").read() if text is None else text
    title, intro, days = parse(text)
    on_chart = {d["label"] for d in DAYS}
    nav, sections = [], []
    for heading, blocks in days:
        label = chart_label(heading) or heading
        anchor = slug(label)
        nav.append(f'<a href="#{anchor}">{html.escape(label)}</a>')
        link = (f'<p class="tochart"><a href="index.html?day={html.escape(label).replace(" ", "%20")}">'
                f"See this day on the chart</a></p>" if label in on_chart else "")
        sections.append(f'<section id="{anchor}">\n<h2>{html.escape(heading)}</h2>\n'
                        f"{link}\n{_blocks(blocks)}\n</section>")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>The journal — Sea Base 1830, Sea of Abaco, March 2024</title>
<link rel="icon" href="data:,">
<link rel="stylesheet" href="journal.css">
</head>
<body>
<header class="top">
  <p class="back"><a href="index.html">&larr; The chart</a></p>
  <h1>Sea Base 1830</h1>
  <p class="sub">{html.escape(title or "The journal")} &middot; Sea of Abaco &middot; March 2024</p>
</header>
<nav class="days" aria-label="Days">{' '.join(nav)}</nav>
<main>
<div class="intro">
{_blocks(intro)}
</div>
{chr(10).join(sections)}
</main>
<footer><p><a href="index.html">&larr; Back to the chart</a></p></footer>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=os.path.join(HERE, "site_build", "journal.html"))
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(render())
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
