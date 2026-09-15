"""Integration smoke test using a fake Stockfish/Openix layer and real Theresia."""
import importlib.util
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Minimal chess facade so engine.py can be imported in an offline test sandbox.
chess = types.ModuleType("chess")
chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING = range(1, 7)
class Move:
    def __init__(self, uci): self._uci = uci
    def uci(self): return self._uci
    @staticmethod
    def from_uci(u): return Move(u)
chess.Move = Move
chess.Board = object
engine_mod = types.ModuleType("chess.engine")
engine_mod.SimpleEngine = object
engine_mod.EngineError = RuntimeError
engine_mod.Limit = lambda **kw: kw
chess.engine = engine_mod
sys.modules["chess"] = chess
sys.modules["chess.engine"] = engine_mod

spec = importlib.util.spec_from_file_location("engine", ROOT / "engine.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class Board:
    turn = True
    fullmove_number = 1
    move_stack = []
    def fen(self):
        return "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

class FakeStockfish:
    def analyse(self, board, limit, multipv):
        return [{"score": FakeScore(35), "pv": [Move("d2d4"), Move("d7d5")]},
                {"score": FakeScore(20), "pv": [Move("e2e4"), Move("e7e5")]}]
    def quit(self): pass
class FakeScore:
    def __init__(self, n): self.n=n
    def pov(self, turn): return self
    def score(self, mate_score=100000): return self.n

class FakeTheresia:
    def analyze(self, fen, depth=3, time_ms=1500):
        return {"bestmove":"d2d4","score":30,"confidence":0.62,"depth":depth,"nodes":1234,"adaptation":"stable-line"}
    def ping(self): return {"ok":True}
    def close(self): pass

m = mod.EngineManager.__new__(mod.EngineManager)
m.style={k:0.5 for k in ["risk","attack","tactics","sacrifices","queen_activity","positional","endgame"]}
m.profile={}
m.engine=FakeStockfish()
m.theresia=FakeTheresia()
m.openings=None
m.engine_path=None
m._closed=False
m.stockfish_depth=16
m.stockfish_multipv=5
m.theresia_depth=3
m.resources={k:mod.ResourceState(k) for k in ["theresia","stockfish","openix"]}
m._style_bonus=lambda board, move, pv: 0.0
m.health=lambda: {"resources":{k:v.snapshot() for k,v in m.resources.items()}}

result=m._analyze(Board())
assert result["decision"]["move"] == "d2d4"
assert result["decision"]["agreement"] == "agreement"
assert result["sources"]["theresia"]["available"]
assert result["sources"]["stockfish"]["available"]
print("FLOW PASS: main -> EngineManager -> Theresia + Stockfish -> fusion")

# Real Theresia bridge protocol check.
bridge = ROOT / "theresia" / "bridge.py"
proc = subprocess.run([sys.executable, "-c", f"import sys;sys.path.insert(0,{str(ROOT)!r});from theresia.bridge import TheresiaClient; t=TheresiaClient(); print(t.ping()); print(t.analyze('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',3,700)); t.close()"], capture_output=True, text=True, timeout=10)
if proc.returncode:
    raise SystemExit(proc.stderr)
print(proc.stdout.strip())
