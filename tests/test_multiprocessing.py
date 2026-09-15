#!/usr/bin/env python3
"""Direct multiprocessing safety smoke test for Chessreck."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import chess
from engine import MultiprocessingCoordinator


def main():
    mp = MultiprocessingCoordinator(workers=2, task_timeout=4.0)
    mp.start()
    board = chess.Board()
    features = mp.move_features(board.fen(), ["e2e4", "d2d4", "g1f3"])
    assert set(features) == {"e2e4", "d2d4", "g1f3"}
    assert features["e2e4"]["capture"] is False
    assert features["e2e4"]["check"] is False
    perft = mp.perft(board.fen(), 2)
    assert perft == 400, perft
    snap = mp.snapshot()
    assert snap["workers"] == 2
    assert snap["alive"] == 2
    assert snap["jobs"] >= 3
    mp.close()
    print(f"MP PASS: workers={snap['workers']} jobs={snap['jobs']} perft2={perft}")


if __name__ == "__main__":
    main()
