#!/usr/bin/env python3
"""Chessreck v0.1.0
Copyright (c) 2026 wyuri

Chessreck's original source code is provided by wyuri.
Stockfish is a separate open-source chess engine licensed under the GNU GPL v3.0.
See THIRD_PARTY_NOTICES.md for attribution and license information..
"""
import json
import os
import re
from pathlib import Path

import chess
import chess.engine

from engine import EngineManager

ROOT = Path(__file__).resolve().parent
STYLE_DIR = ROOT / "styles"
PROFILE_DIR = ROOT / "profiles"
DATA_DIR = ROOT / "data"
STYLE_DIR.mkdir(exist_ok=True)
PROFILE_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

ENGINE_PATHS = [
    "/data/data/com.termux/files/usr/bin/stockfish",
    "/usr/bin/stockfish",
    "stockfish",
]

DEFAULT_STYLE = {
    "name": "balanced",
    "risk": 0.35,
    "attack": 0.50,
    "tactics": 0.50,
    "sacrifices": 0.25,
    "queen_activity": 0.25,
    "positional": 0.50,
    "endgame": 0.50,
}


def engine_path():
    for path in ENGINE_PATHS:
        if path == "stockfish" or os.path.exists(path):
            return path
    return None


def safe_name(name, fallback="Bot"):
    """Make a user supplied name safe to use as a local filename."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    cleaned = cleaned.strip("._")
    return cleaned[:80] or fallback


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default.copy() if isinstance(default, dict) else default


def style():
    active = DATA_DIR / "active_style.json"
    active_data = load_json(active, {"name": "balanced"})
    name = active_data.get("name", "balanced")
    path = STYLE_DIR / f"{safe_name(name, 'balanced')}.json"
    raw = load_json(path, DEFAULT_STYLE)
    result = DEFAULT_STYLE.copy()
    result.update(raw)
    result["name"] = str(raw.get("name", name))
    for key in DEFAULT_STYLE:
        if key == "name":
            continue
        try:
            result[key] = max(0.0, min(1.0, float(result[key])))
        except (TypeError, ValueError):
            result[key] = DEFAULT_STYLE[key]
    return result


def prof(name):
    path = PROFILE_DIR / f"{safe_name(name)}.json"
    default = {
        "name": name,
        "games": 0,
        "moves": 0,
        "captures": 0,
        "checks": 0,
        "castles": 0,
        "queen_moves": 0,
    }
    data = load_json(path, default)
    for key in default:
        if key == "name":
            data[key] = name
        else:
            try:
                data[key] = int(data.get(key, default[key]))
            except (TypeError, ValueError):
                data[key] = default[key]
    return data


def move_input(board, text):
    text = text.strip()
    try:
        return board.parse_san(text)
    except ValueError as san_error:
        try:
            move = chess.Move.from_uci(text)
        except ValueError:
            raise ValueError("use SAN (example: Nf3) or UCI (example: g1f3)") from san_error
        if move not in board.legal_moves:
            raise ValueError("illegal move")
        return move


def history_show(history):
    print("\nMOVE HISTORY")
    if not history:
        print("(empty)")
        return
    for i in range(0, len(history), 2):
        print(f"{i // 2 + 1}. {history[i]} {history[i + 1] if i + 1 < len(history) else '...'}")


def save_profile(profile):
    path = PROFILE_DIR / f"{safe_name(profile['name'])}.json"
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def print_help():
    print("\nCommands: board | history | fen | style | help | quit")


def main():
    path = engine_path()
    if not path:
        print("Stockfish was not found. Chessreck will try its internal analysis resource.")

    print("\nCHESSRECK v0.3.3")
    print("Copyright (c) 2026 wyuri")
    print("Stockfish engine: GNU GPL v3.0 - see THIRD_PARTY_NOTICES.md")
    print("Who are you?\n1. White\n2. Black")
    while True:
        choice = input("> ").strip()
        if choice in ("1", "2"):
            me = choice == "1"
            break
        print("Choose 1 or 2.")

    opponent = input("Opponent name (default: Bot): ").strip() or "Bot"
    s = style()
    board = chess.Board()
    profile = prof(opponent)
    history = []
    manager = EngineManager(path, DATA_DIR, s, profile)

    try:
        manager.start()
    except RuntimeError as exc:
        print(f"Failed to start analysis: {exc}")
        manager.close()
        return

    print(f"\nYou: {'White' if me else 'Black'}")
    print(f"Opponent: {'Black' if me else 'White'}")
    print(f"Style: {s['name']}")
    print_help()

    try:
        while not board.is_game_over():
            actor = "YOU" if board.turn == me else "OPPONENT"
            raw = input(f"\n{actor} MOVE > ").strip()
            if not raw:
                continue
            command = raw.lower()
            if command == "quit":
                break
            if command == "board":
                print(board)
                continue
            if command == "history":
                history_show(history)
                continue
            if command == "fen":
                print(board.fen())
                continue
            if command == "style":
                print(json.dumps(s, indent=2, ensure_ascii=False))
                continue
            if command == "help":
                print_help()
                continue

            try:
                move = move_input(board, raw)
            except ValueError as exc:
                print("Invalid move:", exc)
                continue

            san = board.san(move)
            if board.turn != me:
                profile["moves"] += 1
                if board.is_capture(move):
                    profile["captures"] += 1
                if board.gives_check(move):
                    profile["checks"] += 1
                if board.is_castling(move):
                    profile["castles"] += 1
                piece = board.piece_at(move.from_square)
                if piece and piece.piece_type == chess.QUEEN:
                    profile["queen_moves"] += 1

            history.append(san)
            board.push(move)
            print(f"You played: {san}" if actor == "YOU" else f"Opponent played: {san}")

            if board.turn == me and not board.is_game_over():
                manager.submit(board)
                result = manager.result(wait=True)
                if result:
                    formatted = manager.format_result(board, result)
                    if formatted:
                        print("\n" + formatted)

        if history:
            profile["games"] += 1
            save_profile(profile)
        if board.is_game_over():
            print("\nRESULT:", board.result())
        else:
            print("\nSession stopped.")
        history_show(history)
    finally:
        manager.close()


if __name__ == "__main__":
    main()
