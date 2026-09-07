import { useState } from "react";
import type { Key } from "chessground/types";
import type { PuzzleOut, TacticOut, Trainable } from "../api/types";
import { Board } from "../board/Board";
import { colorName, kindLabel, themeLabel } from "../lib/format";
import { MistakeCard } from "./MistakeCard";
import type { PuzzleCtl } from "./usePuzzle";

// `unknown` no resultado do submit: a view não lê `state.review`, então serve
// tanto para os próprios (ReviewOut) quanto para as táticas (AttemptOut).
type Ctl = PuzzleCtl<unknown>;

/** Segunda linha do cabeçalho de uma tática do banco do Lichess (sessão de táticas). */
function TacticInfo({ tactic, orderInfo }: { tactic: TacticOut; orderInfo?: string }) {
  return (
    <div className="muted">
      <span className="tag">{themeLabel(tactic.theme)}</span><span className="tag">rating {tactic.rating}</span>
      {tactic.solver_moves} lance(s) seu(s)
      {orderInfo ? ` · ${orderInfo}` : ""}
    </div>
  );
}

/** Segunda linha do cabeçalho de um exercício da repetição, conforme a fonte. */
function PuzzleInfo({ puzzle, orderInfo }: { puzzle: PuzzleOut; orderInfo?: string }) {
  const srs = puzzle.srs.due_at ? ` · revisão (intervalo ${puzzle.srs.interval_days} d)` : " · novo";
  const order = orderInfo ? ` · ${orderInfo}` : "";
  if (puzzle.study) {
    return (
      <div className="muted">
        <span className="tag">estudo</span>
        {puzzle.study.title} · {puzzle.study.chapter_name} · {puzzle.solver_moves} lance(s) seu(s)
        {srs}{order}
      </div>
    );
  }
  if (puzzle.source === "lichess") {
    return (
      <div className="muted">
        <span className="tag">{themeLabel(puzzle.theme)}</span>
        tática do Lichess guardada · {puzzle.solver_moves} lance(s) seu(s)
        {srs}{order}
      </div>
    );
  }
  if (!puzzle.game || puzzle.ply == null) {
    return (
      <div className="muted">
        <span className="tag">{themeLabel(puzzle.theme)}</span><span className="tag">{puzzle.category}</span>
        {puzzle.solver_moves} lance(s) seu(s)
        {srs}{order}
      </div>
    );
  }
  return (
    <div className="muted">
      <span className="tag">{themeLabel(puzzle.theme)}</span><span className="tag">{puzzle.category}</span>
      {puzzle.game.white} × {puzzle.game.black}, lance {Math.ceil(puzzle.ply / 2)} · {puzzle.solver_moves} lance(s) seu(s)
      {srs}{order}
    </div>
  );
}

export function PuzzleView({ puzzle, ctl, clockLabel, orderInfo, onSkip, skipDisabled }:
  { puzzle: Trainable; ctl: Ctl; clockLabel?: string; orderInfo?: string; onSkip?: () => void; skipDisabled?: boolean }) {
  const tactic = puzzle.kind === "tactic";
  const { state, dests } = ctl;
  // erro da partida: escondido por padrão — no "evitar" ele entrega a resposta
  const [verErro, setVerErro] = useState(false);
  const comErro = !tactic && puzzle.source === "own" && !!puzzle.mistake && !!puzzle.game ? puzzle : null;
  const playable = state.phase === "awaiting_move";
  // com o lance errado no tabuleiro a dica dá lugar ao "Tentar de novo"
  const refutando = state.phase === "refuting" || state.phase === "refuted";
  // enunciado do capítulo do estudo (comentário do autor antes do primeiro lance)
  const intro = !tactic && puzzle.source === "study" ? puzzle.solution.intro : undefined;
  // setas e casas do autor do estudo: só na posição inicial, como dica visual dele
  // (durante a introdução o tabuleiro ainda mostra a posição de antes do lance
  // do adversário, e na refutação mostra o lance errado e a réplica da engine:
  // nos dois casos essas marcações apontariam para casas cujas peças já saíram)
  const authored = (state.phase !== "intro" && !refutando && state.idx === 0 ? puzzle.solution.shapes?.["start"] : undefined) ?? [];
  const arrows = authored.filter((s) => s.dest).map((s) => ({ orig: s.orig as Key, dest: s.dest as Key, brush: s.brush }));
  const squares = authored.filter((s) => !s.dest).map((s) => ({ orig: s.orig as Key, brush: s.brush }));
  const what = tactic ? "tática" : puzzle.source === "own" ? kindLabel(puzzle.kind) : puzzle.source === "study" ? "exercício do estudo" : "tática guardada";
  return (
    <div className="two-col">
      <div>
        <Board
          fen={state.fen} orientation={puzzle.side_to_move} turnColor={state.turn}
          movableColor={playable ? puzzle.side_to_move : undefined} dests={dests}
          lastMove={state.lastMove} check={state.check} highlight={state.hint ? [state.hint] : []}
          arrows={arrows} squares={squares} drawable
          onMove={(o: Key, d: Key) => ctl.tryMove(o, d)}
        />
        {state.pendingPromotion && (
          <div className="card row" style={{ marginTop: 8 }}>
            <span>Promover a:</span>
            <div className="promo">
              {(["q", "r", "b", "n"] as const).map((p) => <button key={p} onClick={() => ctl.choosePromotion(p)}>{{ q: "♕", r: "♖", b: "♗", n: "♘" }[p]}</button>)}
            </div>
            <button onClick={ctl.cancelPromotion}>Cancelar</button>
          </div>
        )}
      </div>
      <div className="card">
        <div style={{ fontSize: 20, fontWeight: 600 }}>
          {colorName(puzzle.side_to_move)} jogam · {what}
        </div>
        {tactic ? <TacticInfo tactic={puzzle} orderInfo={orderInfo} /> : <PuzzleInfo puzzle={puzzle} orderInfo={orderInfo} />}
        {intro && <p style={{ fontWeight: 600, marginBottom: 0 }}>{intro}</p>}
        <div className={`msg ${state.message.tone}`} aria-live="polite">{state.message.text}</div>
        <div className="row" style={{ marginTop: 10 }}>
          {refutando ? (
            <button onClick={ctl.retryMove} aria-label="Tentar de novo">Tentar de novo</button>
          ) : (
            <button onClick={ctl.useHint} disabled={!playable} aria-label="Dica">
              {state.hintStage === 1 ? "Jogar o lance" : "Mostrar peça"}
            </button>
          )}
          {onSkip && <button onClick={onSkip} disabled={skipDisabled} aria-label="Pular">Pular</button>}
          {comErro && (
            <button onClick={() => setVerErro((v) => !v)} aria-expanded={verErro}>
              {comErro.kind === "avoid" ? "Meu erro (revela o lance que não jogar)" : "Erro do adversário"}
            </button>
          )}
          {clockLabel && <span className="muted" aria-label="relógio">{clockLabel}</span>}
        </div>
        {comErro && verErro && <div style={{ marginTop: 10 }}><MistakeCard puzzle={comErro} /></div>}
      </div>
    </div>
  );
}
