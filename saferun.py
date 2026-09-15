#!/usr/bin/env python3
"""Chessreck portable recovery and integrity checker.

Copyright (c) 2026 wyuri

This file is intentionally standalone. It does not import main.py, engine.py,
python-chess, Rich, Openix, or Theresia during basic recovery checks.

A copy of the known-good main.py from the distribution is embedded below so
this file can repair a missing/corrupt main.py even when copied out of the
original Chessreck directory.

Do not add multiprocessing workers at module import time. On spawn-based
platforms, child processes import the launching module; all process creation
must remain behind the __main__ guard.
"""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import multiprocessing
import os
from pathlib import Path
import tempfile
import zlib

VERSION = "0.3.3"
EXPECTED_MAIN_SHA256 = "6089dc04090cb53778de631d99fc3d7b25eab71160ffba6d6ee2c748e516498b"
_EMBEDDED_MAIN = """c-oy=TXWmG5q{^dz+oRuPGtHvr*o>Q+Ho8uahpi4C7&~?<8ojMvQU!*Lx7f5SO2}c07&ts6E}X4$i?nrvH12T|KX>jLgq*JJUwFR6UjDeCDJp;b=`{<lQL(~BY8Rw&Vn=NLS&nqKdcn-BA=WdpZ<}oH$~1Jr(!*jL;wp<X-uRj@`#a0EEwUEWVv|a3$`Hl8zUAtGbN(OC6_B)r$n-h=2S5vGL{~e;;5Ri6m&8Y^N6JqbQI}=<wUI*`7pU5AFe);r?cP~G%`l!A1|-pg;(d-^Dp6KI={Ra&w^w@mLexqshr;zii?!cbW!RfJcZSSB0a#PJ3PrmuE@WoNXus-%cq<<%UmQRqiPlNdt%8~@amL2+U&+lV9wweS$iPMFxGFMX-Xeh?l{-e>70zTLN5%LJZ53&2RV}>eqx><fSXvVoZ0-#r*Zi1@)~%x$Psa++Qdw{&eiqw{bgqr?f|vH`n&V_d24Y&6?Jz?gXD3+bB{f9sY3BMn&$=c>w5bcO2z%F&Uo_Sax#Y7nSY$Y-nR~cKlcdtHXo5l0>$#Acs|mmR_K%^SlodX+PhLG+&Rv>@%!_ePxDY84K{r-Tq#YMJ0$KsjcFROMJb(g`3Q8t{LhvGu%VHm{d{a`Kv6uBO`@bx&X)ixLq9DQd@C4BLzH;pYSUcHgyaZ38aH*Zbn##;G{mjrI19G4$O#dAo<G#Q2yJ`^9Fw|(%_{!!rC}J2>fV7^1y~2T66lMP9zOd!IsD6+D)LmzJGJ+TKrm~QBwex)-Ra@SfGlYo--E|S?pvW;s}92IGks(b=Y@pWl|`1t96}jIv<9LCE)j~kAQlm%5JUj32N;v6B#IeLL1+Y41hTmIa`*OM=ZF8KhyOV~{8JDf-o0@L#0}v?%Snj$%=7)0uzj-2ZV<YD{b+XicKFNj9r~y|k3DWI=pw|_puII9K%+&h>^W7w+4;{ZMCJg+jDsPRL4#t?%3~?yN1i^6+(Io6e{rp;>^Wi?<k{(LoaZ7R7!7}$O(*XdCR9!JJNsBmf(SCT=i{w&$y2Ei-=19rdwHaM!ea2XrIq)H$)g07Mk@nnRjC4Ugdv8SF+iK#8gGaJ3<5j<82W&`bc1bc4ytc|R96r@Fy$HkL5<(A8xWIS<~t%w_oa=$gHr0i-`1?m>AGQ^xxGeqC}AMMDR}hyn)PapBPcSkn0cVMPQEqP-+=-E7_K(XgkScWF>oK*2IID|RU>eb0pr%Vuo0S(NEJ^DRuLQEt62m((42%md&j}?fFwNiPViv~?oeKh%eSW0Q8?dZ%;NA@8W$b(bvJ69MicAtWq2*<uqNqyvkL7M*9%zBB{weCqPR-!_4KY0v7=&2)ycU=OT<%$7SRk$?UGl}<aBwZiaV?(=eKlkjlJzSY37kOG%WqKpg`^AJ>c^0Iw9hltR1+t<$0>SDky<g8ELW75dMGQ(%z`9whk5Ku|PprhCIy*<=qRKF9rlNXqk245!B#Une_K&V=awMl!Q!1Q%|d@r`?^^Sd4%rWcV`NA7*G9))n38eTJ6+yS%W7cujln4y`Dn9J2Cm)pM~T&dw(UIw_iDF&mP}^32DobaQc8qduGf+4YI;E-RDkkkK}#LLsD#3u5*_V*}CenZaYttd+Qa+oMRex3q#bLgbrJuEg52FJ)xs2q*Vz`g!{6n0&mP&8OF2tTM0<O|t?!YpjgNl1y#<&dyb+a6DB`(+B23R)emg+Iv7w{kA?xC!8D|kyG-9oNNQ~VwrFG-M03Et9QDJ;uHCEL$4{I2SE@VY{9Ow69SCdF59!;ug+_h|Mmdi4(=K$PJshJT6Yg?u2!KemP`H&y^BgR>lWk*);U+q^cK2jSQJSnOVtDL(gH?@(dhvCNC^opq%z`s^q#_Dd?dEok)7h4Wif>|LU)K&?gnp$D;8&7`;IR}lE8>1hX!lpzvbP+(~_m|shbF-gE)MBE4Zrsm{2HCO~*C*-a2NG(gDnFv|K|7BimBI&=`>2RJ#UDV<Z!<BqlnR<J1Z>SiF%ikK(w66KH@&HIMdjJeysQFaB-^<FYp~>-(nUCfCkBbFN`ykR^vO4DXv{n~Hv02?FCF*@)t=U(=I-{I&uBd`(XS@;1h)#c;1zaQy^_u$`--m4H!2XL(Gj?q7)OH<G7yvgLyS^V}0`%1+%@Hcw3QGwPr!ow$wVd+2u`+c$Kv5&{C~1XI~*<z$g%Fju5%XVtW%=vJ}pVuu7q3x8O%81?9RL+g>c`O@vIem5X2GxS@0^GZMJ(7@orPNX!zES8vsN!664#LVbGXw2+oFKJul0g;1Ju{~I$WLPa=I?a{Ws6E#Ov~<a?`T)6`z1~w$yug7;Yp6gwBrm|ft)<Cwrzi$zd!6*@)U|$1zlZ`<9B2p~=$gT7n$uW1*fy}YtnLPd3`axA=xGbh@LE7ZmWi&xV6#b&(+q?$luh;GGQ@5!gxZsPEkMFNA@GviFVh<rZ89RdSOGvw3*G6})pRnR%-vS`TUYo)x4dX|TcYb$Z<N&15eRo%olc`}h&n~$Fbg9>EY^6Aw#tfWge@hc$gc8cc=gEX!}kc98_}!&>r8Gbw&BsEy0;DZp*^5j{J!Y{aCrWYDc31tulia6mES3yKj=Te`o7)EK-jDI`<=Y)O1q77HL&h&OFOBjmAx<1CmQpG);)xp0KBg?6`E5p%3K|`->9Mk`&zvIgz?&Ei0PK>_;yF$jL1oct5OBo!p?MN!>+=H(rW(up56xzyN7x%e4S!5LB7gd7%QO{d!@Z*2Hm4K<4jk2JNn>T2y=f@O)BzR0bPXOXONLa$m%C6tzgJQ44Z=bkDKv$@*NZF1F<#J=}8#@%`%oQJb*^i9BX?aS3Qs^iwjgR0)6U+EwIASbgQ$!EeB;i(7AtCy;=gk^E+TP#RHx3x<b^b_Qid|_vYK`N2ikA5WF?z%Km!Zb2)~o-}B~w8cP4-St>QO(CRMJfqwIQmB1dAp8jnby|D|EQpI2MBwu!Cy9PSU4>LXR?H#F{zJS?#36*u%<JrxpIp!-PWZh8z$*c1lNhLf3pyNM|;1qz+MNsRq_E)<l{wpl*Y5mHE%yHldp&kIkP(w5fary~ETNunJ<oplY_w29"""


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _decode_embedded_main() -> bytes:
    try:
        packed = base64.b85decode(_EMBEDDED_MAIN.encode("ascii"))
        data = zlib.decompress(packed)
    except Exception as exc:
        raise RuntimeError("embedded main.py recovery payload is unreadable") from exc
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED_MAIN_SHA256:
        raise RuntimeError("embedded main.py recovery payload failed integrity check")
    return data


def _syntax_ok(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "missing"
    try:
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        return True, "ok"
    except (OSError, SyntaxError, UnicodeError) as exc:
        return False, str(exc)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def check() -> int:
    root = _project_root()
    main = root / "main.py"
    engine = root / "engine.py"
    theresia = root / "theresia" / "theresia.js"

    print(f"CHESSRECK SAFERUN v{VERSION}")
    print(f"Root: {root}")
    print()

    checks = [
        ("Python", True, f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}"),
        ("multiprocessing", True, f"cpu_count={max(1, multiprocessing.cpu_count())}; no child process started"),
        ("main.py", *_syntax_ok(main)),
        ("engine.py", *_syntax_ok(engine)),
        ("Theresia JS", *_node_check(theresia)),
    ]

    failed = False
    for name, ok, detail in checks:
        print(f"[{'OK' if ok else 'FAIL'}] {name}: {detail}")
        failed |= not ok

    try:
        _decode_embedded_main()
        print("[OK] recovery payload: integrity verified")
    except RuntimeError as exc:
        print(f"[FAIL] recovery payload: {exc}")
        failed = True

    if failed:
        print()
        print("Recovery resources are incomplete or damaged.")
        print("Use --repair-main only when you want saferun to restore main.py.")
        return 1

    print()
    print("Basic recovery checks passed.")
    return 0


def _node_check(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "missing"
    # Do not launch Node here. Basic recovery must remain dependency-light.
    return True, "present"


def repair_main(force: bool = False) -> int:
    root = _project_root()
    target = root / "main.py"
    data = _decode_embedded_main()

    ok, detail = _syntax_ok(target)
    if ok and not force:
        print("main.py is syntactically valid; no repair performed.")
        print("Use --repair-main --force to replace it anyway.")
        return 0

    if ok and force:
        print("main.py is valid; --force requested replacement from embedded copy.")
    elif target.exists():
        print(f"main.py is damaged: {detail}")
    else:
        print("main.py is missing.")

    _atomic_write(target, data)
    ok_after, detail_after = _syntax_ok(target)
    if not ok_after:
        print(f"REPAIR FAILED: restored main.py is not valid: {detail_after}")
        return 2

    print("main.py restored successfully.")
    print(f"SHA-256: {hashlib.sha256(target.read_bytes()).hexdigest()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Standalone Chessreck diagnostics and main.py recovery tool."
    )
    parser.add_argument("--check", action="store_true", help="run dependency-light checks")
    parser.add_argument("--repair-main", action="store_true", help="restore main.py from the embedded known-good copy")
    parser.add_argument("--force", action="store_true", help="allow --repair-main to replace a valid main.py")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.repair_main:
        return repair_main(force=args.force)
    return check()


if __name__ == "__main__":
    # Critical for multiprocessing/spawn safety: importing this module never
    # executes the CLI or starts another process.
    raise SystemExit(main())
