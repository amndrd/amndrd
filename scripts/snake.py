#!/usr/bin/env python3
"""The contribution snake, in the look of Platane/snk but with its own route planning:

- it only ever moves over the calendar squares;
- every leg is the shortest path, then the one with the fewest turns, so no pointless loops;
- once everything is eaten it roams while the squares pop back in, then slides into the
  exact spot it started from, so the loop restarts without a jump.

Standard library only.

Usage: GITHUB_TOKEN=… python3 scripts/snake.py <output-dir> [login]
"""

import heapq
import os
import random
import sys
from pathlib import Path

from cards import Timeline, graphql

LEVELS = ("NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE")
PALETTES = {  # the colours of the Platane/snk version this replaces
    "dark": ("#161b22", "#01311f", "#034525", "#0f6d31", "#00c647"),
    "light": ("#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"),
}
SNAKE_COLOR = "#800080"
SEGMENTS = (14.4, 12.3, 10.8, 9.9)  # head to tail
PITCH, SQUARE, STEP = 16, 12, .1
DIRECTIONS = ((1, 0), (0, 1), (-1, 0), (0, -1))

CALENDAR_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar { weeks { contributionDays { weekday contributionLevel } } }
    }
  }
}"""


def fetch(login):
    weeks = graphql(CALENDAR_QUERY, login=login)["contributionsCollection"]["contributionCalendar"]["weeks"]
    return {(col, day["weekday"]): LEVELS.index(day["contributionLevel"])
            for col, week in enumerate(weeks) for day in week["contributionDays"]}


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def route(squares, body, goal, avoid=frozenset()):
    """Cells the head walks through to reach `goal`: fewest steps first, then fewest turns.

    The body (head first) follows the head, so segment i only blocks its square for the
    first len(body) - 1 - i steps; together with no reversing, the snake never crosses itself."""
    length, head = len(body), body[0]
    heading = (head[0] - body[1][0], head[1] - body[1][1]) if length > 1 else None
    start = (head, 0, heading)
    best, parent = {start: (0, 0)}, {}
    queue, pushed = [(0, 0, 0, start)], 0
    while queue:
        steps, turns, _, key = heapq.heappop(queue)
        cost, (cell, elapsed, direction) = (steps, turns), key
        if cost > best[key]:
            continue
        if cell == goal:
            path = []
            while key != start:
                path.append(key[0])
                key = parent[key]
            return path[::-1]
        for step in DIRECTIONS:
            nxt = (cell[0] + step[0], cell[1] + step[1])
            later = min(elapsed + 1, length)
            if (nxt not in squares or (nxt in avoid and nxt != goal) or nxt in body[:length - later]
                    or (direction is not None and step == (-direction[0], -direction[1]))):
                continue
            candidate = (cost[0] + 1, cost[1] + (direction is not None and step != direction))
            child = (nxt, later, step)
            if candidate < best.get(child, (1 << 30, 0)):
                best[child], parent[child] = candidate, key
                pushed += 1
                heapq.heappush(queue, (*candidate, pushed, child))
    return None


def visiting_order(start, targets):
    """Nearest neighbour, polished with 2-opt: a short open tour over the green squares."""
    order, here, left = [], start, set(targets)
    while left:
        here = min(left, key=lambda cell: (manhattan(here, cell), cell))
        order.append(here)
        left.remove(here)
    points, improved = [start] + order, True
    while improved:
        improved = False
        for i in range(1, len(points) - 1):
            for j in range(i + 1, len(points)):
                after = points[j + 1] if j + 1 < len(points) else None
                before = manhattan(points[i - 1], points[i]) + (manhattan(points[j], after) if after else 0)
                swapped = manhattan(points[i - 1], points[j]) + (manhattan(points[i], after) if after else 0)
                if swapped < before:
                    points[i:j + 1] = reversed(points[i:j + 1])
                    improved = True
    return points[1:]


def resting_place(squares, greens):
    """A straight spot a couple of squares away from the green ones, where the loop starts and ends.
    Empty if at all possible; on a nearly full calendar, the one covering the fewest green squares."""
    candidates = []
    for col, row in squares:
        for dx, dy in DIRECTIONS:
            body = [(col - dx * i, row - dy * i) for i in range(len(SEGMENTS))]
            if all(cell in squares for cell in body):
                covered = sum(cell in greens for cell in body)
                gap = min((manhattan(body[0], green) for green in greens - set(body)), default=2)
                candidates.append(((covered, abs(gap - 2), abs(row - 3), (dx, dy) != (1, 0), col), body))
    return min(candidates)[1]


def plan(levels):
    # The days still to come in the current week are drawn as empty squares too: a ragged last
    # column would leave dead-end squares that a snake can only leave by reversing through itself.
    cols = max(col for col, _ in levels) + 1
    squares = {(col, row) for col in range(cols) for row in range(7)}
    greens = {cell for cell, level in levels.items() if level}
    home = resting_place(squares, greens)
    body, trail, eaten = list(home), [home[0]], {}

    def walk(path):
        nonlocal body
        for cell in path:
            body = [cell] + body[:-1]
            trail.append(cell)
            if cell in greens and cell not in eaten:
                eaten[cell] = (len(trail) - 1) * STEP

    for target in visiting_order(home[0], greens):
        if target not in eaten:
            walk(route(squares, body, target) or route(squares, body[:1], target))
    finished = len(trail) - 1

    # Roam around the empty squares while the green ones grow back.
    # Empty squares away from the starting spot if possible; on a crowded calendar, whatever gets it out.
    rng = random.Random(sum(col * 7 + row for col, row in greens))
    empty = sorted(squares - greens - set(home)) or sorted(squares - set(home))
    for _ in range(12):
        if len(trail) - 1 - finished >= 34:
            break
        goal = rng.choice([cell for cell in empty if manhattan(cell, body[0]) >= 10] or empty)
        walk(route(squares, body, goal, avoid=greens | set(home)) or route(squares, body, goal, avoid=set(home))
             or route(squares, body, goal) or [])

    # Slide back into the starting spot: reach its tail square, then run along it to the head.
    walk(route(squares, body, home[-1], avoid=greens | set(home[:-1]))
         or route(squares, body, home[-1], avoid=set(home[:-1])) or route(squares, body[:1], home[-1]))
    walk(home[-2::-1])
    return {"squares": squares, "levels": levels, "home": home, "trail": trail, "eaten": eaten, "finished": finished}


def render(snake, theme):
    squares, levels, home, trail, eaten = snake["squares"], snake["levels"], snake["home"], snake["trail"], snake["eaten"]
    palette = PALETTES[theme]
    duration = (len(trail) - 1) * STEP
    tl = Timeline(duration)
    cols = max(col for col, _ in squares) + 1
    width, height = cols * PITCH, 7 * PITCH

    body = [f'<rect x="{col * PITCH + 2}" y="{row * PITCH + 2}" width="{SQUARE}" height="{SQUARE}" rx="2" '
            f'fill="{palette[0]}" stroke="#1b1f230a"/>' for col, row in sorted(squares)]

    # Green squares pop out when eaten and pop back in as a wave once the plate is clean.
    greens = sorted(eaten)
    regrow = snake["finished"] * STEP + .6
    left = min((col for col, _ in greens), default=0)
    span = max(max((col for col, _ in greens), default=0) - left, 1)
    for col, row in greens:
        gone, back = eaten[(col, row)], regrow + (col - left) / span * 1.1 + row * .02
        cls = tl([(0, "opacity:1;transform:scale(1)"), (gone, "opacity:1;transform:scale(1)"),
                  (gone + .12, "opacity:0;transform:scale(.3)"), (back, "opacity:0;transform:scale(0)"),
                  (back + .22, "opacity:1;transform:scale(1.35)"), (back + .45, "opacity:1;transform:scale(1)")])
        body.append(f'<rect x="{col * PITCH + 2}" y="{row * PITCH + 2}" width="{SQUARE}" height="{SQUARE}" rx="2" '
                    f'fill="{palette[levels[(col, row)]]}" class="pop {cls}"/>')

    # One keyframe per turn is enough: the head moves in straight lines between them.
    turns = [0] + [i for i in range(1, len(trail) - 1)
                   if (trail[i][0] - trail[i - 1][0], trail[i][1] - trail[i - 1][1])
                   != (trail[i + 1][0] - trail[i][0], trail[i + 1][1] - trail[i][1])] + [len(trail) - 1]
    move = tl([(i * STEP, f"transform:translate({trail[i][0] * PITCH}px,{trail[i][1] * PITCH}px)") for i in turns])
    for i, size in reversed(list(enumerate(SEGMENTS))):
        # Segment i replays the head's path i steps late — a negative delay keeps the loop seamless.
        offset = (PITCH - size) / 2
        body.append(f'<g transform="translate({home[i][0] * PITCH} {home[i][1] * PITCH})" class="{move}" '
                    f'style="animation-delay:-{duration - i * STEP:.2f}s">'
                    f'<rect x="{offset:.1f}" y="{offset:.1f}" width="{size}" height="{size}" rx="{size / 3.2:.1f}" '
                    f'fill="{SNAKE_COLOR}"/></g>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Contribution graph, eaten by a snake">
<title>Contribution graph, eaten by a snake</title>
<style>
  .pop {{ transform-box: fill-box; transform-origin: center; }}
  {tl.css}
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
    snake = plan(fetch(login))
    out.mkdir(parents=True, exist_ok=True)
    (out / "github-snake.svg").write_text(render(snake, "light"), encoding="utf-8")
    (out / "github-snake-dark.svg").write_text(render(snake, "dark"), encoding="utf-8")
    print(f"{login}: {len(snake['eaten'])} green squares eaten in {snake['finished']} steps, "
          f"loop of {(len(snake['trail']) - 1) * STEP:.1f}s → 2 snakes in {out}/")


if __name__ == "__main__":
    main()
