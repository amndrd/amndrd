#!/usr/bin/env python3
"""Community chess played through issues.

Every legal move in the README links to a pre-filled issue titled `chess|move|<uci>|<ply>`.
The chess workflow runs this script on the new issue: it validates the move, updates
chess/game.json, redraws chess/board.svg and the README section, and writes the reply.

Usage:
  python3 scripts/chess_game.py render   # redraw board + README from chess/game.json
  python3 scripts/chess_game.py play     # apply $ISSUE_TITLE for $ISSUE_USER (in the workflow)
"""

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

import chess
import chess.svg

ROOT = Path(__file__).resolve().parent.parent
STATE, BOARD, README = ROOT / "chess" / "game.json", ROOT / "chess" / "board.svg", ROOT / "README.md"
REPO = os.environ.get("GITHUB_REPOSITORY") or "amndrd/amndrd"
START, END = "<!-- chess:start -->", "<!-- chess:end -->"
COLORS = {
    "square light": "#eeeed2", "square dark": "#769656",
    "square light lastmove": "#f6f669", "square dark lastmove": "#baca2b",
    "margin": "#161b22", "coord": "#c9d1d9", "inner border": "#30363d", "outer border": "#30363d",
}


def load():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"moves": [], "players": {}, "games": []}


def replay(state):
    board = chess.Board()
    for move in state["moves"]:
        board.push_uci(move["uci"])
    return board


def issue_link(title):
    body = "Just click **Create** — your move is already in the title. A GitHub Action plays it within a minute."
    return f"https://github.com/{REPO}/issues/new?title={quote(title)}&body={quote(body)}"


def user_link(login):
    return f'<a href="https://github.com/{login}">@{login}</a>'


def outcome_text(outcome):
    if outcome.winner is None:
        return f"Draw by {outcome.termination.name.replace('_', ' ').lower()}"
    winner = "White" if outcome.winner else "Black"
    return f"{outcome.termination.name.replace('_', ' ').capitalize()} — {winner} wins"


def render(state):
    board = replay(state)
    last = board.peek() if board.move_stack else None
    check = board.king(board.turn) if board.is_check() else None
    BOARD.parent.mkdir(exist_ok=True)
    BOARD.write_text(chess.svg.board(board, size=400, lastmove=last, check=check, colors=COLORS))

    ply, outcome = len(state["moves"]), board.outcome(claim_draw=True)
    lines = [
        "## ♟️ Community chess",
        "",
        "Anyone can play. Pick a move below, click **Create** on the issue that opens, "
        "and a GitHub Action plays it within a minute.",
        "",
        f'<p align="center"><img src="https://raw.githubusercontent.com/{REPO}/main/chess/board.svg?v={len(state["games"])}-{ply}" '
        f'width="400" alt="Chess board after {ply} moves"></p>',
        "",
    ]
    status = []
    if outcome:
        status.append(f"<b>{outcome_text(outcome)}</b>")
    else:
        status.append(f"<b>{'White' if board.turn else 'Black'} to play</b> · move {board.fullmove_number}")
    if state["moves"]:
        status.append(f"last move <b>{state['moves'][-1]['san']}</b> by {user_link(state['moves'][-1]['user'])}")
    lines += [f'<p align="center">{" · ".join(status)}</p>', ""]

    if outcome:
        lines += [f'<p align="center">🏁 <a href="{issue_link("chess|new")}"><b>Start a new game</b></a></p>', ""]
    else:
        by_square = {}
        for move in board.legal_moves:
            by_square.setdefault(move.from_square, []).append(move)
        lines += ["| Piece | Moves |", "| :--- | :--- |"]
        for square in sorted(by_square, key=lambda s: (board.piece_type_at(s), s)):
            piece = board.piece_at(square)
            links = " · ".join(f"[{board.san(move)}]({issue_link(f'chess|move|{move.uci()}|{ply}')})"
                               for move in sorted(by_square[square], key=lambda m: board.san(m)))
            lines.append(f"| {piece.unicode_symbol()} {chess.square_name(square)} | {links} |")
        lines.append("")

    if state["moves"]:
        rows = [f"| {i // 2 + 1}{'.' if i % 2 == 0 else '…'} | {move['san']} | {user_link(move['user'])} |"
                for i, move in enumerate(state["moves"])]
        lines += ["<details><summary>Moves so far</summary>", "", "| # | Move | Player |", "| :-- | :-- | :-- |",
                  *rows, "", "</details>", ""]
    if state["players"]:
        top = sorted(state["players"].items(), key=lambda item: (-item[1], item[0].lower()))[:5]
        lines += ["**Top players:** " + " · ".join(f"{user_link(login)} ({count})" for login, count in top), ""]
    if state["games"]:
        lines += [f"<sub>{len(state['games'])} finished game{'s' if len(state['games']) > 1 else ''} so far.</sub>", ""]

    readme = README.read_text()
    if START not in readme or END not in readme:
        sys.exit(f"README.md is missing the {START} / {END} markers")
    head, rest = readme.split(START, 1)
    README.write_text(f"{head}{START}\n{chr(10).join(lines)}\n{END}{rest.split(END, 1)[1]}")


def play():
    title, user = os.environ["ISSUE_TITLE"].strip(), os.environ["ISSUE_USER"]
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    state = load()
    board = replay(state)
    board_url = f"https://github.com/{owner or REPO.split('/')[0]}"
    changed, summary = False, ""
    parts = title.split("|")

    if parts == ["chess", "new"]:
        if board.outcome(claim_draw=True) or not state["moves"] or user.lower() == owner.lower():
            if state["moves"]:
                outcome = board.outcome(claim_draw=True)
                state["games"].append({"moves": len(state["moves"]),
                                       "result": outcome.result() if outcome else "abandoned"})
            state["moves"] = []
            changed, summary = True, f"new game started by @{user}"
            reply = f"♟️ New game started. White to play — [make the first move]({board_url})!"
        else:
            reply = f"A game is still in progress — [jump in and play a move]({board_url}) instead."
    elif (len(parts) == 4 and parts[:2] == ["chess", "move"]
          and re.fullmatch(r"[a-h][1-8][a-h][1-8][qrbn]?", parts[2]) and parts[3].isdigit()):
        move = chess.Move.from_uci(parts[2])
        if int(parts[3]) != len(state["moves"]) or move not in board.legal_moves:
            reply = (f"Someone moved just before you, so this move no longer fits the board. "
                     f"[Pick a fresh one]({board_url}).")
        else:
            san = board.san(move)
            board.push(move)
            state["moves"].append({"uci": move.uci(), "san": san, "user": user})
            state["players"][user] = state["players"].get(user, 0) + 1
            changed, summary = True, f"{san} by @{user}"
            outcome = board.outcome(claim_draw=True)
            if outcome:
                reply = f"♟️ **{san}** — {outcome_text(outcome)}! 🎉 [See the final position]({board_url})."
            else:
                side = "White" if board.turn else "Black"
                reply = (f"♟️ **{san}** played{' — check!' if board.is_check() else ''}. "
                         f"{side} to play next: [back to the board]({board_url}).")
    else:
        reply = f"I couldn't read a chess move in this title. [Use one of the links on the board]({board_url})."

    if changed:
        STATE.parent.mkdir(exist_ok=True)
        STATE.write_text(json.dumps(state, indent=2) + "\n")
        render(state)
    Path(os.environ["REPLY_FILE"]).write_text(reply + "\n")
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as output:
        output.write(f"changed={'true' if changed else 'false'}\nsummary={summary}\n")
    print(reply)


if __name__ == "__main__":
    if sys.argv[1:] == ["render"]:
        state = load()
        STATE.parent.mkdir(exist_ok=True)
        STATE.write_text(json.dumps(state, indent=2) + "\n")
        render(state)
    elif sys.argv[1:] == ["play"]:
        play()
    else:
        sys.exit(__doc__)
