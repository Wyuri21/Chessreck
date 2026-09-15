import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "theresia" / "theresia.js"
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
MATE_FEN = "7k/5Q2/7K/8/8/8/8/8 b - - 0 1"


def request(proc, payload):
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())


@pytest.fixture
def node_proc():
    proc = subprocess.Popen(
        ["node", str(SCRIPT)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1
    )
    yield proc
    proc.terminate()
    proc.wait(timeout=2)


def test_ping(node_proc):
    result = request(node_proc, {"cmd": "ping"})
    assert result["ok"] is True
    assert result["name"] == "Theresia"


def test_start_position_has_20_legal_moves(node_proc):
    result = request(node_proc, {"cmd": "legal_moves", "fen": START_FEN})
    assert result["count"] == 20
    assert "e2e4" in result["moves"]
    assert "g1f3" in result["moves"]


def test_simple_mate_has_no_legal_moves(node_proc):
    result = request(node_proc, {"cmd": "legal_moves", "fen": MATE_FEN})
    assert result["count"] == 0


def test_evaluation_is_symmetric_for_start_position(node_proc):
    white = request(node_proc, {"cmd": "evaluate", "fen": START_FEN})
    black_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1"
    black = request(node_proc, {"cmd": "evaluate", "fen": black_fen})
    assert white["score"] == -black["score"]


def test_analyze_returns_uci_move_and_confidence(node_proc):
    result = request(node_proc, {"cmd": "analyze", "fen": START_FEN, "depth": 2})
    assert isinstance(result["bestmove"], str)
    assert 0 <= result["confidence"] <= 1
    assert result["depth"] == 2
    assert result["nodes"] > 0
