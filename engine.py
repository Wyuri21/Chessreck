#!/usr/bin/env python3
"""Chessreck v0.1.0 central orchestration layer.

The TUI talks only to EngineManager. EngineManager owns scheduling, resource
lifecycle, cache, health, normalization, Theresia control, Stockfish usage,
opening context, fusion, and graceful degradation.
"""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import chess
import chess.engine

try:
    from Openix import ChessOpeningsLibrary
except ImportError:
    ChessOpeningsLibrary = None

try:
    from theresia.bridge import TheresiaClient
except ImportError:
    TheresiaClient = None



# ---------- isolated multiprocessing workers ----------
def _mp_worker_main(request_queue, response_queue):
    """Long-lived spawn-safe worker.

    This function is deliberately top-level. Child processes import this module
    under the spawn start method, but importing the module never creates a
    process. Workers only start when EngineManager explicitly starts them.
    """
    import chess as _chess

    while True:
        task = request_queue.get()
        if task is None:
            return
        task_id, operation, payload = task
        try:
            if operation == "move_features":
                board = _chess.Board(payload["fen"])
                features = {}
                for uci in payload["moves"]:
                    try:
                        move = _chess.Move.from_uci(uci)
                        if move not in board.legal_moves:
                            continue
                        before = 0
                        for piece in board.piece_map().values():
                            value = {
                                _chess.PAWN: 100, _chess.KNIGHT: 320,
                                _chess.BISHOP: 330, _chess.ROOK: 500,
                                _chess.QUEEN: 900, _chess.KING: 0,
                            }[piece.piece_type]
                            before += value if piece.color == board.turn else -value
                        test = board.copy(stack=False)
                        capture = board.is_capture(move)
                        check = board.gives_check(move)
                        moving = board.piece_at(move.from_square)
                        test.push(move)
                        after = 0
                        for piece in test.piece_map().values():
                            value = {
                                _chess.PAWN: 100, _chess.KNIGHT: 320,
                                _chess.BISHOP: 330, _chess.ROOK: 500,
                                _chess.QUEEN: 900, _chess.KING: 0,
                            }[piece.piece_type]
                            after += value if piece.color == board.turn else -value
                        features[uci] = {
                            "material_delta": after - before,
                            "capture": capture,
                            "check": check,
                            "piece": moving.piece_type if moving else None,
                            "pieces_after": len(test.piece_map()),
                            "legal_after": len(list(test.legal_moves)),
                        }
                    except (ValueError, TypeError):
                        continue
                response_queue.put((task_id, {"ok": True, "features": features}))
            elif operation == "perft":
                board = _chess.Board(payload["fen"])
                depth = max(1, min(5, int(payload["depth"])))

                def _perft(node, remaining):
                    if remaining == 0:
                        return 1
                    total = 0
                    for mv in node.legal_moves:
                        child = node.copy(stack=False)
                        child.push(mv)
                        total += _perft(child, remaining - 1)
                    return total

                response_queue.put((task_id, {"ok": True, "nodes": _perft(board, depth)}))
            elif operation == "ping":
                response_queue.put((task_id, {"ok": True, "pid": os.getpid()}))
            else:
                raise ValueError("unknown multiprocessing operation")
        except Exception as exc:
            response_queue.put((task_id, {"ok": False, "error": str(exc)}))


class MultiprocessingCoordinator:
    """Bounded, restartable CPU sidecar for Chessreck.

    It uses spawn explicitly and never creates workers during import. The
    coordinator owns process lifecycle and exposes only small, serializable
    tasks, keeping Stockfish and Theresia in the main EngineManager process.
    """

    def __init__(self, workers=1, task_timeout=4.0):
        requested = int(workers)
        self.workers = max(1, min(8, requested))
        self.task_timeout = max(0.25, float(task_timeout))
        self._ctx = multiprocessing.get_context("spawn")
        self._requests = None
        self._responses = None
        self._processes = []
        self._lock = threading.RLock()
        self._next_id = 0
        self.started = False
        self.jobs = 0
        self.failures = 0
        self.restarts = 0
        self.last_error = None
        self.total_ms = 0.0

    def start(self):
        with self._lock:
            if self.started:
                return
            self._requests = self._ctx.Queue(maxsize=max(4, self.workers * 2))
            self._responses = self._ctx.Queue(maxsize=max(4, self.workers * 2))
            self._processes = []
            try:
                for index in range(self.workers):
                    process = self._ctx.Process(
                        target=_mp_worker_main,
                        args=(self._requests, self._responses),
                        name=f"chessreck-mp-{index + 1}",
                    )
                    process.daemon = True
                    process.start()
                    self._processes.append(process)
                self.started = True
                self._request_locked("ping", {}, timeout=min(2.0, self.task_timeout))
            except Exception:
                self._stop_locked()
                raise

    def _request_locked(self, operation, payload, timeout=None):
        if not self.started:
            raise RuntimeError("multiprocessing coordinator is not started")
        timeout = self.task_timeout if timeout is None else max(0.1, timeout)
        self._next_id += 1
        task_id = self._next_id
        started = time.perf_counter()
        self._requests.put((task_id, operation, payload), timeout=timeout)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("multiprocessing task timed out")
            response_id, response = self._responses.get(timeout=remaining)
            if response_id != task_id:
                continue
            elapsed = (time.perf_counter() - started) * 1000
            self.jobs += 1
            self.total_ms += elapsed
            if not response.get("ok"):
                raise RuntimeError(response.get("error", "multiprocessing worker failed"))
            return response["features"] if operation == "move_features" else response

    def move_features(self, fen, moves):
        moves = list(dict.fromkeys(moves))
        if not moves:
            return {}
        with self._lock:
            try:
                return self._request_locked("move_features", {"fen": fen, "moves": moves})
            except Exception as exc:
                self.failures += 1
                self.last_error = str(exc)
                self.restart()
                return {}

    def perft(self, fen, depth=3):
        with self._lock:
            return self._request_locked("perft", {"fen": fen, "depth": depth}, timeout=max(self.task_timeout, 8.0))

    def restart(self):
        with self._lock:
            self.restarts += 1
            self._stop_locked()
            self.start()

    def _stop_locked(self):
        for _ in self._processes:
            try:
                self._requests.put(None, timeout=0.2)
            except Exception:
                break
        for process in self._processes:
            try:
                process.join(timeout=0.5)
            except Exception:
                pass
            if process.is_alive():
                try:
                    process.terminate()
                except Exception:
                    pass
        self._processes = []
        for queue in (self._requests, self._responses):
            try:
                if queue is not None:
                    queue.close()
                    queue.join_thread()
            except Exception:
                pass
        self._requests = None
        self._responses = None
        self.started = False

    def close(self):
        with self._lock:
            self._stop_locked()

    def snapshot(self):
        alive = sum(1 for process in self._processes if process.is_alive())
        return {
            "available": self.started and alive == len(self._processes),
            "workers": self.workers,
            "alive": alive,
            "jobs": self.jobs,
            "failures": self.failures,
            "restarts": self.restarts,
            "last_error": self.last_error,
            "average_ms": round(self.total_ms / self.jobs, 2) if self.jobs else 0.0,
        }


class ResourceState:
    def __init__(self, name: str):
        self.name = name
        self.available = False
        self.failures = 0
        self.calls = 0
        self.last_error = None
        self.last_ok = 0.0
        self.total_ms = 0.0

    def ok(self, elapsed_ms: float):
        self.available = True
        self.failures = 0
        self.last_error = None
        self.last_ok = time.time()
        self.calls += 1
        self.total_ms += elapsed_ms

    def fail(self, error: Exception | str):
        self.available = False
        self.failures += 1
        self.last_error = str(error)
        self.calls += 1

    def snapshot(self):
        return {
            "available": self.available,
            "failures": self.failures,
            "calls": self.calls,
            "last_error": self.last_error,
            "last_ok": self.last_ok,
            "average_ms": round(self.total_ms / self.calls, 2) if self.calls else 0.0,
        }


class EngineManager:
    """Chessreck's central brain.

    Theresia is the internal controller/reasoning layer. Stockfish is an
    external computational resource. Openix supplies opening knowledge. None
    of those resources is allowed to own the Chessreck lifecycle.
    """

    def __init__(self, engine_path, cache_dir, style, profile):
        self.engine_path = engine_path
        self.cache_path = Path(cache_dir) / "analysis_cache.json"
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.style = style
        self.profile = profile
        # Process creation is explicit and lazy. Spawn re-imports this module,
        # but import itself never creates another process.
        try:
            self.cpu_count = max(1, multiprocessing.cpu_count())
        except NotImplementedError:
            self.cpu_count = 1
        configured_workers = os.environ.get("CHESSRECK_MP_WORKERS")
        try:
            configured_workers = int(configured_workers) if configured_workers else max(1, min(4, self.cpu_count - 1 if self.cpu_count > 1 else 1))
        except ValueError:
            configured_workers = max(1, min(4, self.cpu_count - 1 if self.cpu_count > 1 else 1))
        self.mp = MultiprocessingCoordinator(workers=configured_workers)

        self.engine = None
        self.theresia = None
        self.openings = None

        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chessreck-core")
        self.future = None
        self._pending = None
        self._state_lock = threading.RLock()
        self._generation = 0
        self._closed = False
        self._started = False

        self.resources = {
            "theresia": ResourceState("theresia"),
            "stockfish": ResourceState("stockfish"),
            "openix": ResourceState("openix"),
        }
        self.cache_ttl = 30 * 24 * 60 * 60
        self.cache_max_entries = 5000
        self.cache_max_bytes = 20 * 1024 * 1024
        self.cache_version = 4
        self.analysis_timeout = 8.0
        self.theresia_depth = 3
        self.stockfish_depth = 16
        self.stockfish_multipv = 5
        self._load_openings()

    # ---------- lifecycle ----------
    def _load_openings(self):
        if ChessOpeningsLibrary is None:
            self.resources["openix"].fail("Openix unavailable")
            return
        try:
            self.openings = ChessOpeningsLibrary()
            self.openings.load_builtin_openings()
            self.resources["openix"].available = True
        except Exception as exc:
            self.openings = None
            self.resources["openix"].fail(exc)

    def start(self):
        if self._closed:
            raise RuntimeError("Engine manager is closed")
        if self._started:
            return
        if self.engine is None and self.engine_path:
            try:
                self.engine = chess.engine.SimpleEngine.popen_uci(self.engine_path)
                self.resources["stockfish"].available = True
            except (OSError, chess.engine.EngineError) as exc:
                self.engine = None
                self.resources["stockfish"].fail(exc)

        if self.theresia is None and TheresiaClient is not None:
            try:
                self.theresia = TheresiaClient()
                pong = self.theresia.ping()
                if pong.get("ok") is not True:
                    raise RuntimeError("Theresia ping failed")
                self.resources["theresia"].available = True
            except Exception as exc:
                self._close_theresia()
                self.resources["theresia"].fail(exc)

        if self.engine is None and self.theresia is None:
            self._started = True
            raise RuntimeError("No analysis resource is available")
        try:
            self.mp.start()
        except Exception as exc:
            # CPU sidecar is optional. Core analysis must survive its loss.
            self.mp.last_error = str(exc)
            self.mp.failures += 1
        self._started = True

    def _close_theresia(self):
        if self.theresia is not None:
            try:
                self.theresia.close()
            except Exception:
                pass
        self.theresia = None

    def _restart_theresia(self):
        self._close_theresia()
        if TheresiaClient is None or self._closed:
            return False
        try:
            self.theresia = TheresiaClient()
            self.theresia.ping()
            self.resources["theresia"].available = True
            return True
        except Exception as exc:
            self._close_theresia()
            self.resources["theresia"].fail(exc)
            return False

    def _restart_stockfish(self):
        if self._closed or not self.engine_path:
            return False
        try:
            self.engine = chess.engine.SimpleEngine.popen_uci(self.engine_path)
            self.resources["stockfish"].available = True
            return True
        except Exception as exc:
            self.engine = None
            self.resources["stockfish"].fail(exc)
            return False

    def close(self):
        with self._state_lock:
            self._closed = True
            self._pending = None
            future = self.future
        if future is not None and not future.done():
            try:
                future.result(timeout=self.analysis_timeout + 2.0)
            except Exception:
                pass
        if self.engine is not None:
            try:
                self.engine.quit()
            except Exception:
                pass
        self._close_theresia()
        self.engine = None
        try:
            self.mp.close()
        except Exception:
            pass
        self.executor.shutdown(wait=True, cancel_futures=True)

    # ---------- knowledge ----------
    def opening_info(self, board):
        if self.openings is None:
            return None
        started = time.perf_counter()
        try:
            replay = chess.Board()
            moves = []
            for move in board.move_stack:
                moves.append(replay.san(move))
                replay.push(move)
            matches = self.openings.find_openings_after_moves(moves)
            self.resources["openix"].ok((time.perf_counter() - started) * 1000)
            if not matches:
                return None
            opening = matches[0]
            return {"eco": getattr(opening, "eco_code", "?"), "name": getattr(opening, "name", "Unknown opening")}
        except Exception as exc:
            self.resources["openix"].fail(exc)
            return None

    # ---------- cache ----------
    def _cache_load(self):
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict) or raw.get("version") != self.cache_version:
            return {}
        return self._cache_cleanup(raw.get("entries", {}))

    def _cache_save(self, entries):
        entries = self._cache_cleanup(entries)
        payload = {"version": self.cache_version, "entries": entries}
        temp = self.cache_path.with_suffix(".tmp")
        try:
            temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            temp.replace(self.cache_path)
        except OSError:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass

    def _cache_cleanup(self, entries):
        now = time.time()
        if not isinstance(entries, dict):
            return {}
        cleaned = {}
        for key, value in entries.items():
            if not isinstance(value, dict) or "result" not in value:
                continue
            last = float(value.get("last_used", value.get("created", 0)))
            if now - last <= self.cache_ttl:
                cleaned[key] = value
        if len(cleaned) > self.cache_max_entries:
            cleaned = dict(sorted(cleaned.items(), key=lambda x: float(x[1].get("last_used", 0)), reverse=True)[:self.cache_max_entries])
        while cleaned:
            raw = json.dumps({"version": self.cache_version, "entries": cleaned}, ensure_ascii=False, separators=(",", ":"))
            if len(raw.encode()) <= self.cache_max_bytes:
                break
            oldest = min(cleaned, key=lambda k: float(cleaned[k].get("last_used", 0)))
            del cleaned[oldest]
        return cleaned

    def _style_fingerprint(self):
        payload = {key: self.style.get(key) for key in sorted(self.style)}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _analysis_context(self):
        return {
            "style": self._style_fingerprint(),
            "stockfish_depth": self.stockfish_depth,
            "stockfish_multipv": self.stockfish_multipv,
            "theresia_depth": self.theresia_depth,
            "fusion": 2,
            "resilience": 1,
        }

    def _position_key(self, board):
        payload = {"fen": board.fen(), "context": self._analysis_context()}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _cache_get(self, key):
        data = self._cache_load()
        entry = data.get(key)
        if not isinstance(entry, dict) or "result" not in entry:
            return None
        entry["last_used"] = time.time()
        self._cache_save(data)
        return entry["result"]

    def _cache_put(self, key, result):
        data = self._cache_load()
        now = time.time()
        data[key] = {"created": now, "last_used": now, "result": result}
        self._cache_save(data)

    # ---------- resource analysis ----------
    def _analyze_theresia(self, board):
        if self.theresia is None:
            return {"available": False, "source": "theresia"}
        started = time.perf_counter()
        try:
            data = self.theresia.analyze(board.fen(), depth=self.theresia_depth, time_ms=1500)
            elapsed = (time.perf_counter() - started) * 1000
            self.resources["theresia"].ok(elapsed)
            return {
                "available": True, "source": "theresia",
                "bestmove": data.get("bestmove"), "score": int(data.get("score", 0)),
                "confidence": float(data.get("confidence", 0.0)),
                "depth": int(data.get("depth", 0)), "nodes": int(data.get("nodes", 0)),
                "adaptation": data.get("adaptation"), "elapsed_ms": round(elapsed, 2),
            }
        except Exception as exc:
            self.resources["theresia"].fail(exc)
            self._restart_theresia()
            return {"available": False, "source": "theresia", "error": str(exc)}

    def _analyze_stockfish(self, board):
        if self.engine is None:
            return {"available": False, "source": "stockfish", "choices": []}
        started = time.perf_counter()
        try:
            infos = self.engine.analyse(board, chess.engine.Limit(depth=self.stockfish_depth), multipv=self.stockfish_multipv)
            if isinstance(infos, dict):
                infos = [infos]
            choices = []
            for info in infos:
                pv = info.get("pv", [])
                if not pv:
                    continue
                raw = info["score"].pov(board.turn).score(mate_score=100000)
                choices.append({"score": int(raw), "move": pv[0].uci(), "pv": [m.uci() for m in pv]})
            elapsed = (time.perf_counter() - started) * 1000
            self.resources["stockfish"].ok(elapsed)
            return {"available": True, "source": "stockfish", "depth": self.stockfish_depth, "choices": choices, "elapsed_ms": round(elapsed, 2)}
        except Exception as exc:
            self.resources["stockfish"].fail(exc)
            try:
                self.engine.quit()
            except Exception:
                pass
            self.engine = None
            self._restart_stockfish()
            return {"available": False, "source": "stockfish", "choices": [], "error": str(exc)}

    # ---------- Chessreck decision layer ----------
    def _theresia_directive(self, board, theresia, stockfish):
        """Translate Theresia's result into control signals, not fake strength."""
        move = theresia.get("bestmove") if theresia.get("available") else None
        confidence = max(0.0, min(1.0, float(theresia.get("confidence", 0.0))))
        sf_moves = {x.get("move") for x in stockfish.get("choices", [])}
        tactical = theresia.get("adaptation") == "tactical-extension"
        if move and move in sf_moves:
            return {"mode": "confirm", "preferred": move, "authority": 0.70 + confidence * 0.25}
        if tactical:
            return {"mode": "challenge", "preferred": move, "authority": 0.55 + confidence * 0.20}
        return {"mode": "cross-check", "preferred": move, "authority": 0.45 + confidence * 0.20}

    def _fuse(self, board, theresia, stockfish, opening):
        sf_choices = stockfish.get("choices", [])
        th_move = theresia.get("bestmove") if theresia.get("available") else None
        sf_top = sf_choices[0] if sf_choices else None
        directive = self._theresia_directive(board, theresia, stockfish)

        if th_move and sf_top and th_move == sf_top["move"]:
            final_move = th_move
            status = "agreement"
            confidence = min(1.0, 0.72 + theresia.get("confidence", 0.0) * 0.22)
        elif sf_top and directive.get("mode") != "challenge":
            final_move = sf_top["move"]
            status = "stockfish-cross-check"
            confidence = min(1.0, 0.50 + sf_top["score"] / 4000.0 + theresia.get("confidence", 0.0) * 0.10)
        elif th_move:
            final_move = th_move
            status = "theresia-challenge"
            confidence = min(1.0, directive["authority"])
        else:
            return {"fen": board.fen(), "choices": [], "opening": opening, "decision": {"move": None, "confidence": 0.0, "agreement": "no-resource"}, "sources": {"theresia": theresia, "stockfish": stockfish}, "health": self.health()}

        choices = []
        candidate_moves = [item["move"] for item in sf_choices[:5]]
        parallel_features = self._parallel_move_features(board, candidate_moves)
        for item in sf_choices[:5]:
            move = item["move"]
            bonus = 0.0
            if move == final_move:
                bonus += 10.0
            if move == th_move:
                bonus += 4.0 * theresia.get("confidence", 0.0)
            try:
                mv = chess.Move.from_uci(move)
                pv = [chess.Move.from_uci(x) for x in item["pv"]]
                bonus += self._style_bonus(board, mv, pv, parallel_features.get(move))
            except ValueError:
                continue
            choices.append((item["score"] + bonus, item["score"], move, item["pv"], bonus))
        if not choices and th_move:
            choices.append((theresia["score"], theresia["score"], th_move, [], 0.0))

        return {
            "fen": board.fen(), "choices": choices, "opening": opening,
            "decision": {"move": final_move, "confidence": round(max(0.0, min(1.0, confidence)), 3), "agreement": status, "directive": directive},
            "sources": {"theresia": theresia, "stockfish": stockfish}, "health": self.health(),
        }

    def _analyze(self, board):
        # Theresia gets first computational sight. Its output becomes a control
        # signal for how Chessreck interprets the external Stockfish resource.
        theresia = self._analyze_theresia(board)
        stockfish = self._analyze_stockfish(board)
        opening = self.opening_info(board)
        return self._fuse(board, theresia, stockfish, opening)

    # ---------- scheduling / resilience ----------
    def submit(self, board):
        key = self._position_key(board)
        snapshot = board.copy(stack=True)
        with self._state_lock:
            if self._closed:
                raise RuntimeError("Engine manager is closed")
            self._generation += 1
            generation = self._generation
            self._pending = (snapshot, key, generation)
            if self.future is None or self.future.done():
                self.future = self.executor.submit(self._worker)

    def _worker(self):
        while True:
            with self._state_lock:
                job = self._pending
                self._pending = None
                if job is None or self._closed:
                    self.future = None
                    return None
                board, key, generation = job
            cached = self._cache_get(key)
            result = cached if cached is not None else self._analyze(board)
            if cached is None:
                self._cache_put(key, result)
            with self._state_lock:
                newer = self._pending is not None
                current = self._generation
            if generation == current and not newer:
                return result

    def result(self, wait=True):
        with self._state_lock:
            future = self.future
        if future is None:
            return None
        if not wait and not future.done():
            return None
        try:
            return future.result(timeout=self.analysis_timeout + 2.0 if wait else 0)
        except TimeoutError:
            return None
        except Exception:
            with self._state_lock:
                if future is self.future:
                    self.future = None
            raise

    def health(self):
        return {
            "closed": self._closed,
            "started": self._started,
            "cpu_count": self.cpu_count,
            "multiprocessing": self.mp.snapshot(),
            "resources": {name: state.snapshot() for name, state in self.resources.items()},
        }

    def _parallel_move_features(self, board, moves):
        if not getattr(self.mp, "started", False):
            return {}
        try:
            return self.mp.move_features(board.fen(), moves)
        except Exception:
            return {}

    # ---------- style / presentation ----------
    def _style_bonus(self, board, move, pv, parallel_feature=None):
        before = material_score(board, board.turn)
        test = board.copy(stack=False)
        if parallel_feature:
            is_capture = bool(parallel_feature.get("capture"))
            is_check = bool(parallel_feature.get("check"))
            moving_piece = board.piece_at(move.from_square)
            material_delta = float(parallel_feature.get("material_delta", 0))
            pieces = int(parallel_feature.get("pieces_after", len(test.piece_map())))
        else:
            is_capture = board.is_capture(move)
            is_check = board.gives_check(move)
            moving_piece = board.piece_at(move.from_square)
            test.push(move)
            after = material_score(test, board.turn)
            material_delta = after - before
            pieces = len(test.piece_map())
        sacrifice = max(0, -material_delta) / 900.0
        tactical = (1.0 if is_check else 0.0) + (0.7 if is_capture else 0.0)
        risk = min(1.0, 0.35 * tactical + 0.65 * sacrifice)
        attack = min(1.0, tactical / 1.7)
        queen_activity = 1.0 if moving_piece and moving_piece.piece_type == chess.QUEEN else 0.0
        positional = 1.0 if board.is_castling(move) else 0.0
        if moving_piece and moving_piece.piece_type in (chess.KNIGHT, chess.BISHOP) and board.fullmove_number <= 12:
            positional += 0.6
        positional = min(1.0, positional)
        endgame = 1.0 if pieces <= 12 else 0.5 if pieces <= 18 else 0.0
        tactics = min(1.0, max(0, len(pv) - 1) / 8.0)
        features = {"risk": risk, "attack": attack, "tactics": tactics, "sacrifices": min(1.0, sacrifice), "queen_activity": queen_activity, "positional": positional, "endgame": endgame}
        bonus = 0.0
        for key, feature in features.items():
            contribution = feature if key != "risk" or self.style[key] >= 0.5 else -feature
            bonus += (self.style[key] - 0.5) * contribution * 14.0
        return bonus

    def format_result(self, board, result):
        if not result:
            return None
        lines = []
        opening = result.get("opening")
        if opening:
            lines.append(f"Opening: {opening['name']} ({opening['eco']})")
        decision = result.get("decision", {})
        if decision.get("move"):
            move = chess.Move.from_uci(decision["move"])
            lines.append(f"Decision: {board.san(move)}  confidence={decision.get('confidence', 0):.3f}  status={decision.get('agreement', 'unknown')}")
        lines.append("\nCHESSRECK RECOMMENDATIONS")
        for i, (_, raw, uci, pv_uci, bonus) in enumerate(result.get("choices", []), 1):
            move = chess.Move.from_uci(uci)
            temp = board.copy(stack=False)
            pv = []
            for item in pv_uci[:6]:
                mv = chess.Move.from_uci(item)
                try:
                    pv.append(temp.san(mv)); temp.push(mv)
                except ValueError:
                    break
            eval_text = f"mate {raw:+d}" if abs(raw) >= 100000 else f"{raw / 100:+.2f}"
            lines.append(f"{i}. {board.san(move):<7} eval={eval_text:<10} style={bonus:+.1f}  PV: {' '.join(pv)}")
        th = result.get("sources", {}).get("theresia", {})
        sf = result.get("sources", {}).get("stockfish", {})
        lines.append(f"Theresia: {'available' if th.get('available') else 'unavailable'}")
        if th.get("available"):
            lines.append(f"  move={th.get('bestmove')} score={th.get('score')} confidence={th.get('confidence', 0):.3f} nodes={th.get('nodes', 0)}")
        lines.append(f"Stockfish: {'available' if sf.get('available') else 'unavailable'}")
        health = result.get("health", {}).get("resources", {})
        if health:
            lines.append("Resource health: " + ", ".join(f"{k}={'up' if v.get('available') else 'down'}" for k, v in health.items()))
        return "\n".join(lines)


def material_value(piece_type):
    return {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}[piece_type]


def material_score(board, color):
    total = 0
    for piece in board.piece_map().values():
        value = material_value(piece.piece_type)
        total += value if piece.color == color else -value
    return total
