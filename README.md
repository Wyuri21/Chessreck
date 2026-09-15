
# Chessreck

Just a random useless chess tool. For a warningk Chessreck is not intended to be used as a cheating tool or to violate the rules of any chess platform. Use it responsibly and follow the rules of the platform you're playing on. If you get banned, that's on you. I'm not responsible for any bans, penalties, or other consequences resulting from how you use Chessreck

## Install

```bash
pkg update
pkg install python stockfish
pkg install nodejs
pip install -r requirements.txt
```

`Openix` is used for bundled ECO opening lookup. It does not replace Stockfish.

## Run

```bash
python main.py
```

## Style manager

```bash
python styles.py
```
**Why does Chessreck have styles?**
Chessreck has styles because not everyone wants the same kind of chess advice. Styles let you adjust how Chessreck evaluates and presents candidate moves, so you can make it more aggressive, balanced, defensive, experimental, or just weird. Styles do not magically make the engine stronger or weaker. They change its preferences and behavior around the analysis, not the actual playing strength of Stockfish. You can also create your own styles. If you make something ridiculous, that's completely fine. Just remember: the consequences are yours.

## Recovery tool

`saferun.py` is a standalone recovery/check tool shipped inside the archive. It does not import `main.py` during startup and can restore the distribution's known-good `main.py` from its embedded recovery copy.

```bash
python saferun.py --check
python saferun.py --repair-main
```

Keep a copy of `saferun.py` somewhere outside the Chessreck directory if you want a portable recovery path. It uses Python's standard-library `multiprocessing` module only for capability reporting; no child processes are spawned during import or normal checks.

## Recovery tool

`saferun.py` is a standalone recovery/check tool shipped inside the archive. It does not import `main.py` during startup and can restore the distribution's known-good `main.py` from its embedded recovery copy.

```bash
python saferun.py --check
python saferun.py --repair-main
```

Keep a copy of `saferun.py` somewhere outside the Chessreck directory if you want a portable recovery path. It uses Python's standard-library `multiprocessing` module only for capability reporting; no child processes are spawned during import or normal checks.

## License / attribution

Original Chessreck code and modifications: Copyright (c) 2026 wyuri.

Stockfish is a separate third-party component licensed under GNU GPL v3.0.
Openix is a separate third-party Python package licensed under MIT.
See `THIRD_PARTY_NOTICES.md`.
separate third-party Python package licensed under MIT.
See `THIRD_PARTY_NOTICES.md`.
