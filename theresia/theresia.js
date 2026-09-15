#!/usr/bin/env node
'use strict';

// Theresia: Chessreck's lightweight native chess calculation core.
// It intentionally has no general-purpose utilities or external engine calls.

const FILES = 'abcdefgh';
const PIECE_VALUE = { p: 100, n: 320, b: 330, r: 500, q: 900, k: 0 };
const KNIGHT = [[1,2],[2,1],[-1,2],[-2,1],[1,-2],[2,-1],[-1,-2],[-2,-1]];
const KING = [[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]];
const BISHOP = [[1,1],[1,-1],[-1,1],[-1,-1]];
const ROOK = [[1,0],[-1,0],[0,1],[0,-1]];

function sq(file, rank) { return rank * 8 + file; }
function fileOf(s) { return s & 7; }
function rankOf(s) { return s >> 3; }
function inBoard(f,r) { return f >= 0 && f < 8 && r >= 0 && r < 8; }
function squareName(s) { return FILES[fileOf(s)] + String(rankOf(s)+1); }
function parseSquare(s) { return sq(FILES.indexOf(s[0]), Number(s[1])-1); }
function colorOf(p) { return p === p.toUpperCase() ? 1 : -1; }
function typeOf(p) { return p ? p.toLowerCase() : null; }
function opposite(c) { return -c; }

function parseFEN(fen) {
  const fields = fen.trim().split(/\s+/);
  if (fields.length < 4) throw new Error('invalid FEN');
  const board = Array(64).fill(null);
  const rows = fields[0].split('/');
  if (rows.length !== 8) throw new Error('invalid FEN board');
  for (let row=0; row<8; row++) {
    let f=0;
    for (const ch of rows[row]) {
      if (/^[1-8]$/.test(ch)) f += Number(ch);
      else { if (f >= 8) throw new Error('invalid FEN row'); board[sq(f,7-row)] = ch; f++; }
    }
    if (f !== 8) throw new Error('invalid FEN row');
  }
  return {
    board,
    turn: fields[1] === 'b' ? -1 : 1,
    castling: fields[2] === '-' ? '' : fields[2],
    ep: fields[3] === '-' ? -1 : parseSquare(fields[3]),
    halfmove: Number(fields[4] || 0),
    fullmove: Number(fields[5] || 1),
  };
}

function cloneState(s) { return { board: s.board.slice(), turn: s.turn, castling: s.castling, ep: s.ep, halfmove: s.halfmove, fullmove: s.fullmove }; }

function makeMove(s, m) {
  const n = cloneState(s);
  const p = n.board[m.from];
  n.board[m.from] = null;
  if (m.ep) n.board[m.captureSquare] = null;
  if (m.castle) {
    if (m.to === 6) { n.board[5]=n.board[7]; n.board[7]=null; }
    else if (m.to === 2) { n.board[3]=n.board[0]; n.board[0]=null; }
    else if (m.to === 62) { n.board[61]=n.board[63]; n.board[63]=null; }
    else if (m.to === 58) { n.board[59]=n.board[56]; n.board[56]=null; }
  }
  n.board[m.to] = m.promotion ? (n.turn === 1 ? m.promotion.toUpperCase() : m.promotion) : p;
  if (typeOf(p) === 'k') {
    if (n.turn === 1) n.castling = n.castling.replace(/[KQ]/g,'');
    else n.castling = n.castling.replace(/[kq]/g,'');
  }
  if (m.from===0 || m.to===0) n.castling=n.castling.replace('Q','');
  if (m.from===7 || m.to===7) n.castling=n.castling.replace('K','');
  if (m.from===56 || m.to===56) n.castling=n.castling.replace('q','');
  if (m.from===63 || m.to===63) n.castling=n.castling.replace('k','');
  n.ep = -1;
  if (typeOf(p)==='p' && Math.abs(m.to-m.from)===16) n.ep=(m.from+m.to)>>1;
  n.halfmove = (typeOf(p)==='p' || m.capture) ? 0 : n.halfmove+1;
  if (n.turn === -1) n.fullmove++;
  n.turn = opposite(n.turn);
  return n;
}

function attacked(s, target, byColor) {
  const tf=fileOf(target), tr=rankOf(target);
  const pawnRank = tr - byColor;
  for (const df of [-1,1]) {
    const f=tf-df, r=pawnRank;
    if (inBoard(f,r)) { const p=s.board[sq(f,r)]; if (p && colorOf(p)===byColor && typeOf(p)==='p') return true; }
  }
  for (const [df,dr] of KNIGHT) {
    const f=tf-df,r=tr-dr;
    if (inBoard(f,r)) { const p=s.board[sq(f,r)]; if (p && colorOf(p)===byColor && typeOf(p)==='n') return true; }
  }
  for (const [df,dr] of KING) {
    const f=tf-df,r=tr-dr;
    if (inBoard(f,r)) { const p=s.board[sq(f,r)]; if (p && colorOf(p)===byColor && typeOf(p)==='k') return true; }
  }
  for (const [df,dr] of BISHOP) {
    let f=tf+df,r=tr+dr;
    while(inBoard(f,r)) { const p=s.board[sq(f,r)]; if(p){ if(colorOf(p)===byColor && (typeOf(p)==='b'||typeOf(p)==='q')) return true; break;} f+=df;r+=dr; }
  }
  for (const [df,dr] of ROOK) {
    let f=tf+df,r=tr+dr;
    while(inBoard(f,r)) { const p=s.board[sq(f,r)]; if(p){ if(colorOf(p)===byColor && (typeOf(p)==='r'||typeOf(p)==='q')) return true; break;} f+=df;r+=dr; }
  }
  return false;
}

function kingSquare(s,c) { for(let i=0;i<64;i++) if(s.board[i]=== (c===1?'K':'k')) return i; return -1; }
function inCheck(s,c) { const k=kingSquare(s,c); return k<0 || attacked(s,k,opposite(c)); }

function pushMove(s,m,out) {
  if (m.capture && typeOf(s.board[m.to]||'')==='k') return;
  out.push(m);
}

function pseudoMoves(s) {
  const out=[];
  const c=s.turn;
  for(let from=0;from<64;from++) {
    const p=s.board[from]; if(!p || colorOf(p)!==c) continue;
    const t=typeOf(p), f=fileOf(from), r=rankOf(from);
    if(t==='p') {
      const dir=c===1?1:-1, start=c===1?1:6, promoRank=c===1?7:0;
      const oneR=r+dir;
      if(inBoard(f,oneR) && !s.board[sq(f,oneR)]) {
        const to=sq(f,oneR);
        if(oneR===promoRank) for(const pr of ['q','r','b','n']) pushMove(s,{from,to,promotion:pr,capture:false},out);
        else pushMove(s,{from,to,capture:false},out);
        if(r===start && !s.board[sq(f,r+2*dir)]) pushMove(s,{from,to:sq(f,r+2*dir),capture:false},out);
      }
      for(const df of [-1,1]) {
        const nf=f+df,nr=r+dir; if(!inBoard(nf,nr)) continue;
        const to=sq(nf,nr), target=s.board[to];
        if((target && colorOf(target)!==c) || to===s.ep) {
          const ep=to===s.ep && !target;
          if(nr===promoRank) for(const pr of ['q','r','b','n']) pushMove(s,{from,to,promotion:pr,capture:true,ep,captureSquare:ep?sq(nf,r):to},out);
          else pushMove(s,{from,to,capture:true,ep,captureSquare:ep?sq(nf,r):to},out);
        }
      }
    } else if(t==='n') {
      for(const [df,dr] of KNIGHT){const nf=f+df,nr=r+dr;if(!inBoard(nf,nr))continue;const to=sq(nf,nr),q=s.board[to];if(!q||colorOf(q)!==c)pushMove(s,{from,to,capture:!!q},out);}
    } else if(t==='b'||t==='r'||t==='q') {
      const dirs=t==='b'?BISHOP:t==='r'?ROOK:BISHOP.concat(ROOK);
      for(const [df,dr] of dirs){let nf=f+df,nr=r+dr;while(inBoard(nf,nr)){const to=sq(nf,nr),q=s.board[to];if(!q)pushMove(s,{from,to,capture:false},out);else{if(colorOf(q)!==c)pushMove(s,{from,to,capture:true},out);break;}nf+=df;nr+=dr;}}
    } else if(t==='k') {
      for(const [df,dr] of KING){const nf=f+df,nr=r+dr;if(!inBoard(nf,nr))continue;const to=sq(nf,nr),q=s.board[to];if(!q||colorOf(q)!==c)pushMove(s,{from,to,capture:!!q},out);}
      const home=c===1?4:60;
      if(from===home && !inCheck(s,c)) {
        const ks=c===1?'K':'k', qs=c===1?'Q':'q';
        const rookK=c===1?7:63, rookQ=c===1?0:56;
        if(s.castling.includes(ks) && !s.board[home+1]&&!s.board[home+2]&&!attacked(s,home+1,-c)&&!attacked(s,home+2,-c)&&s.board[rookK]=== (c===1?'R':'r')) pushMove(s,{from,to:home+2,capture:false,castle:true},out);
        if(s.castling.includes(qs) && !s.board[home-1]&&!s.board[home-2]&&!s.board[home-3]&&!attacked(s,home-1,-c)&&!attacked(s,home-2,-c)&&s.board[rookQ]=== (c===1?'R':'r')) pushMove(s,{from,to:home-2,capture:false,castle:true},out);
      }
    }
  }
  return out;
}

function legalMoves(s) { const out=[]; for(const m of pseudoMoves(s)){const n=makeMove(s,m);if(!inCheck(n,s.turn))out.push(m);} return out; }

function moveUci(m){return squareName(m.from)+squareName(m.to)+(m.promotion||'');}
function material(s){let score=0;for(const p of s.board)if(p)score+=colorOf(p)*PIECE_VALUE[typeOf(p)];return score;}
function mobility(s,c){const old=s.turn;s.turn=c;const n=legalMoves(s).length;s.turn=old;return n;}
function centerBonus(s){let v=0;for(const x of [27,28,35,36]){const p=s.board[x];if(p)v+=colorOf(p)*12;}return v;}
function evaluate(s) {
  const mat=material(s);
  const mob=(mobility(s,1)-mobility(s,-1))*3;
  const center=centerBonus(s);
  const check=(inCheck(s,1)?-25:0)+(inCheck(s,-1)?25:0);
  return mat+mob+center+check;
}
function orderedMoves(s,moves){return moves.slice().sort((a,b)=>((b.capture?PIECE_VALUE[typeOf(s.board[b.to])||'p']:0)+(b.promotion?800:0))-((a.capture?PIECE_VALUE[typeOf(s.board[a.to])||'p']:0)+(a.promotion?800:0)));}
function negamax(s,depth,alpha,beta){
  const moves=legalMoves(s);
  if(depth===0) return evaluate(s)*s.turn;
  if(!moves.length) return inCheck(s,s.turn)?-100000+depth:0;
  let best=-Infinity;
  for(const m of orderedMoves(s,moves)){const score=-negamax(makeMove(s,m),depth-1,-beta,-alpha);if(score>best)best=score;if(score>alpha)alpha=score;if(alpha>=beta)break;}
  return best;
}
function analyze(fen,depth=3){
  const s=parseFEN(fen);const moves=orderedMoves(s,legalMoves(s));if(!moves.length)return {bestmove:null,score:inCheck(s,s.turn)?-100000:0,confidence:1,nodes:1};
  let best=null,bestScore=-Infinity,second=-Infinity,nodes=0;
  for(const m of moves){const n=makeMove(s,m);const score=-negamaxCount(n,Math.max(0,depth-1),-Infinity,Infinity,()=>nodes++);if(score>bestScore){second=bestScore;bestScore=score;best=m;}else if(score>second)second=score;}
  const gap=Math.max(0,bestScore-second);const confidence=Math.max(0,Math.min(1,0.5+gap/300));
  return {bestmove:moveUci(best),score:bestScore,confidence:Number(confidence.toFixed(3)),depth,nodes};
}
function negamaxCount(s,depth,alpha,beta,count){count();const moves=legalMoves(s);if(depth===0)return evaluate(s)*s.turn;if(!moves.length)return inCheck(s,s.turn)?-100000+depth:0;let best=-Infinity;for(const m of orderedMoves(s,moves)){const score=-negamaxCount(makeMove(s,m),depth-1,-beta,-alpha,count);if(score>best)best=score;if(score>alpha)alpha=score;if(alpha>=beta)break;}return best;}


// Theresia v0.3.0 search layer: specialized Chessreck calculation.
// It deliberately stays independent from Stockfish while providing a useful
// tactical cross-check and a compact internal perspective.
const TT = new Map();
const KILLERS = new Map();
const HISTORY = new Map();
let SEARCH_DEADLINE = 0;
let SEARCH_NODES = 0;

function stateKey(s){
  return s.board.map(p=>p||'.').join('')+'|'+s.turn+'|'+s.castling+'|'+s.ep;
}
function isTactical(s,m){
  return !!m.capture || !!m.promotion || inCheck(makeMove(s,m), opposite(s.turn));
}
function pst(t,sqv){
  const f=fileOf(sqv), r=rankOf(sqv), center=3.5-Math.max(Math.abs(3.5-f),Math.abs(3.5-r));
  const c=Math.max(0,center);
  if(t==='p') return r*4+c*3;
  if(t==='n') return c*10;
  if(t==='b') return c*7;
  if(t==='r') return (r===0||r===7?0:2)+c*2;
  if(t==='q') return c*2;
  return c*4;
}
function evaluate(s){
  let score=0, whiteB=0, blackB=0, whiteP=0, blackP=0;
  for(let i=0;i<64;i++){
    const p=s.board[i]; if(!p) continue;
    const t=typeOf(p), c=colorOf(p), v=PIECE_VALUE[t]+pst(t,i);
    score += c*v;
    if(t==='b'){if(c===1)whiteB++;else blackB++;}
    if(t==='p'){if(c===1)whiteP++;else blackP++;}
  }
  if(whiteB>=2) score+=25; if(blackB>=2) score-=25;
  score += (mobility(s,1)-mobility(s,-1))*2;
  score += (whiteP-blackP)*0;
  if(inCheck(s,1)) score-=35; if(inCheck(s,-1)) score+=35;
  return score;
}
function moveKey(m){return moveUci(m);}
function orderEnhanced(s,moves,ttMove){
  return moves.slice().sort((a,b)=>{
    const score=m=>{
      let x=0, target=m.capture?(s.board[m.to]||'p'):null;
      if(target) x+=PIECE_VALUE[typeOf(target)]*10;
      if(m.promotion) x+=900;
      if(moveKey(m)===ttMove) x+=100000;
      const k=moveKey(m);
      x+=KILLERS.get(k)||0;
      x+=HISTORY.get(k)||0;
      if(isTactical(s,m)) x+=80;
      return x;
    };
    return score(b)-score(a);
  });
}
function qsearch(s,alpha,beta,ply){
  if(Date.now()>=SEARCH_DEADLINE) throw new Error('search-timeout');
  SEARCH_NODES++;
  const stand=evaluate(s)*s.turn;
  if(stand>=beta)return beta;
  if(stand>alpha)alpha=stand;
  let moves=legalMoves(s).filter(m=>m.capture||m.promotion);
  if(inCheck(s,s.turn)) moves=legalMoves(s);
  moves=orderEnhanced(s,moves,null);
  for(const m of moves){
    const score=-qsearch(makeMove(s,m),-beta,-alpha,ply+1);
    if(score>=beta)return beta;
    if(score>alpha)alpha=score;
  }
  return alpha;
}
function negamaxEnhanced(s,depth,alpha,beta,ply){
  if(Date.now()>=SEARCH_DEADLINE) throw new Error('search-timeout');
  SEARCH_NODES++;
  const key=stateKey(s), cached=TT.get(key);
  if(cached && cached.depth>=depth){
    if(cached.flag==='EXACT')return cached.score;
    if(cached.flag==='LOWER' && cached.score>=beta) return cached.score;
    if(cached.flag==='UPPER' && cached.score<=alpha) return cached.score;
  }
  const moves=legalMoves(s);
  if(!moves.length)return inCheck(s,s.turn)?-100000+ply:0;
  if(depth<=0)return qsearch(s,alpha,beta,ply);
  const originalAlpha=alpha;
  const ttMove=cached&&cached.move;
  let best=-Infinity,bestMove=null;
  let ordered=orderEnhanced(s,moves,ttMove);
  for(let i=0;i<ordered.length;i++){
    const m=ordered[i], child=makeMove(s,m);
    let score;
    // Lightweight late-move reduction. Tactical moves are searched at full depth.
    if(i>=3 && depth>=3 && !isTactical(s,m)){
      score=-negamaxEnhanced(child,depth-2,-alpha-1,-alpha,ply+1);
      if(score>alpha)score=-negamaxEnhanced(child,depth-1,-beta,-alpha,ply+1);
    }else{
      score=-negamaxEnhanced(child,depth-1,-beta,-alpha,ply+1);
    }
    if(score>best){best=score;bestMove=m;}
    if(score>alpha)alpha=score;
    if(alpha>=beta){
      const k=moveKey(m); KILLERS.set(k,Math.min(5000,(KILLERS.get(k)||0)+120));
      HISTORY.set(k,Math.min(5000,(HISTORY.get(k)||0)+depth*depth));
      break;
    }
  }
  let flag='EXACT'; if(best<=originalAlpha)flag='UPPER'; else if(best>=beta)flag='LOWER';
  TT.set(key,{depth,score:best,flag,move:bestMove?moveKey(bestMove):null});
  if(TT.size>50000){const first=TT.keys().next().value;TT.delete(first);}
  return best;
}
function analyze(fen,requestedDepth=3,timeMs=1500){
  const s=parseFEN(fen), root=legalMoves(s);
  if(!root.length)return {bestmove:null,score:inCheck(s,s.turn)?-100000:0,confidence:1,depth:0,nodes:1,adaptation:'terminal'};
  const start=Date.now(); SEARCH_DEADLINE=start+Math.max(50,Number(timeMs)||1500); SEARCH_NODES=0;
  TT.clear(); KILLERS.clear(); HISTORY.clear();
  let best=root[0],bestScore=-Infinity,second=-Infinity,completed=0;
  for(let d=1;d<=Math.max(1,Math.min(8,Number(requestedDepth)||3));d++){
    try{
      let localBest=null,localScore=-Infinity,localSecond=-Infinity;
      for(const m of orderEnhanced(s,root,null)){
        const score=-negamaxEnhanced(makeMove(s,m),d-1,-Infinity,Infinity,1);
        if(score>localScore){localSecond=localScore;localScore=score;localBest=m;}else if(score>localSecond)localSecond=score;
      }
      if(localBest){best=localBest;bestScore=localScore;second=localSecond;completed=d;}
    }catch(e){if(e.message!=='search-timeout')throw e;break;}
  }
  const gap=Math.max(0,bestScore-second);
  const tactical=gap>120 || isTactical(s,best);
  const confidence=Math.max(0,Math.min(1,0.48+gap/350+completed*0.025));
  return {bestmove:moveUci(best),score:bestScore,confidence:Number(confidence.toFixed(3)),depth:completed,nodes:SEARCH_NODES,adaptation:tactical?'tactical-extension':completed>=requestedDepth?'stable-line':'normal',elapsed_ms:Date.now()-start};
}

function handle(obj){
  if(obj.cmd==='ping')return {ok:true,name:'Theresia',version:'0.3.0',role:'chessreck-specialized-controller'};
  if(obj.cmd==='analyze')return analyze(obj.fen,obj.depth||3,obj.time_ms||1500);
  if(obj.cmd==='legal_moves'){const s=parseFEN(obj.fen);return {moves:legalMoves(s).map(moveUci),count:legalMoves(s).length};}
  if(obj.cmd==='evaluate'){const s=parseFEN(obj.fen);return {score:evaluate(s)};}
  throw new Error('unknown command');
}

const readline=require('readline');
const rl=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
rl.on('line',line=>{if(!line.trim())return;try{process.stdout.write(JSON.stringify(handle(JSON.parse(line)))+'\n');}catch(e){process.stdout.write(JSON.stringify({error:String(e.message||e)})+'\n');}});
