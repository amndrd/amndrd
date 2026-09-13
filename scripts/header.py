#!/usr/bin/env python3
"""The top of the profile README: the banner with a metallic sheen over the cards and the
skill icons popping in.

Usage: python3 scripts/header.py <output-dir>
"""

import base64
import re
import sys
from pathlib import Path

from cards import THEMES

ASSETS = Path(__file__).resolve().parent.parent / "assets"

# Corners of the four cards in assets/banner.jpg (1280×640), measured by hand.
CARDS = (
    ((282, 178), (442, 262), (566, 42), (380, -40)),
    ((662, 128), (738, 8), (928, 150), (852, 270)),
    ((452, 545), (495, 372), (733, 445), (688, 608)),
    ((758, 415), (878, 362), (942, 470), (790, 612)),
)


def banner():
    image = base64.b64encode((ASSETS / "banner.jpg").read_bytes()).decode()
    clip = "".join(f'<polygon points="{" ".join(f"{x},{y}" for x, y in card)}"/>' for card in CARDS)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="640" viewBox="0 0 1280 640" role="img" aria-label="Four phones showing black American Express cards">
<title>Four phones showing black American Express cards</title>
<style>
  .sheen {{ animation: sheen 6.5s cubic-bezier(.45,.05,.55,.95) infinite; }}
  @keyframes sheen {{ 0% {{ transform: translateX(-760px); }} 40%, 100% {{ transform: translateX(1180px); }} }}
  @media (prefers-reduced-motion: reduce) {{ .sheen {{ animation: none; opacity: 0; }} }}
</style>
<defs>
  <linearGradient id="shine" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".4" stop-color="#fff" stop-opacity="0"/>
    <stop offset=".5" stop-color="#fff" stop-opacity=".8"/><stop offset=".6" stop-color="#fff" stop-opacity="0"/>
    <stop offset=".7" stop-color="#fff" stop-opacity=".3"/><stop offset=".76" stop-color="#fff" stop-opacity="0"/>
  </linearGradient>
  <clipPath id="cards">{clip}</clipPath>
</defs>
<image href="data:image/jpeg;base64,{image}" width="1280" height="640"/>
<g clip-path="url(#cards)" style="mix-blend-mode:screen">
  <g transform="rotate(18 640 320)"><rect class="sheen" x="0" y="-300" width="420" height="1240" fill="url(#shine)"/></g>
</g>
</svg>
"""


def skills(theme, size=48, gap=12, per_line=8):
    # skillicons.dev wraps every icon in its own positioned <g>; cut the sheet at those boundaries.
    sheet = (ASSETS / f"skillicons-{theme}.svg").read_text()
    starts = list(re.finditer(r'<g transform="translate\(\d+, \d+\)">', sheet))
    ends = [match.start() for match in starts[1:]] + [sheet.rfind("</svg>")]
    icons = [re.sub(r"</g>\s*$", "", sheet[match.end():end].strip()) for match, end in zip(starts, ends)]
    rows = -(-len(icons) // per_line)
    width, height = per_line * size + (per_line - 1) * gap, rows * size + (rows - 1) * gap + 8
    body = []
    for i, icon in enumerate(icons):
        x, y = (i % per_line) * (size + gap), 4 + (i // per_line) * (size + gap)
        tag, rest = icon.split(">", 1)
        tag = re.sub(r'\s(width|height)="[\d.]+"', "", tag)
        icon = f'{tag} width="{size}" height="{size}">{rest}'
        body.append(f'<g transform="translate({x} {y})"><g class="wave" style="animation-delay:{1.6 + i * .07:.2f}s">'
                    f'<g class="pop" style="animation-delay:{i * .07:.2f}s">{icon}</g></g></g>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" role="img" aria-label="Skills">
<title>Skills</title>
<style>
  .pop {{ transform-box: fill-box; transform-origin: center; animation: pop .55s cubic-bezier(.3,1.6,.5,1) both; }}
  @keyframes pop {{ from {{ transform: scale(0); opacity: 0; }} }}
  .wave {{ animation: wave 6s ease-in-out infinite; }}
  @keyframes wave {{ 0%, 10%, 100% {{ transform: translateY(0); }} 5% {{ transform: translateY(-4px); }} }}
  @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
</style>
{"".join(body)}
</svg>
"""


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    (out / "banner.svg").write_text(banner(), encoding="utf-8")
    for theme in THEMES:
        (out / f"skills-{theme}.svg").write_text(skills(theme), encoding="utf-8")
    print(f"banner and skills → {1 + len(THEMES)} files in {out}/")


if __name__ == "__main__":
    main()
