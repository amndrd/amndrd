#!/usr/bin/env python3
"""Render the profile README cards as theme-aware SVGs, straight from the GitHub API.

Public card services (github-readme-stats, activity-graph…) keep getting paused or
rate-limited, so the cards are drawn here and served from the `output` branch
instead. Standard library only.

Usage: GITHUB_TOKEN=… python3 scripts/cards.py <output-dir> [login]
"""

import html
import json
import math
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',Helvetica,Arial,sans-serif"

THEMES = {
    "dark": {
        "bg": "#0d1117", "border": "#30363d", "title": "#e6edf3", "text": "#c9d1d9",
        "muted": "#8b949e", "accent": "#58a6ff", "grid": "#21262d",
    },
    "light": {
        "bg": "#ffffff", "border": "#d0d7de", "title": "#1f2328", "text": "#1f2328",
        "muted": "#656d76", "accent": "#0969da", "grid": "#eaeef2",
    },
}

# Octicons, 16px grid.
ICONS = {
    "star": "M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.751.751 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Zm0 2.445L6.615 5.5a.75.75 0 0 1-.564.41l-3.097.45 2.24 2.184a.75.75 0 0 1 .216.664l-.528 3.084 2.769-1.456a.75.75 0 0 1 .698 0l2.77 1.456-.53-3.084a.75.75 0 0 1 .216-.664l2.24-2.183-3.096-.45a.75.75 0 0 1-.564-.41L8 2.694Z",
    "commit": "M1.643 3.143L.427 1.927A.25.25 0 000 2.104V5.75c0 .138.112.25.25.25h3.646a.25.25 0 00.177-.427L2.715 4.215a6.5 6.5 0 11-1.18 4.458.75.75 0 10-1.493.154 8.001 8.001 0 101.6-5.684zM7.75 4a.75.75 0 01.75.75v2.992l2.028.812a.75.75 0 01-.557 1.392l-2.5-1A.75.75 0 017 8.25v-3.5A.75.75 0 017.75 4z",
    "pr": "M7.177 3.073L9.573.677A.25.25 0 0110 .854v4.792a.25.25 0 01-.427.177L7.177 3.427a.25.25 0 010-.354zM3.75 2.5a.75.75 0 100 1.5.75.75 0 000-1.5zm-2.25.75a2.25 2.25 0 113 2.122v5.256a2.251 2.251 0 11-1.5 0V5.372A2.25 2.25 0 011.5 3.25zM11 2.5h-1V4h1a1 1 0 011 1v5.628a2.251 2.251 0 101.5 0V5A2.5 2.5 0 0011 2.5zm1 10.25a.75.75 0 111.5 0 .75.75 0 01-1.5 0zM3.75 12a.75.75 0 100 1.5.75.75 0 000-1.5z",
    "issue": "M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM0 8a8 8 0 1116 0A8 8 0 010 8zm9 3a1 1 0 11-2 0 1 1 0 012 0zm-.25-6.25a.75.75 0 00-1.5 0v3.5a.75.75 0 001.5 0v-3.5z",
    "repo": "M2 2.5A2.5 2.5 0 014.5 0h8.75a.75.75 0 01.75.75v12.5a.75.75 0 01-.75.75h-2.5a.75.75 0 110-1.5h1.75v-2h-8a1 1 0 00-.714 1.7.75.75 0 01-1.072 1.05A2.495 2.495 0 012 11.5v-9zm10.5-1V9h-8c-.356 0-.694.074-1 .208V2.5a1 1 0 011-1h8zM5 12.25v3.25a.25.25 0 00.4.2l1.45-1.087a.25.25 0 01.3 0L8.6 15.7a.25.25 0 00.4-.2v-3.25a.25.25 0 00-.25-.25h-3.5a.25.25 0 00-.25.25z",
}

PROFILE_QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    name login
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    repositoriesContributedTo(includeUserRepositories: true,
      contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]) { totalCount }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}"""

CALENDAR_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestReviewContributions
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
  }
}"""


def graphql(query, **variables):
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"bearer {os.environ['GITHUB_TOKEN']}",
            "Content-Type": "application/json",
            "User-Agent": "profile-cards",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if payload.get("errors"):
        sys.exit(f"GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def fetch(login):
    user, repos, cursor = None, [], None
    while True:
        page = graphql(PROFILE_QUERY, login=login, cursor=cursor)
        user = user or page
        repos += page["repositories"]["nodes"]
        if not page["repositories"]["pageInfo"]["hasNextPage"]:
            break
        cursor = page["repositories"]["pageInfo"]["endCursor"]

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=364)
    year = graphql(CALENDAR_QUERY, login=login,
                   **{"from": f"{start}T00:00:00Z", "to": f"{today}T23:59:59Z"})["contributionsCollection"]
    days = {date.fromisoformat(day["date"]): day["contributionCount"]
            for week in year["contributionCalendar"]["weeks"] for day in week["contributionDays"]}

    # Every repo weighs the same: one generated 10 MB HTML export shouldn't drown the rest.
    # The profile repo itself is skipped, or this very script would count as a Python project.
    shares, colors = defaultdict(float), {}
    for repo in repos:
        if repo["name"].lower() == login.lower():
            continue
        edges = repo["languages"]["edges"]
        total = sum(edge["size"] for edge in edges)
        for edge in edges:
            shares[edge["node"]["name"]] += edge["size"] / total
            colors[edge["node"]["name"]] = edge["node"]["color"]

    return {
        "name": user["name"] or user["login"],
        "today": today,
        "days": days,
        "stars": sum(repo["stargazerCount"] for repo in repos),
        "followers": user["followers"]["totalCount"],
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
        "contributed_to": user["repositoriesContributedTo"]["totalCount"],
        "commits_year": year["totalCommitContributions"],
        "reviews_year": year["totalPullRequestReviewContributions"],
        "languages": sorted(((name, share, colors[name]) for name, share in shares.items()),
                            key=lambda item: -item[1]),
    }


def rank(stats):
    """Same scoring as github-readme-stats, so the letter means what people expect."""
    exponential = lambda x: 1 - 2 ** -x
    log_normal = lambda x: x / (1 + x)
    weighted = [
        (2, exponential(stats["commits_year"] / 250)),
        (3, exponential(stats["prs"] / 50)),
        (1, exponential(stats["issues"] / 25)),
        (1, exponential(stats["reviews_year"] / 2)),
        (4, log_normal(stats["stars"] / 50)),
        (1, log_normal(stats["followers"] / 10)),
    ]
    percentile = (1 - sum(w * v for w, v in weighted) / sum(w for w, _ in weighted)) * 100
    for threshold, level in zip((1, 12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100),
                                ("S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C")):
        if percentile <= threshold:
            return level, percentile
    return "C", percentile


# ---------------------------------------------------------------- drawing helpers

def esc(text):
    return html.escape(str(text))


def short_date(day, today):
    return f"{day:%b} {day.day}" + ("" if day.year == today.year else f", {day.year}")


def svg(theme, width, height, label, body, heading=None, subheading=None, css=""):
    t = THEMES[theme]
    head = ""
    if heading:
        head += f'<text x="25" y="36" class="heading">{esc(heading)}</text>'
    if subheading:
        head += f'<text x="{width - 25}" y="36" class="small" text-anchor="end">{esc(subheading)}</text>'
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(label)}">
<title>{esc(label)}</title>
<style>
  svg {{ font-family: {FONT}; fill: {t["text"]}; }}
  .heading {{ font-size: 16px; font-weight: 600; fill: {t["title"]}; }}
  .label {{ font-size: 13px; }}
  .value {{ font-size: 13px; font-weight: 600; fill: {t["title"]}; }}
  .small {{ font-size: 11px; fill: {t["muted"]}; }}
  .fade {{ animation: fade .6s ease-out both; }}
  @keyframes fade {{ from {{ opacity: 0; }} }}
  {css}
  @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
</style>
<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10" fill="{t["bg"]}" stroke="{t["border"]}"/>
{head}
{body}
</svg>
"""


def nice_ceiling(peak, ticks=4):
    raw = max(peak, ticks) / ticks
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    return step * ticks, step


def monotone_path(points):
    """Smooth curve that never overshoots its points (Fritsch–Carlson), so it can't dip below zero."""
    xs, ys = zip(*points)
    n = len(points)
    slopes = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
    tangents = [slopes[0]] + [
        0 if slopes[i - 1] * slopes[i] <= 0 else (slopes[i - 1] + slopes[i]) / 2 for i in range(1, n - 1)
    ] + [slopes[-1]]
    for i, slope in enumerate(slopes):
        if slope == 0:
            tangents[i] = tangents[i + 1] = 0
            continue
        a, b = tangents[i] / slope, tangents[i + 1] / slope
        if a * a + b * b > 9:
            k = 3 / math.hypot(a, b)
            tangents[i], tangents[i + 1] = k * a * slope, k * b * slope
    path = f"M{xs[0]:.1f},{ys[0]:.1f}"
    for i in range(n - 1):
        dx = (xs[i + 1] - xs[i]) / 3
        path += (f" C{xs[i] + dx:.1f},{ys[i] + tangents[i] * dx:.1f}"
                 f" {xs[i + 1] - dx:.1f},{ys[i + 1] - tangents[i + 1] * dx:.1f} {xs[i + 1]:.1f},{ys[i + 1]:.1f}")
    return path


# ---------------------------------------------------------------- cards

def activity_card(stats, theme):
    t = THEMES[theme]
    width, height = 850, 320
    left, right, top, bottom = 62, 822, 70, 256
    dates = [stats["today"] - timedelta(days=30 - i) for i in range(31)]
    values = [stats["days"].get(day, 0) for day in dates]
    y_max, step = nice_ceiling(max(values))
    x = lambda i: left + i * (right - left) / 30
    y = lambda v: bottom - v / y_max * (bottom - top)

    body = []
    for tick in range(5):
        value = tick * step
        body.append(f'<line x1="{left}" x2="{right}" y1="{y(value):.1f}" y2="{y(value):.1f}" stroke="{t["grid"]}"/>')
        body.append(f'<text x="{left - 14}" y="{y(value) + 4:.1f}" class="small" text-anchor="end">{value:g}</text>')
    for i, day in enumerate(dates):
        body.append(f'<text x="{x(i):.1f}" y="{bottom + 22}" class="small" text-anchor="middle">{day.day}</text>')
        if i == 0 or day.day == 1:
            body.append(f'<text x="{x(i):.1f}" y="{bottom + 40}" class="small" text-anchor="middle" '
                        f'font-weight="600">{day:%b}</text>')

    line = monotone_path([(x(i), y(v)) for i, v in enumerate(values)])
    body.append(f"""<defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="{t["accent"]}" stop-opacity=".35"/><stop offset="1" stop-color="{t["accent"]}" stop-opacity="0"/>
</linearGradient></defs>
<path d="{line} L{right},{bottom} L{left},{bottom} Z" fill="url(#area)" class="fade" style="animation-delay:.9s"/>
<path d="{line}" fill="none" stroke="{t["accent"]}" stroke-width="2.5" stroke-linejoin="round" pathLength="1" class="draw"/>""")
    for i, value in enumerate(values):
        body.append(f'<circle cx="{x(i):.1f}" cy="{y(value):.1f}" r="3.5" fill="{t["bg"]}" stroke="{t["accent"]}" '
                    f'stroke-width="2" class="fade" style="animation-delay:{0.2 + i * 0.05:.2f}s">'
                    f'<title>{short_date(dates[i], stats["today"])}: {value}</title></circle>')

    return svg(theme, width, height, f"{stats['name']}'s contribution graph", "\n".join(body),
               heading=f"{stats['name']}'s contribution graph",
               subheading=f"last 31 days · {sum(values):,} contributions",
               css=".draw { stroke-dasharray: 1; animation: draw 1.8s ease-out both; }"
                   " @keyframes draw { from { stroke-dashoffset: 1; } to { stroke-dashoffset: 0; } }")


def stats_card(stats, theme):
    t = THEMES[theme]
    rows = [
        ("star", "Total stars earned", stats["stars"]),
        ("commit", "Commits (last 12 months)", stats["commits_year"]),
        ("pr", "Pull requests", stats["prs"]),
        ("issue", "Issues", stats["issues"]),
        ("repo", "Repositories contributed to", stats["contributed_to"]),
    ]
    body = []
    for i, (icon, label, value) in enumerate(rows):
        row_y = 72 + i * 25
        body.append(f'<g class="fade" style="animation-delay:{0.1 + i * 0.1:.1f}s">'
                    f'<path transform="translate(25 {row_y - 12})" d="{ICONS[icon]}" fill="{t["muted"]}"/>'
                    f'<text x="50" y="{row_y}" class="label">{label}</text>'
                    f'<text x="270" y="{row_y}" class="value">{value:,}</text></g>')

    level, percentile = rank(stats)
    progress = max(100 - percentile, 0.5)
    body.append(f"""<circle cx="400" cy="110" r="42" fill="none" stroke="{t["grid"]}" stroke-width="7"/>
<circle cx="400" cy="110" r="42" fill="none" stroke="{t["accent"]}" stroke-width="7" stroke-linecap="round"
  pathLength="100" stroke-dasharray="{progress:.1f} 100" transform="rotate(-90 400 110)" class="ring"/>
<text x="400" y="119" text-anchor="middle" font-size="26" font-weight="700" fill="{t["title"]}">{level}</text>
<text x="400" y="176" text-anchor="middle" class="small">top {percentile:.0f}%</text>""")

    return svg(theme, 495, 195, f"{stats['name']}'s GitHub stats", "\n".join(body),
               heading=f"{stats['name']}'s GitHub stats",
               css=".ring { animation: ring 1.2s ease-out both; }"
                   " @keyframes ring { from { stroke-dasharray: 0 100; } }")


def languages_card(stats, theme):
    t = THEMES[theme]
    languages = stats["languages"]
    total = sum(share for _, share, _ in languages) or 1
    slices = [(name, share / total * 100, color or t["muted"]) for name, share, color in languages[:5]]
    rest = 100 - sum(percent for _, percent, _ in slices)
    if rest >= 0.5:
        slices.append(("Other", rest, t["muted"]))

    cx, cy, r = 110, 112, 50
    body, offset = [], 0.0
    for name, percent, color in slices:
        dash = max(percent - 0.6, 0.1)  # hairline gap between slices
        body.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="20" pathLength="100" '
                    f'stroke-dasharray="{dash:.2f} {100 - dash:.2f}" stroke-dashoffset="{-offset:.2f}" '
                    f'transform="rotate(-90 {cx} {cy})"><title>{esc(name)}: {percent:.1f}%</title></circle>')
        offset += percent
    if slices:
        body.append(f'<text x="{cx}" y="{cy + 2}" text-anchor="middle" font-size="18" font-weight="700" '
                    f'fill="{t["title"]}">{slices[0][1]:.0f}%</text>'
                    f'<text x="{cx}" y="{cy + 18}" text-anchor="middle" class="small">{esc(slices[0][0])}</text>')
    for i, (name, percent, color) in enumerate(slices):
        row_y = 72 + i * 21
        body.append(f'<g class="fade" style="animation-delay:{0.1 + i * 0.08:.2f}s">'
                    f'<circle cx="215" cy="{row_y - 4}" r="5" fill="{color}"/>'
                    f'<text x="230" y="{row_y}" class="label">{esc(name)}</text>'
                    f'<line x1="330" x2="{330 + 100 * percent / slices[0][1]:.1f}" y1="{row_y - 4}" y2="{row_y - 4}" '
                    f'stroke="{color}" stroke-width="6" stroke-linecap="round" opacity=".8"/>'
                    f'<text x="470" y="{row_y}" class="small" text-anchor="end">{percent:.1f}%</text></g>')

    return svg(theme, 495, 195, "Most used languages", "\n".join(body),
               heading="Most used languages", subheading="each repo weighs the same")


CARDS = {
    "activity": activity_card,
    "stats": stats_card,
    "languages": languages_card,
}


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out = Path(sys.argv[1])
    login = sys.argv[2] if len(sys.argv) > 2 else os.environ["GITHUB_REPOSITORY_OWNER"]
    stats = fetch(login)
    out.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        for name, render in CARDS.items():
            (out / f"{name}-{theme}.svg").write_text(render(stats, theme), encoding="utf-8")
    print(f"{login}: {stats['commits_year']} commits in the last 12 months, {stats['stars']} stars, "
          f"rank {rank(stats)[0]} → {len(CARDS) * len(THEMES)} cards in {out}/")


if __name__ == "__main__":
    main()
