#!/usr/bin/env python3
"""The top of the profile README: the banner with a metallic sheen over the cards, an animated
terminal and the skill icons popping in.

Usage: GITHUB_TOKEN=… python3 scripts/header.py <output-dir> [login]
"""

import base64
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from cards import THEMES, Timeline, esc, graphql

ASSETS = Path(__file__).resolve().parent.parent / "assets"
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"

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


# ---------------------------------------------------------------- terminal

PROFILE_QUERY = """
query($login: String!) {
  user(login: $login) {
    name login bio
    repositories(first: 6, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes { name pushedAt primaryLanguage { name color } }
    }
  }
}"""

WINDOW = {"dark": ("#010409", "#161b22"), "light": ("#24292f", "#32383f")}
INK = {"prompt": "#7ee787", "path": "#79c0ff", "command": "#e6edf3", "out": "#c9d1d9", "dim": "#8b949e", "key": "#d2a8ff"}
STACK = (
    ("mobile", "Swift · SwiftUI · Vision · Firebase"),
    ("web", "TypeScript · Next.js · React · Three.js"),
    ("backend", "Python · FastAPI · Playwright · Telegram bots"),
)


def ago(stamp, now):
    days = (now - datetime.fromisoformat(stamp.replace("Z", "+00:00"))).days
    if days < 1:
        return "today"
    if days < 2:
        return "yesterday"
    if days < 14:
        return f"{days} days ago"
    if days < 60:
        return f"{days // 7} weeks ago"
    return f"{days // 30} months ago"


def terminal(profile, theme):
    t = THEMES[theme]
    window, bar = WINDOW[theme]
    now = datetime.now(timezone.utc)
    repos = [r for r in profile["repositories"]["nodes"] if r["name"].lower() != profile["login"].lower()][:3]
    name = profile["name"] or profile["login"]
    bio = (profile["bio"] or "").strip().rstrip(".")
    whoami = f"{name} · {bio}" if bio else name

    session = [("cmd", "whoami"), ("out", [(INK["out"], whoami[:92])]), ("gap",), ("cmd", "cat stack.txt")]
    session += [("out", [(INK["key"], key.ljust(9)), (INK["out"], value)]) for key, value in STACK]
    session += [("gap",), ("cmd", "ls projects --sort=recent")]
    session += [("out", [(INK["path"], repo["name"].ljust(22)),
                         ((repo["primaryLanguage"] or {}).get("color") or INK["dim"],
                          ((repo["primaryLanguage"] or {}).get("name") or "—").ljust(13)),
                         (INK["dim"], f"pushed {ago(repo['pushedAt'], now)}")]) for repo in repos]
    session += [("gap",), ("prompt",)]

    width, pad, line, char = 850, 24, 21, 8.1
    y, clock, placed = 36 + 30, .6, []
    for entry in session:
        if entry[0] == "gap":
            y += line / 2
            continue
        placed.append((entry, y, clock))
        if entry[0] == "cmd":
            clock += len(entry[1]) * .065 + .45
        elif entry[0] == "out":
            clock += .12
        y += line
    height = y + 10
    duration = clock + 4.5
    tl = Timeline(duration)
    shown = lambda start: tl([(0, "opacity:0"), (start - .01, "opacity:0"), (start, "opacity:1"),
                              (duration - .35, "opacity:1"), (duration - .3, "opacity:0")])

    body = []
    for (kind, *content), top, start in placed:
        baseline = top + 14
        if kind in ("cmd", "prompt"):
            body.append(f'<g class="{shown(start)}"><text x="{pad}" y="{baseline}" class="mono">'
                        f'<tspan fill="{INK["path"]}">~</tspan> <tspan fill="{INK["prompt"]}">$</tspan></text>')
            x = pad + 4 * char
            if kind == "cmd":
                text = content[0]
                n, typed = len(text), start + len(text) * .065
                body.append(f'<text x="{x}" y="{baseline}" class="mono" fill="{INK["command"]}" '
                            f'textLength="{n * char:.1f}" lengthAdjust="spacingAndGlyphs">{esc(text)}</text>')
                curtain = tl([(0, f"transform:translateX({-n * char:.1f}px)"),
                              (start, f"transform:translateX({-n * char:.1f}px);animation-timing-function:steps({n},end)"),
                              (typed, "transform:translateX(0)")])
                body.append(f'<rect x="{x + n * char:.1f}" y="{top}" width="{n * char + 2:.1f}" height="19" fill="{window}" class="{curtain}"/>')
                cursor = tl([(0, "opacity:0;transform:translateX(0)"), (start - .01, "opacity:0;transform:translateX(0)"),
                             (start, f"opacity:1;transform:translateX(0);animation-timing-function:steps({n},end)"),
                             (typed, f"opacity:1;transform:translateX({n * char:.1f}px)"),
                             (typed + .35, f"opacity:1;transform:translateX({n * char:.1f}px)"),
                             (typed + .36, f"opacity:0;transform:translateX({n * char:.1f}px)")])
                body.append(f'<rect x="{x}" y="{top + 1}" width="{char:.1f}" height="17" fill="{INK["command"]}" opacity="0" class="{cursor}"/>')
            else:
                blink = tl([(0, "opacity:0"), (start - .01, "opacity:0")] + [
                    (start + k * .5, f"opacity:{1 - k % 2}") for k in range(int((duration - start) / .5))], "steps(1,end)")
                body.append(f'<rect x="{x}" y="{top + 1}" width="{char:.1f}" height="17" fill="{INK["command"]}" class="{blink}"/>')
            body.append("</g>")
        else:
            spans = "".join(f'<tspan fill="{color}">{esc(text)}</tspan>' for color, text in content[0])
            body.append(f'<text x="{pad}" y="{baseline}" class="mono {shown(start)}">{spans}</text>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height:.0f}" viewBox="0 0 {width} {height:.0f}" role="img" aria-label="Terminal session: whoami, stack and recent projects">
<title>Terminal session: whoami, stack and recent projects</title>
<style>
  .mono {{ font-family: {MONO}; font-size: 13.5px; white-space: pre; }}
  {tl.css}
  @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
</style>
<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1:.0f}" rx="10" fill="{window}" stroke="{t["border"]}"/>
<path d="M0.5,36V10.5A10,10 0 0 1 10.5,0.5H{width - 10.5}A10,10 0 0 1 {width - .5},10.5V36Z" fill="{bar}"/>
<circle cx="22" cy="18" r="6" fill="#ff5f57"/><circle cx="42" cy="18" r="6" fill="#febc2e"/><circle cx="62" cy="18" r="6" fill="#28c840"/>
<text x="{width / 2}" y="22" text-anchor="middle" class="mono" font-size="12" fill="{INK["dim"]}">{esc(profile["login"])}@github: ~</text>
{"".join(body)}
</svg>
"""


# ---------------------------------------------------------------- skill icons

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
    login = sys.argv[2] if len(sys.argv) > 2 else os.environ["GITHUB_REPOSITORY_OWNER"]
    profile = graphql(PROFILE_QUERY, login=login)
    out.mkdir(parents=True, exist_ok=True)
    (out / "banner.svg").write_text(banner(), encoding="utf-8")
    for theme in THEMES:
        (out / f"terminal-{theme}.svg").write_text(terminal(profile, theme), encoding="utf-8")
        (out / f"skills-{theme}.svg").write_text(skills(theme), encoding="utf-8")
    print(f"{login}: banner, terminal and skills → {1 + 2 * len(THEMES)} files in {out}/")


if __name__ == "__main__":
    main()
