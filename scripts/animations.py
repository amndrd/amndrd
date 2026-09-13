#!/usr/bin/env python3
"""Looping animations built from the last year of contributions, in the spirit of Platane/snk:
a 3D skyline, Space Invaders, Tetris, Conway's Game of Life and Pac-Man.

Every contribution day becomes a building, an invader, a block, a seed cell or a power
pellet. Standard library only; the API client and card chrome come from cards.py.

Usage: GITHUB_TOKEN=… python3 scripts/animations.py <output-dir> [login]
"""

import math
import os
import re
import sys
from collections import Counter, namedtuple
from pathlib import Path

from cards import THEMES, graphql, svg

LEVELS = ("NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE")
PALETTES = {  # GitHub's own contribution greens
    "dark": ("#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"),
    "light": ("#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"),
}
SPRITES = {  # brighter greens for sprites that have to read against the card background
    "dark": ("#30363d", "#2ea043", "#3fb950", "#56d364", "#7ee787"),
    "light": ("#d0d7de", "#4ac26b", "#2da44e", "#1a7f37", "#116329"),
}

Cell = namedtuple("Cell", "col row count level")

CALENDAR_QUERY = """
query($login: String!) {
  user(login: $login) {
    name login
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { weekday contributionCount contributionLevel } }
      }
    }
  }
}"""


def fetch(login):
    user = graphql(CALENDAR_QUERY, login=login)
    calendar = user["contributionsCollection"]["contributionCalendar"]
    cells = [Cell(col, day["weekday"], day["contributionCount"], LEVELS.index(day["contributionLevel"]))
             for col, week in enumerate(calendar["weeks"]) for day in week["contributionDays"]]
    return {"name": user["name"] or user["login"], "login": user["login"],
            "total": calendar["totalContributions"], "weeks": len(calendar["weeks"]), "cells": cells}


class Timeline:
    """One looping @keyframes per element, written in seconds rather than percentages."""

    def __init__(self, duration):
        self.duration, self.rules = duration, []

    def __call__(self, stops, timing="linear"):
        name = f"k{len(self.rules)}"
        stops = sorted(stops, key=lambda stop: stop[0])
        if stops[0][0] > 0:
            stops.insert(0, (0, stops[0][1]))
        if stops[-1][0] < self.duration:
            stops.append((self.duration, stops[-1][1]))
        frames = "".join(f"{min(time / self.duration * 100, 100):.3f}%{{{css}}}" for time, css in stops)
        self.rules.append(f"@keyframes {name}{{{frames}}}"
                          f".{name}{{animation:{name} {self.duration:.2f}s {timing} infinite}}")
        return name

    @property
    def css(self):
        return "\n".join(self.rules)


def pixels(*rows):
    """Pixel art ('X' = lit) → a single path, one run of pixels per subpath."""
    return "".join(f"M{run.start()},{y}h{len(run.group())}v1h-{len(run.group())}z"
                   for y, row in enumerate(rows) for run in re.finditer("X+", row))


def shade(color, factor):
    channels = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{min(255, round(c * factor)):02x}" for c in channels)


def grid_left(weeks, pitch, width=850):
    return (width - (weeks * pitch - 3)) / 2


def slots(pattern_id, pitch, x, y, width, height, fill):
    """Empty calendar squares as one patterned rect instead of hundreds of elements."""
    return (f'<defs><pattern id="{pattern_id}" width="{pitch}" height="{pitch}" patternUnits="userSpaceOnUse" '
            f'x="{x}" y="{y}"><rect width="{pitch - 3}" height="{pitch - 3}" rx="2" fill="{fill}"/></pattern></defs>'
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="url(#{pattern_id})"/>')


# ---------------------------------------------------------------- skyline

def skyline(data, theme):
    t, palette = THEMES[theme], PALETTES[theme]
    width, height, weeks, duration = 850, 330, data["weeks"], 9
    ux, uy, vx, vy = 13.2, 2.2, -5.2, 4.4  # screen offset of one week, of one weekday
    ox, oy = (width - (weeks * ux - 7 * vx)) / 2 - 7 * vx, 138
    at = lambda i, j: (ox + i * ux + j * vx, oy + i * uy + j * vy)
    polygon = lambda points, fill, extra="": (
        f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in points)}" fill="{fill}"{extra}/>')
    drop = lambda points, depth: points + [(x, y + depth) for x, y in reversed(points)]

    edge = t["border"]
    body = [
        polygon([at(-.4, -.4), at(weeks + .4, -.4), at(weeks + .4, 7.4), at(-.4, 7.4)], edge),
        polygon(drop([at(-.4, 7.4), at(weeks + .4, 7.4)], 16), shade(edge, .8)),
        polygon(drop([at(weeks + .4, -.4), at(weeks + .4, 7.4)], 16), shade(edge, .6)),
    ]
    x, y = at(1, 7.4)
    body.append(f'<text transform="translate({x:.1f} {y + 11.5:.1f}) skewY({math.degrees(math.atan2(uy, ux)):.2f})" '
                f'font-size="9" letter-spacing="1" fill="{t["muted"]}">github.com/{data["login"]}</text>')

    gap = .12
    footprint = lambda i, j: [at(i + gap, j + gap), at(i + 1 - gap, j + gap), at(i + 1 - gap, j + 1 - gap), at(i + gap, j + 1 - gap)]
    for cell in data["cells"]:
        if not cell.count:
            body.append(polygon(footprint(cell.col, cell.row), palette[0]))

    peak = max((cell.count for cell in data["cells"]), default=1) or 1
    lifts = set()
    for cell in sorted((c for c in data["cells"] if c.count), key=lambda c: (c.col * uy + c.row * vy, c.col)):
        back, right, front, left = footprint(cell.col, cell.row)
        h = round(5 + (cell.count / peak) ** .6 * 85)
        lifts.add(h)
        color, delay = palette[cell.level], f'style="animation-delay:{cell.col * .045:.2f}s"'
        # Side faces are skewed rects so they can grow with a plain scaleY from their base edge.
        for start, end, factor in ((left, front, .72), (front, right, .5)):
            dx, dy = end[0] - start[0], end[1] - start[1]
            body.append(f'<g transform="translate({start[0]:.1f} {start[1]:.1f}) skewY({math.degrees(math.atan2(dy, dx)):.2f})">'
                        f'<rect y="{-h}" width="{dx:.2f}" height="{h}" fill="{shade(color, factor)}" class="rise" {delay}/></g>')
        body.append(polygon([(px, py - h) for px, py in (back, right, front, left)], color,
                            f' stroke="{shade(color, 1.25)}" stroke-width=".6" class="lift{h}" {delay}'))

    ease = "cubic-bezier(.3,.7,.4,1)"
    css = [f".rise{{transform-origin:0 0;animation:rise {duration}s {ease} infinite both}}"
           "@keyframes rise{0%{transform:scaleY(0)}16%,82%{transform:scaleY(1)}94%,100%{transform:scaleY(0)}}"]
    css += [f".lift{h}{{animation:lift{h} {duration}s {ease} infinite both}}"
            f"@keyframes lift{h}{{0%{{transform:translateY({h}px)}}16%,82%{{transform:translateY(0)}}"
            f"94%,100%{{transform:translateY({h}px)}}}}" for h in sorted(lifts)]
    return svg(theme, width, height, f"{data['name']}'s contribution skyline", "\n".join(body),
               heading=f"{data['name']}'s contribution skyline",
               subheading=f"{data['total']:,} contributions · last 12 months", css="\n".join(css))


# ---------------------------------------------------------------- space invaders

CRAB = (
    pixels("..X.....X..", "...X...X...", "..XXXXXXX..", ".XX.XXX.XX.", "XXXXXXXXXXX", "X.XXXXXXX.X", "X.X.....X.X", "...XX.XX..."),
    pixels("..X.....X..", "X..X...X..X", "X.XXXXXXX.X", "XXX.XXX.XXX", "XXXXXXXXXXX", ".XXXXXXXXX.", "..X.....X..", ".X.......X."),
)
BOOM = pixels(".X.....X.", "..X.X.X..", "X..XXX..X", "..XXXXX..", "X..XXX..X", "..X.X.X..", ".X.....X.")
CANNON = pixels("......X......", ".....XXX.....", ".....XXX.....", ".XXXXXXXXXXX.",
                "XXXXXXXXXXXXX", "XXXXXXXXXXXXX", "XXXXXXXXXXXXX", "XXXXXXXXXXXXX")


def invaders(data, theme):
    t, sprites = THEMES[theme], SPRITES[theme]
    width, height, pitch, weeks = 850, 262, 14, data["weeks"]
    gx, gy, ship_y, home, speed = grid_left(weeks, pitch), 60, 216, width / 2, 320
    center = lambda cell: (gx + cell.col * pitch + 5.5, gy + cell.row * pitch + 5.5)
    targets = sorted((c for c in data["cells"] if c.count), key=lambda c: (c.col, -c.row))  # bottom row first

    shots, ship, x, clock = [], [(0, home)], home, .8
    for cell in targets:
        tx, ty = center(cell)
        travel = abs(tx - x) / speed
        ship += [(clock, x), (clock + travel, tx)]
        clock += travel
        rise = ship_y - 9 - ty
        shots.append((cell, clock, clock + rise / 650, rise))
        x, clock = tx, clock + .2
    finish = (shots[-1][2] if shots else clock) + .9
    ship += [(finish, x), (finish + abs(home - x) / speed, home)]
    duration = finish + abs(home - x) / speed + 1.2
    tl = Timeline(duration)

    body = [f'<defs><path id="crab-a" d="{CRAB[0]}"/><path id="crab-b" d="{CRAB[1]}"/><path id="boom" d="{BOOM}"/></defs>']
    body += [f'<rect x="{center(c)[0] - 1:.1f}" y="{center(c)[1] - 1:.1f}" width="2" height="2" fill="{t["grid"]}"/>'
             for c in data["cells"] if not c.count]
    for cell, fire, hit, rise in shots:
        cx, cy = center(cell)
        alien = tl([(0, "opacity:1;transform:scale(1)"), (hit, "opacity:1;transform:scale(1)"),
                    (hit + .15, "opacity:0;transform:scale(1.8)"), (duration - .9, "opacity:0;transform:scale(1)"),
                    (duration - .3, "opacity:1;transform:scale(1)")])
        bolt = tl([(0, "opacity:0;transform:translateY(0)"), (fire - .01, "opacity:0;transform:translateY(0)"),
                   (fire, "opacity:1;transform:translateY(0)"), (hit, f"opacity:1;transform:translateY({-rise:.1f}px)"),
                   (hit + .01, f"opacity:0;transform:translateY({-rise:.1f}px)")])
        boom = tl([(0, "opacity:0"), (hit, "opacity:0"), (hit + .01, "opacity:1"), (hit + .25, "opacity:1"),
                   (hit + .26, "opacity:0")])
        fill = sprites[cell.level]
        body.append(f'<g class="pop {alien}"><use href="#crab-a" x="{cx - 5.5:.1f}" y="{cy - 4:.1f}" fill="{fill}" class="fa"/>'
                    f'<use href="#crab-b" x="{cx - 5.5:.1f}" y="{cy - 4:.1f}" fill="{fill}" opacity="0" class="fb"/></g>'
                    f'<rect x="{cx - 1:.1f}" y="{ship_y - 9}" width="2" height="8" fill="{t["title"]}" opacity="0" class="{bolt}"/>'
                    f'<use href="#boom" x="{cx - 4.5:.1f}" y="{cy - 3.5:.1f}" fill="{t["title"]}" opacity="0" class="{boom}"/>')

    cannon = tl([(time, f"transform:translateX({pos - home:.1f}px)") for time, pos in ship])
    span = weeks * pitch - 3
    body.append(f'<g transform="translate({home} {ship_y})"><g class="{cannon}">'
                f'<path d="{CANNON}" transform="translate(-10.4 0) scale(1.6)" fill="{sprites[4]}"/></g></g>'
                f'<line x1="{gx}" x2="{gx + span}" y1="{ship_y + 22}" y2="{ship_y + 22}" stroke="{sprites[3]}" stroke-width="2"/>')

    css = (".pop{transform-box:fill-box;transform-origin:center}"
           ".fa{animation:fa 1s steps(1,end) infinite}@keyframes fa{0%{opacity:1}50%,100%{opacity:0}}"
           ".fb{animation:fb 1s steps(1,end) infinite}@keyframes fb{0%{opacity:0}50%,100%{opacity:1}}\n" + tl.css)
    return svg(theme, width, height, f"{data['name']}'s contribution invaders", "\n".join(body),
               heading=f"{data['name']}'s contribution invaders",
               subheading=f"{len(targets)} invaders · {data['total']:,} contributions", css=css)


# ---------------------------------------------------------------- tetris

def tetrominoes(cells):
    """Split contribution days into falling pieces of up to four touching cells."""
    active = {(c.col, c.row): c for c in cells if c.count}
    pieces, taken = [], set()
    for key in sorted(active, key=lambda k: (k[0], -k[1])):
        if key in taken:
            continue
        piece, queue = [], [key]
        while queue and len(piece) < 4:
            col, row = current = queue.pop(0)
            if current in taken:
                continue
            taken.add(current)
            piece.append(active[current])
            queue += [n for n in ((col, row + 1), (col + 1, row), (col, row - 1), (col - 1, row))
                      if n in active and n not in taken]
        pieces.append(piece)
    return pieces


def tetris(data, theme):
    t, palette, sprites = THEMES[theme], PALETTES[theme], SPRITES[theme]
    width, height, pitch, weeks = 850, 232, 13, data["weeks"]
    board_w, panel = weeks * pitch - 3, 80
    x0, well_top = (width - (board_w + 24 + panel)) / 2, 58
    board_top = well_top + 4 * pitch
    pieces = tetrominoes(data["cells"])

    clock, schedule = .6, []
    for piece in pieces:
        rows = max(c.row for c in piece) + 1  # lowest cell starts just above the board
        schedule.append((piece, clock, clock + rows * .05, rows))
        clock += rows * .05 + .1
    done = clock + .6
    clear = done + 1.1
    duration = clear + .8
    tl = Timeline(duration)

    def block(x, y, size, color):
        return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{size}" height="{size}" rx="1.5" fill="{color}"/>'
                f'<path d="M{x + 1.5:.1f},{y + size - 1.5:.1f}V{y + 1.5:.1f}H{x + size - 1.5:.1f}" fill="none" '
                f'stroke="{shade(color, 1.45)}" stroke-width="1.2" stroke-linecap="round"/>')

    px, py = x0 + board_w + 24, well_top - 6
    body = [f'<rect x="{x0 - 6}" y="{well_top - 6}" width="{board_w + 12}" height="{11 * pitch - 3 + 12}" rx="6" '
            f'fill="none" stroke="{t["border"]}"/>',
            slots("well", pitch, x0, board_top, board_w, 7 * pitch - 3, palette[0]),
            f'<rect x="{px}" y="{py}" width="{panel}" height="80" rx="6" fill="none" stroke="{t["border"]}"/>'
            f'<text x="{px + 10}" y="{py + 18}" class="small" font-weight="600">NEXT</text>'
            f'<rect x="{px}" y="{py + 92}" width="{panel}" height="61" rx="6" fill="none" stroke="{t["border"]}"/>'
            f'<text x="{px + 10}" y="{py + 110}" class="small" font-weight="600">PIECES</text>'
            f'<text x="{px + 10}" y="{py + 140}" font-size="20" font-weight="700" fill="{t["title"]}">{len(pieces)}</text>']

    previous = 0
    for piece, spawn, land, rows in schedule:
        fall = tl([(0, f"opacity:0;transform:translateY({-rows * pitch}px)"),
                   (spawn - .01, f"opacity:0;transform:translateY({-rows * pitch}px)"),
                   (spawn, f"opacity:1;transform:translateY({-rows * pitch}px);animation-timing-function:steps({rows},end)"),
                   (land, "opacity:1;transform:translateY(0)"), (clear, "opacity:1;transform:translateY(0)"),
                   (clear + .01, "opacity:0;transform:translateY(0)")])
        body.append(f'<g class="{fall}">' + "".join(
            block(x0 + c.col * pitch, board_top + c.row * pitch, pitch - 3, sprites[c.level]) for c in piece) + "</g>")

        left, top = min(c.col for c in piece), min(c.row for c in piece)
        cols, rows_tall = max(c.col for c in piece) - left + 1, max(c.row for c in piece) - top + 1
        mx, my = px + panel / 2 - cols * 9 / 2, py + 50 - rows_tall * 9 / 2
        preview = tl([(0, "opacity:0"), (previous, "opacity:0"), (previous + .01, "opacity:1"),
                      (spawn, "opacity:1"), (spawn + .01, "opacity:0")])
        body.append(f'<g opacity="0" class="{preview}">' + "".join(
            block(mx + (c.col - left) * 9, my + (c.row - top) * 9, 8, sprites[c.level]) for c in piece) + "</g>")
        previous = spawn

    flash = tl([(0, "opacity:0"), (done, "opacity:0"), (done + .15, "opacity:.55"), (done + .3, "opacity:0"),
                (done + .45, "opacity:.55"), (done + .6, "opacity:0"), (done + .75, "opacity:.55"), (done + .9, "opacity:0")])
    body.append(f'<rect x="{x0}" y="{board_top}" width="{board_w}" height="{7 * pitch - 3}" rx="2" '
                f'fill="{t["title"]}" opacity="0" class="{flash}"/>')
    return svg(theme, width, height, f"{data['name']}'s contribution tetris", "\n".join(body),
               heading=f"{data['name']}'s contribution tetris",
               subheading=f"{sum(map(len, pieces))} blocks · {data['total']:,} contributions", css=tl.css)


# ---------------------------------------------------------------- game of life

def life(data, theme):
    t, palette = THEMES[theme], PALETTES[theme]
    width, pitch, weeks, rows, pad, generation = 850, 14, data["weeks"], 15, 4, .16
    gx, gy = grid_left(weeks, pitch), 58
    height = gy + rows * pitch + 52

    # The calendar sits in the middle of a taller torus: on 7 wrapped rows it dies within a few generations.
    history = [frozenset((c.col, c.row + pad) for c in data["cells"] if c.count)]
    seen = set(history)
    while len(history) < 160:
        alive = history[-1]
        neighbours = Counter(((col + dc) % weeks, (row + dr) % rows)
                             for col, row in alive for dc in (-1, 0, 1) for dr in (-1, 0, 1) if dc or dr)
        nxt = frozenset(cell for cell, n in neighbours.items() if n == 3 or (n == 2 and cell in alive))
        if nxt in seen:
            break
        history.append(nxt)
        seen.add(nxt)
    settled = len(history) < 160
    run = len(history) * generation
    duration = max(run + 2, 6)
    tl = Timeline(duration)

    span = weeks * pitch - 3
    body = [slots("dish", pitch, gx, gy, span, rows * pitch - 3, palette[0])]
    for col, row in sorted(set().union(*history)):
        states = [(col, row) in alive for alive in history]
        stops = [(0, f"opacity:{int(states[0])}")] + [
            (i * generation, f"opacity:{int(states[i])}") for i in range(1, len(states)) if states[i] != states[i - 1]]
        body.append(f'<rect x="{gx + col * pitch}" y="{gy + row * pitch}" width="11" height="11" rx="2" '
                    f'fill="{palette[3]}" opacity="{int(states[0])}" class="{tl(stops, "steps(1,end)")}"/>')

    bar_y = gy + rows * pitch + 8
    progress = tl([(0, "transform:scaleX(0)"), (run, "transform:scaleX(1)")])
    body.append(f'<rect x="{gx}" y="{bar_y}" width="{span}" height="4" rx="2" fill="{t["grid"]}"/>'
                f'<rect x="{gx}" y="{bar_y}" width="{span}" height="4" rx="2" fill="{palette[3]}" class="bar {progress}"/>'
                f'<text x="{gx}" y="{bar_y + 24}" class="small">seeded with the last 12 months of contributions</text>'
                f'<text x="{gx + span}" y="{bar_y + 24}" class="small" text-anchor="end">'
                f'{len(history)}{"" if settled else "+"} generations{" until it settles" if settled else ""}</text>')
    css = ".bar{transform-box:fill-box;transform-origin:0 50%}\n" + tl.css
    return svg(theme, width, height, f"{data['name']}'s game of life", "\n".join(body),
               heading=f"{data['name']}'s game of life",
               subheading=f"{len(history[0])} seed cells · rules B3/S23", css=css)


# ---------------------------------------------------------------- pac-man

def mouth(angle, r=6.5):
    if not angle:
        return f"M{-r},0a{r},{r} 0 1 0 {2 * r},0a{r},{r} 0 1 0 {-2 * r},0"
    x, y = r * math.cos(math.radians(angle)), r * math.sin(math.radians(angle))
    return f"M0,0L{x:.2f},{-y:.2f}A{r},{r} 0 1 0 {x:.2f},{y:.2f}Z"


GHOST = "M-6.5,6.5V-.5A6.5,6.5 0 0 1 6.5,-.5V6.5l-2.17,-2l-2.17,2l-2.16,-2l-2.17,2l-2.16,-2l-2.17,2Z"


def pacman(data, theme):
    t, sprites = THEMES[theme], SPRITES[theme]
    yellow, pellet = ("#e3b341", "#d29922") if theme == "dark" else ("#d4a72c", "#bf8700")
    width, height, pitch, weeks = 850, 205, 14, data["weeks"]
    gx, gy, step, start = grid_left(weeks, pitch), 66, .032, .5
    center = lambda col, row: (gx + col * pitch + 5.5, gy + row * pitch + 5.5)
    order = lambda col, row: row * weeks + (col if row % 2 == 0 else weeks - 1 - col)  # zig-zag, row by row
    duration = start + 7 * weeks * step + 1.4
    tl = Timeline(duration)

    span = weeks * pitch - 3
    body = [f'<rect x="{gx - 10}" y="{gy - 10}" width="{span + 20}" height="{7 * pitch - 3 + 20}" rx="7" fill="none" '
            f'stroke="{t["accent"]}" stroke-width="2"/>'
            f'<rect x="{gx - 6}" y="{gy - 6}" width="{span + 12}" height="{7 * pitch - 3 + 12}" rx="4" fill="none" '
            f'stroke="{t["accent"]}" stroke-width="1" opacity=".5"/>']
    for cell in data["cells"]:
        cx, cy = center(cell.col, cell.row)
        eaten = start + order(cell.col, cell.row) * step
        cls = tl([(0, "opacity:1"), (eaten, "opacity:1"), (eaten + .01, "opacity:0"),
                  (duration - .6, "opacity:0"), (duration - .1, "opacity:1")])
        if cell.count:
            body.append(f'<rect x="{cx - 5:.1f}" y="{cy - 5:.1f}" width="10" height="10" rx="2" fill="{sprites[cell.level]}" class="{cls}"/>')
        else:
            body.append(f'<rect x="{cx - 1.3:.1f}" y="{cy - 1.3:.1f}" width="2.6" height="2.6" fill="{pellet}" class="{cls}"/>')

    path, facing = [], []
    for row in range(7):
        first, last = (0, weeks - 1) if row % 2 == 0 else (weeks - 1, 0)
        begin = start + order(first, row) * step
        path += [(begin, "transform:translate({:.1f}px,{:.1f}px)".format(*center(first, row))),
                 (begin + (weeks - 1) * step, "transform:translate({:.1f}px,{:.1f}px)".format(*center(last, row)))]
        facing.append((max(begin - step / 2, 0), f"transform:scaleX({1 if row % 2 == 0 else -1})"))
    move, face = tl(path), tl(facing, "steps(1,end)")
    home = "translate({:.1f} {:.1f})".format(*center(0, 0))

    for color, delay in (("#ff7b72", .95), ("#f778ba", .7), ("#79c0ff", .45)):
        body.append(f'<g transform="{home}" class="{move}" style="animation-delay:{delay}s">'
                    f'<path d="{GHOST}" fill="{color}"/><circle cx="-2.4" cy="-1.5" r="2" fill="#fff"/>'
                    f'<circle cx="2.4" cy="-1.5" r="2" fill="#fff"/><circle cx="-1.8" cy="-1.2" r=".9" fill="#1f6feb"/>'
                    f'<circle cx="3" cy="-1.2" r=".9" fill="#1f6feb"/></g>')
    body.append(f'<g transform="{home}" class="{move}"><g class="{face}">'
                f'<path d="{mouth(40)}" fill="{yellow}" class="m-open"/>'
                f'<path d="{mouth(18)}" fill="{yellow}" opacity="0" class="m-half"/>'
                f'<path d="{mouth(0)}" fill="{yellow}" opacity="0" class="m-shut"/></g></g>')

    css = (".m-open{animation:m-open .28s steps(1,end) infinite}@keyframes m-open{0%{opacity:1}25%,100%{opacity:0}}"
           ".m-half{animation:m-half .28s steps(1,end) infinite}@keyframes m-half{0%{opacity:0}25%{opacity:1}50%{opacity:0}75%,100%{opacity:1}}"
           ".m-shut{animation:m-shut .28s steps(1,end) infinite}@keyframes m-shut{0%,25%{opacity:0}50%{opacity:1}75%,100%{opacity:0}}\n"
           + tl.css)
    return svg(theme, width, height, f"{data['name']}'s contribution pac-man", "\n".join(body),
               heading=f"{data['name']}'s contribution pac-man",
               subheading=f"{sum(1 for c in data['cells'] if c.count)} power pellets · {data['total']:,} contributions",
               css=css)


ANIMATIONS = {
    "skyline": skyline,
    "invaders": invaders,
    "tetris": tetris,
    "life": life,
    "pacman": pacman,
}


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out = Path(sys.argv[1])
    login = sys.argv[2] if len(sys.argv) > 2 else os.environ["GITHUB_REPOSITORY_OWNER"]
    data = fetch(login)
    out.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        for name, render in ANIMATIONS.items():
            (out / f"{name}-{theme}.svg").write_text(render(data, theme), encoding="utf-8")
    print(f"{login}: {data['total']} contributions over {data['weeks']} weeks → "
          f"{len(ANIMATIONS) * len(THEMES)} animations in {out}/")


if __name__ == "__main__":
    main()
