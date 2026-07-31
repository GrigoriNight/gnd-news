#!/usr/bin/env python3
"""Sanity-check Launcher.godaddy.html before it goes live on the website.

Launcher.godaddy.html is an embed *fragment* pasted into a GoDaddy page, not a
standalone document. It has been broken three times by pasting the desktop
(Tauri) launcher document over it, by a truncated chunked write, and once by a
write that left a single byte behind. Each check below corresponds to one of
those failures.

Usage: python3 tools/check_embed.py [path]
Exits non-zero and prints every problem found.
"""

import re
import sys

EMBED = "Launcher.godaddy.html"

# The last known-good published build was 72,120 bytes. A truncated write left
# 20,000; a wiped write left 1. Anything under this floor is not a real build.
MIN_BYTES = 50_000

# Markup the embed must contain to be functional on the page.
REQUIRED_IDS = [
    "gnd-launcher",
    "newsList",
    "storeGrid",
    "adminModal",
    "accountModal",
]

# Markup that means a full desktop-launcher document was pasted in by mistake.
FORBIDDEN = [
    ("<!DOCTYPE", "embed is a fragment, not a standalone document"),
    ("<html", "embed is a fragment, not a standalone document"),
    ("<body", "embed is a fragment, not a standalone document"),
    ('src="bridge.js"', "bridge.js is the desktop Tauri bridge and does not exist on the website"),
]


def strip_news_template(html):
    """Remove the news document that buildNewsHtml() returns as a template literal.

    That literal is a complete standalone page written out to news.html — it has
    its own <html>, <body>, <script id="gnd-news-data"> and #newsList. It is a
    payload, not part of the embed, so every document-shape check below has to
    ignore it or it reports the embed as a merged document.
    """
    start = html.find("function buildNewsHtml")
    if start < 0:
        return html
    open_tick = html.find("`", start)
    if open_tick < 0:
        return html
    i = open_tick + 1
    while i < len(html):
        if html[i] == "\\":
            i += 2
            continue
        if html[i] == "`":
            return html[:open_tick] + html[i + 1:]
        i += 1
    return html[:open_tick]


def script_tag_balance(html):
    """Count real <script>/</script> markup pairs.

    A script tag whose close is written escaped (<\\/script>) is inside JS — a
    string or a regex literal, like the one parseNewsHtml uses to find the news
    data block. Drop those regions first so they are not counted as markup.
    """
    markup = re.sub(
        r"<script[^>]*>(?:(?!<script|</script>).)*?<\\/script>", "", html, flags=re.S
    )
    return len(re.findall(r"<script[\s>]", markup)), len(re.findall(r"</script>", markup))


def duplicate_ids(html):
    ids = re.findall(r'\bid="([\w-]+)"', html)
    seen, dupes = set(), []
    for i in ids:
        if i in seen and i not in dupes:
            dupes.append(i)
        seen.add(i)
    return dupes


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else EMBED
    try:
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
    except OSError as exc:
        print(f"FAIL cannot read {path}: {exc}")
        return 1

    problems = []
    shape = strip_news_template(html)

    if len(html) < MIN_BYTES:
        problems.append(
            f"file is {len(html):,} bytes, below the {MIN_BYTES:,}-byte floor "
            "— looks like a truncated or wiped write"
        )

    for needle, why in FORBIDDEN:
        if needle.lower() in shape.lower():
            problems.append(f"contains {needle!r} — {why}")

    opens, closes = script_tag_balance(shape)
    if opens != closes:
        problems.append(f"unbalanced script tags: {opens} <script> vs {closes} </script>")

    for wanted in REQUIRED_IDS:
        if f'id="{wanted}"' not in shape:
            problems.append(f'missing required element id="{wanted}"')

    for dupe in duplicate_ids(shape):
        problems.append(f'duplicate element id="{dupe}" — two copies of the markup were merged')

    if problems:
        print(f"FAIL {path}")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(f"OK {path} ({len(html):,} bytes, {opens} script blocks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
