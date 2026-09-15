"""Optional real-engine benchmark. Run on a device with Stockfish installed."""
import shutil, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
path=shutil.which("stockfish") or next((p for p in ["/usr/bin/stockfish","/data/data/com.termux/files/usr/bin/stockfish"] if Path(p).exists()),None)
if not path:
    print("SKIP: Stockfish executable not installed in this environment.")
    sys.exit(0)
fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
# UCI probe, deliberately independent of python-chess.
p=subprocess.Popen([path],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
def send(x): p.stdin.write(x+'\n'); p.stdin.flush()
send('uci')
lines=[]
while True:
    line=p.stdout.readline().strip(); lines.append(line)
    if line=='uciok': break
send('isready')
while p.stdout.readline().strip()!='readyok': pass
send('position fen '+fen); send('go depth 3')
best=None; info=[]
while True:
    line=p.stdout.readline().strip()
    if line.startswith('info '): info.append(line)
    if line.startswith('bestmove '): best=line.split()[1]; break
send('quit'); p.wait(timeout=2)
print('Stockfish bestmove:',best)
print('Stockfish info lines:',len(info))
