# Engine Comparison Notes

This file records the intended relationship between Theresia and Stockfish.

- Theresia is Chessreck's internal decision/calculation layer.
- Stockfish is an external high-strength calculation resource.
- engine.py controls both resources and fuses their outputs.
- Chessreck does not attempt to duplicate Stockfish's NNUE/search stack inside Theresia.
- Device resilience belongs to Chessreck as a system property, not to Theresia as an engine identity.

A binary head-to-head benchmark is environment-dependent because Stockfish is an external executable.
