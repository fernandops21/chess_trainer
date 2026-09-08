import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Chess } from "chess.js";
import type { Key } from "chessground/types";
import { api } from "../api/client";
import type { AnalyseOut, ReviewIn, ReviewOut, Trainable } from "../api/types";
import { destsFrom } from "../board/dests";
import { uciToMove } from "../board/line";
import { formatEval } from "../lib/format";
import { play, sanSound } from "../lib/sound";

/** O mínimo que a máquina de estados precisa: serve tanto para `PuzzleOut` quanto para `TacticOut`.
 *  `fen_before`/`last_move` (só os próprios/estudo/Lichess guardado têm) ligam a
 *  introdução: a posição de antes do lance do adversário, animada antes de jogar. */
export type PuzzleInput = Pick<Trainable, "id" | "fen_start" | "solution"> & {
  fen_before?: string | null;
  last_move?: string | null;
};

export type Phase = "intro" | "awaiting_move" | "engine_replying" | "refuting" | "refuted" | "solved" | "submitting" | "result" | "submit_error";
export type Promotion = "q" | "r" | "b" | "n";

/** Por que o lance errado não serve: a réplica da engine e a queda de avaliação. */
export interface Refutation {
  /** SAN do lance errado que o usuário jogou. */
  wrongSan: string;
  /** SAN da melhor réplica da engine; ausente quando o lance errado já terminou a partida. */
  replySan?: string;
  /** Avaliação depois da réplica, em centipeões do ponto de vista de quem resolve. */
  evalAfter?: number;
  /** Avaliação de antes do lance errado; chega depois, pela segunda análise. */
  evalBefore?: number;
  /** Continuação depois da réplica, em SAN. */
  pvSan: string[];
  /** Comentário do autor do estudo para este lance errado, quando houver. */
  authored?: string;
  /** Fim de partida provocado pelo lance errado. */
  terminal?: Terminal;
}

/** Fim de partida que a análise sabe apontar. */
export type Terminal = "checkmate" | "stalemate" | "draw";

const TERMINAL_TEXT: Record<Terminal, string> = {
  checkmate: "é mate, mas não é a solução do exercício",
  stalemate: "afoga o rei: empate",
  draw: "é empate",
};

/** O `terminal` da análise, quando é um dos fins de partida conhecidos. */
function terminalDe(valor: string | null | undefined): Terminal | undefined {
  return valor && Object.hasOwn(TERMINAL_TEXT, valor) ? (valor as Terminal) : undefined;
}

/** Texto da mensagem da refutação, montado do que já se sabe (a avaliação de antes pode faltar). */
function refutationMessage(r: Refutation): string {
  if (r.terminal) return `${r.wrongSan}? — ${TERMINAL_TEXT[r.terminal]}`;
  const cabeca = r.replySan ? `${r.wrongSan}? ${r.replySan}` : `${r.wrongSan}?`;
  const avaliacao = r.evalAfter == null ? ""
    : r.evalBefore != null
      ? ` — avaliação cai de ${formatEval(r.evalBefore)} para ${formatEval(r.evalAfter)}`
      : ` — avaliação ${formatEval(r.evalAfter)}`;
  const segue = r.pvSan.length ? ` · segue ${r.pvSan.join(" ")}` : "";
  const autor = r.authored ? ` — ${r.authored}` : "";
  return `${cabeca}${avaliacao}${segue}${autor}`;
}

export interface PuzzleState<R = ReviewOut> {
  phase: Phase;
  fen: string;
  turn: "white" | "black";
  idx: number;
  wrong: boolean;
  usedHint: boolean;
  /** Estágio da dica no lance atual: 0 = nenhuma dica ainda, 1 = peça destacada
   *  (o próximo clique joga o lance esperado). Volta a 0 a cada lance do solver. */
  hintStage: 0 | 1;
  message: { text: string; tone: "ok" | "bad" | "" };
  lastMove?: [Key, Key];
  check: boolean;
  hint?: Key;
  pendingPromotion?: { orig: Key; dest: Key };
  /** Só nas fases `refuting`/`refuted`: o que a engine respondeu ao lance errado. */
  refutation?: Refutation;
  review?: R;
  error?: unknown;
}

export interface UsePuzzleOptions<R = ReviewOut> {
  sessionId: string | null;
  presetHint?: boolean;
  engineDelayMs?: number;
  /** Quanto a posição de antes do lance do adversário fica na tela (padrão 400 ms). */
  introDelayMs?: number;
  submit: (body: ReviewIn) => Promise<R>;
  now?: () => number;
  /** Ligada, ao errar o lance entra no tabuleiro e a engine mostra a refutação (padrão desligada). */
  refute?: boolean;
  /** Injetável para os testes; por padrão a análise de verdade da API. */
  analyse?: (fen: string, multipv?: number) => Promise<AnalyseOut>;
}

const turnOf = (c: Chess) => (c.turn() === "w" ? "white" : "black") as "white" | "black";
const turnOfFen = (fen: string) => (fen.split(" ")[1] === "b" ? "black" : "white") as "white" | "black";
const inCheckAt = (fen: string) => { try { return new Chess(fen).inCheck(); } catch { return false; } };

/**
 * Puzzle state machine.
 *
 * Contract: mount one `usePuzzle` instance per puzzle. Consumers MUST render
 * it with a React `key={puzzle.id}` (or otherwise force a remount when the
 * puzzle changes), e.g. `<Puzzle key={puzzle.id} puzzle={puzzle} ... />`.
 * All state (`phase`, `idx`, the underlying `chess.js` position, `startedAt`,
 * etc.) is initialised once on mount from the `puzzle` prop; this hook does
 * not watch `puzzle` for changes and performs no runtime reset if a new
 * puzzle object is passed into an already-mounted instance.
 */
export function usePuzzle<R = ReviewOut>(puzzle: PuzzleInput, opts: UsePuzzleOptions<R>) {
  const chessRef = useRef(new Chess(puzzle.fen_start));
  const now = opts.now ?? Date.now;
  const startedAt = useRef(now());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Introdução: quando a fonte guarda a posição de antes do lance do adversário,
  // o puzzle abre nela e o chessground anima o lance ao trocar para `fen_start`.
  const introRef = useRef<{ fen: string; lastMove: [Key, Key] } | null>(
    puzzle.fen_before && puzzle.last_move
      ? { fen: puzzle.fen_before, lastMove: [puzzle.last_move.slice(0, 2) as Key, puzzle.last_move.slice(2, 4) as Key] }
      : null,
  );

  const [state, setState] = useState<PuzzleState<R>>(() => ({
    phase: introRef.current ? "intro" : "awaiting_move",
    fen: introRef.current?.fen ?? puzzle.fen_start,
    turn: introRef.current ? turnOfFen(introRef.current.fen) : turnOf(chessRef.current),
    idx: 0,
    wrong: false,
    usedHint: !!opts.presetHint,
    hintStage: 0,
    message: opts.presetHint ? { text: "Solução já vista: conta como dica.", tone: "bad" } : { text: "", tone: "" },
    check: introRef.current ? inCheckAt(introRef.current.fen) : chessRef.current.inCheck(),
  }));

  // Mutable bits read from within the engine-reply setTimeout callback, which
  // closes over the render that scheduled it. Keep them in refs so the
  // callback always sees the latest value instead of a stale snapshot.
  const wrongRef = useRef(state.wrong);
  wrongRef.current = state.wrong;
  const usedHintRef = useRef(state.usedHint);
  usedHintRef.current = state.usedHint;
  // Guards against double-submit: true for the whole lifetime of a submit
  // attempt (set synchronously before the first `setState`, cleared in a
  // `finally`), so a rapid double call to `retrySubmit()` cannot fire a
  // second request while the first is still in flight.
  const submittingRef = useRef(false);
  // O `lastMove` de antes do lance errado, para o "Tentar de novo" (e o fallback
  // de engine indisponível) devolverem o tabuleiro exatamente como estava.
  const lastMoveRef = useRef(state.lastMove);
  lastMoveRef.current = state.lastMove;
  const antesRef = useRef<[Key, Key] | undefined>(undefined);
  // Token da tentativa de refutação: uma resposta atrasada de uma tentativa
  // anterior (outro lance errado, ou depois do "Tentar de novo") é ignorada.
  const tentativaRef = useRef(0);
  // A avaliação de antes do lance errado pode chegar antes da réplica: fica aqui
  // até a refutação existir para recebê-la.
  // Falso depois de desmontar: nenhuma resposta da engine mexe no estado então.
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    return () => { aliveRef.current = false; if (timer.current) clearTimeout(timer.current); };
  }, []);

  // O relógio do puzzle (`startedAt`) só começa depois da introdução: o tempo
  // de ver o lance do adversário não conta como tempo de resolução.
  useEffect(() => {
    const intro = introRef.current;
    if (!intro) return;
    const t = setTimeout(() => {
      startedAt.current = now();
      // a fen vem do chess.js (e não de `puzzle.fen_start`) para bater com a das
      // jogadas seguintes: uma diferença de normalização faria o tabuleiro achar
      // que a posição mudou de novo e apagar as marcações do usuário
      setState((p) => ({ ...p, phase: "awaiting_move", fen: chessRef.current.fen(), turn: turnOf(chessRef.current), check: chessRef.current.inCheck(), lastMove: intro.lastMove }));
    }, opts.introDelayMs ?? 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const snapshot = (partial: Partial<PuzzleState<R>>) => (prev: PuzzleState<R>): PuzzleState<R> => {
    const c = chessRef.current;
    return { ...prev, fen: c.fen(), turn: turnOf(c), check: c.inCheck(), ...partial };
  };

  /** Volta o tabuleiro à posição do exercício, desfazendo o lance errado e o
   *  que a refutação tinha posto na tela ("Tentar de novo" e a engine que falhou). */
  const restaurar = (): Partial<PuzzleState<R>> => {
    const c = chessRef.current;
    return {
      fen: c.fen(), turn: turnOf(c), check: c.inCheck(), lastMove: antesRef.current,
      refutation: undefined, hintStage: 0, hint: undefined, pendingPromotion: undefined,
    };
  };

  const doSubmit = useCallback(async (wrong: boolean, usedHint: boolean) => {
    submittingRef.current = true;
    setState((p) => ({ ...p, phase: "submitting", error: undefined }));
    const body: ReviewIn = {
      puzzle_id: puzzle.id, session_id: opts.sessionId, correct: !wrong, used_hint: usedHint,
      duration_ms: Math.max(0, now() - startedAt.current),
    };
    try {
      const review = await opts.submit(body);
      setState((p) => ({ ...p, phase: "result", review }));
    } catch (error) {
      setState((p) => ({ ...p, phase: "submit_error", error }));
    } finally {
      submittingRef.current = false;
    }
  }, [puzzle.id, opts.sessionId, opts.submit, now]);

  const finish = useCallback((wrong: boolean, usedHint: boolean, text = "Certo!") => {
    play("solved");
    setState(snapshot({ phase: "solved", hint: undefined, message: { text, tone: "ok" } }));
    void doSubmit(wrong, usedHint);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doSubmit]);

  // "Certo!" ganha o comentário do autor do estudo para o lance recém-jogado
  // (`solution.comments["<índice>"]`); sem comentário, a mensagem é a de sempre.
  const okMessage = useCallback((movedIdx: number) => {
    const comment = puzzle.solution.comments?.[String(movedIdx)];
    return comment ? `Certo! — ${comment}` : "Certo!";
  }, [puzzle.solution.comments]);

  const applySolverMove = useCallback((uci: string) => {
    const c = chessRef.current;
    let mv: ReturnType<Chess["move"]>;
    try {
      mv = c.move(uciToMove(uci));
    } catch {
      // Textually matched an expected uci/alternative but chess.js rejects it
      // as an illegal move on the current position (e.g. a malformed
      // alternative). Score it as a wrong attempt instead of crashing.
      play("wrong");
      setState((p) => ({ ...p, wrong: true, hintStage: 0, pendingPromotion: undefined, message: { text: "Lance inválido", tone: "bad" } }));
      return;
    }
    // no lance final só toca o som de conclusão (tocado em `finish`)
    const nextIdx = c.history().length;
    const last: [Key, Key] = [mv.from as Key, mv.to as Key];
    const moves = puzzle.solution.moves;
    if (nextIdx >= moves.length) {
      // (sem som de lance aqui)
      setState(snapshot({ idx: nextIdx, lastMove: last, hintStage: 0, hint: undefined, pendingPromotion: undefined }));
      finish(wrongRef.current, usedHintRef.current, okMessage(nextIdx - 1));
      return;
    }
    play(sanSound(mv.san));
    const reply = moves[nextIdx];
    if (reply.by === "engine") {
      setState(snapshot({ phase: "engine_replying", idx: nextIdx, lastMove: last, hintStage: 0, hint: undefined, pendingPromotion: undefined, message: { text: okMessage(nextIdx - 1), tone: "ok" } }));
      timer.current = setTimeout(() => {
        let r: ReturnType<Chess["move"]>;
        try {
          r = chessRef.current.move(uciToMove(reply.uci));
        } catch {
          // A malformed uci from the backend for the engine's reply. Surface
          // it as a submit error instead of throwing out of the timer.
          setState((p) => ({ ...p, phase: "submit_error", error: new Error("Solução inválida do servidor") }));
          return;
        }
        // som só se o puzzle continua (no fim toca a conclusão)
        const afterReply = chessRef.current.history().length;
        const replyLast: [Key, Key] = [r.from as Key, r.to as Key];
        if (afterReply >= moves.length) {
          setState(snapshot({ idx: afterReply, lastMove: replyLast }));
          finish(wrongRef.current, usedHintRef.current, okMessage(afterReply - 1));
        } else {
          play(sanSound(r.san));
          setState(snapshot({ phase: "awaiting_move", idx: afterReply, lastMove: replyLast }));
        }
      }, opts.engineDelayMs ?? 350);
    } else {
      setState(snapshot({ phase: "awaiting_move", idx: nextIdx, lastMove: last, hintStage: 0, hint: undefined, pendingPromotion: undefined, message: { text: okMessage(nextIdx - 1), tone: "ok" } }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [puzzle.solution.moves, opts.engineDelayMs, finish, okMessage]);

  // Lance errado sem refutação (opção desligada, engine indisponível ou lance
  // ilegal): o lance é só recusado e o tabuleiro nem chega a mudar. Com
  // `voltar`, desfaz também o que a refutação já tinha posto na tela. A dica
  // volta ao estágio 0 nos dois casos, para o lance errado se comportar igual
  // com a refutação ligada ou desligada.
  const recusar = useCallback((authored?: string, voltar = false) => {
    setState((p) => ({
      ...p,
      ...(voltar ? { phase: "awaiting_move" as Phase, ...restaurar() } : null),
      wrong: true, hintStage: 0 as const, hint: undefined, pendingPromotion: undefined,
      message: { text: authored ?? "Não é esse. Tente de novo.", tone: "bad" as const },
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Refutação: o lance errado entra numa cópia da posição (o `chessRef` do
  // exercício nunca o recebe), a engine responde e a mensagem explica a queda.
  const refutar = useCallback((uci: string, authored?: string) => {
    const fenAntes = chessRef.current.fen();
    const copia = new Chess(fenAntes);
    const tentar = (promotion?: string) => {
      try { return copia.move({ ...uciToMove(uci), ...(promotion ? { promotion } : null) }); } catch { return null; }
    };
    // Um lance errado de peão à última fila chega sem a peça da promoção
    // (`tryMove` só pede a peça quando o lance esperado promove): antes de
    // desistir da refutação, tenta o mesmo lance promovendo a dama.
    const mv = tentar() ?? (uci.length === 4 ? tentar("q") : null);
    if (!mv) {
      recusar(authored);
      return;
    }
    const wrongSan = mv.san;
    const fenDepois = copia.fen();
    antesRef.current = lastMoveRef.current;
    const tentativa = ++tentativaRef.current;
    setState((p) => ({
      ...p, phase: "refuting", wrong: true, hintStage: 0, hint: undefined, pendingPromotion: undefined,
      fen: fenDepois, turn: turnOf(copia), check: copia.inCheck(), lastMove: [mv.from as Key, mv.to as Key],
      refutation: undefined, message: { text: `${wrongSan}? Vendo a resposta…`, tone: "bad" },
    }));

    const analyse = opts.analyse ?? api.analyse;
    const vale = () => aliveRef.current && tentativaRef.current === tentativa;

    void analyse(fenDepois, 1).then((out) => {
      if (!vale()) return;
      const terminal = terminalDe(out.terminal);
      if (terminal) {
        // o lance errado terminou a partida: não há réplica para mostrar
        const r: Refutation = { wrongSan, pvSan: [], authored, terminal };
        setState((p) => ({ ...p, phase: "refuted", refutation: r, message: { text: refutationMessage(r), tone: "bad" } }));
        return;
      }
      const linha = out.lines?.[0];
      let resposta: ReturnType<Chess["move"]> | null = null;
      if (linha) {
        try { resposta = copia.move(uciToMove(linha.move)); } catch { resposta = null; }
      }
      if (!linha || !resposta) { recusar(authored, true); return; }
      const rep = resposta;
      play(sanSound(rep.san));
      const r: Refutation = {
        wrongSan, replySan: rep.san, evalAfter: -linha.score,
        pvSan: (linha.pv_san ?? []).slice(1, 6), authored,
      };
      setState((p) => ({
        ...p, phase: "refuted", refutation: r, fen: copia.fen(), turn: turnOf(copia), check: copia.inCheck(),
        lastMove: [rep.from as Key, rep.to as Key], message: { text: refutationMessage(r), tone: "bad" },
      }));
      // A avaliação de antes só serve para a frase "cai de X para Y", e a engine
      // atende uma posição por vez: pedida só depois da réplica, ela não atrasa
      // o que interessa. Se falhar, a mensagem fica com a avaliação de agora.
      void analyse(fenAntes, 1).then((antes) => {
        const linhaAntes = antes.lines?.[0];
        if (!linhaAntes || !vale()) return;
        setState((p) => {
          if (!p.refutation || p.phase !== "refuted") return p;
          const comAntes: Refutation = { ...p.refutation, evalBefore: linhaAntes.score };
          return { ...p, refutation: comAntes, message: { text: refutationMessage(comAntes), tone: "bad" } };
        });
      }, () => { /* sem a avaliação de antes a mensagem continua servindo */ });
    }, () => { if (vale()) recusar(authored, true); });
  }, [opts.analyse, recusar]);

  const judge = useCallback((orig: Key, dest: Key, promotion?: Promotion) => {
    const expected = puzzle.solution.moves[state.idx];
    if (!expected || expected.by !== "solver") return;
    const uci = `${orig}${dest}${promotion ?? ""}`;
    const ok = uci === expected.uci || expected.alternatives.includes(uci);
    if (!ok) {
      // erro previsto pelo autor do estudo: a mensagem vira o comentário dele
      const authored = puzzle.solution.wrong_moves?.[uci];
      play("wrong");
      if (opts.refute) refutar(uci, authored);
      else recusar(authored);
      return;
    }
    applySolverMove(uci);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [puzzle.solution.moves, puzzle.solution.wrong_moves, state.idx, applySolverMove, opts.refute, refutar, recusar]);

  const tryMove = useCallback((orig: Key, dest: Key, promotion?: Promotion) => {
    if (state.phase !== "awaiting_move") return;
    const expected = puzzle.solution.moves[state.idx];
    const candidates = expected ? [expected.uci, ...expected.alternatives] : [];
    const needsPromotion = candidates.some((u) => u.length === 5 && u.startsWith(`${orig}${dest}`));
    if (needsPromotion && !promotion) {
      setState((p) => ({ ...p, pendingPromotion: { orig, dest } }));
      return;
    }
    judge(orig, dest, promotion);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.phase, state.idx, puzzle.solution.moves, judge]);

  const choosePromotion = useCallback((piece: Promotion) => {
    const pp = state.pendingPromotion;
    if (!pp) return;
    judge(pp.orig, pp.dest, piece);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.pendingPromotion, judge]);

  const cancelPromotion = useCallback(() => setState((p) => ({ ...p, pendingPromotion: undefined })), []);

  // Dica em dois estágios, sem limite por puzzle: o primeiro clique destaca a
  // peça que joga; o segundo joga o lance esperado (com a promoção, se houver)
  // e a máquina segue normalmente — a engine responde e o lance seguinte volta
  // ao estágio 0. Qualquer estágio já marca `usedHint`, que conta como erro.
  const useHint = useCallback(() => {
    if (state.phase !== "awaiting_move") return;
    const expected = puzzle.solution.moves[state.idx];
    if (!expected || expected.by !== "solver") return;
    if (state.hintStage === 0) {
      play("hint");
      setState((p) => ({
        ...p, usedHint: true, hintStage: 1, hint: expected.uci.slice(0, 2) as Key,
        message: { text: "Peça destacada. Clique de novo para jogar o lance (dica conta como erro).", tone: "bad" },
      }));
      return;
    }
    applySolverMove(expected.uci);
  }, [state.phase, state.idx, state.hintStage, puzzle.solution.moves, applySolverMove]);

  // "Tentar de novo": volta à posição de antes do lance errado. Vale também
  // enquanto a engine ainda pensa — a resposta que chegar depois é ignorada,
  // porque o token da tentativa já mudou.
  const retryMove = useCallback(() => {
    if (state.phase !== "refuting" && state.phase !== "refuted") return;
    tentativaRef.current++;
    setState((p) => ({
      ...p, phase: "awaiting_move", ...restaurar(),
      message: { text: "Tente de novo.", tone: "bad" },
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.phase]);

  const retrySubmit = useCallback(() => {
    if (state.phase !== "submit_error" || submittingRef.current) return;
    void doSubmit(wrongRef.current, usedHintRef.current);
  }, [doSubmit, state.phase]);

  const dests = useMemo(() => (state.phase === "awaiting_move" ? destsFrom(chessRef.current) : new Map<Key, Key[]>()), [state.phase, state.fen]);

  return { state, dests, tryMove, choosePromotion, cancelPromotion, useHint, retryMove, retrySubmit };
}

/** Retorno de `usePuzzle`; use `PuzzleCtl<unknown>` para aceitar qualquer resultado de submit. */
export type PuzzleCtl<R = ReviewOut> = ReturnType<typeof usePuzzle<R>>;
