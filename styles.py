#!/usr/bin/env python3
"""Chessreck Style Manager.
Copyright (c) 2026 wyuri
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SD = ROOT / "styles"
DD = ROOT / "data"
SD.mkdir(exist_ok=True)
DD.mkdir(exist_ok=True)

FIELDS = ["risk", "attack", "tactics", "sacrifices", "queen_activity", "positional", "endgame"]


def clean_name(name):
    return "_".join(name.strip().lower().split())


def read_style(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


while True:
    print("\nCHESSRECK STYLE MANAGER")
    print("1. List styles\n2. Create style\n3. Activate style\n4. Delete style\n5. Exit")
    c = input("> ").strip()
    if c == "1":
        files = sorted(SD.glob("*.json"))
        if not files:
            print("(no styles)")
        for p in files:
            data = read_style(p)
            if data:
                print("-", data.get("name", p.stem))
    elif c == "2":
        n = clean_name(input("Style name: "))
        if not n or n in ("active_style",):
            print("Invalid style name.")
            continue
        s = {"name": n}
        for f in FIELDS:
            while True:
                try:
                    v = float(input(f"{f} [0..1]: "))
                    if 0 <= v <= 1:
                        s[f] = v
                        break
                except ValueError:
                    pass
                print("Enter a number from 0 to 1.")
        (SD / f"{n}.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
        print("Style created.")
    elif c == "3":
        n = clean_name(input("Style: "))
        if (SD / f"{n}.json").exists():
            (DD / "active_style.json").write_text(json.dumps({"name": n}, indent=2), encoding="utf-8")
            print("Active style:", n)
        else:
            print("Style not found.")
    elif c == "4":
        n = clean_name(input("Delete style: "))
        if n == "balanced":
            print("The built-in balanced style cannot be deleted.")
            continue
        target = SD / f"{n}.json"
        if target.exists():
            target.unlink()
            print("Style deleted.")
        else:
            print("Style not found.")
    elif c == "5":
        break
