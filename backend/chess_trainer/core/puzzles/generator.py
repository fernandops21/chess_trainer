import json
from dataclasses import asdict, dataclass, field

import chess

from chess_trainer.core.analysis.engine import EngineLike, LineEval
from chess_trainer.core.evals import clamp, is_mate_for
from chess_trainer.core.puzzles.material import floor_to_piece, material_balance


@dataclass
class SolutionMove:
    uci: str
    by: str  # "solver" | "engine"
    alternatives: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PuzzleDraft:
    fen_start: str
    side_to_move: str
    moves: list[SolutionMove]
    end_reason: str  # "mate" | "material_gain" | "explanation"
    solver_moves: int
    explanation_pv: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({"moves": [m.to_dict() for m in self.moves], "explanation_pv": self.explanation_pv})


@dataclass(frozen=True)
class PuzzleConfig:
    depth: int = 22
    reply_depth: int = 16
    alt_window_cp: int = 50
    max_solver_moves: int = 10
    max_mate_moves: int = 15
    min_solver_eval_cp: int = 100
    avoid_gap_cp: int = 150


def _color_name(color: chess.Color) -> str:
    return "white" if color == chess.WHITE else "black"


def _gain(board: chess.Board, solver: chess.Color, start_balance: int) -> int:
    return material_balance(board, solver) - start_balance


def _is_close(best: LineEval, alt: LineEval, cfg: PuzzleConfig, mate_mode: bool) -> bool:
    if mate_mode:
        return alt.score == best.score
    return best.score - alt.score <= cfg.alt_window_cp


def _final_alternatives(
    board: chess.Board, close_alts: list[LineEval], mate_mode: bool,
    target: int, start_balance: int, solver: chess.Color,
) -> list[str] | None:
    """Alternativas aceitas no lance final; None se alguma alternativa próxima não materializa."""
    accepted: list[str] = []
    for alt in close_alts:
        if not alt.pv or alt.pv[0] != alt.move:
            return None
        b = board.copy()
        b.push_uci(alt.move)
        if b.is_checkmate():
            accepted.append(alt.move)
            continue
        if b.is_game_over():
            return None
        if mate_mode:
            return None
        if len(alt.pv) < 2:
            return None
        gain_now = _gain(b, solver, start_balance)
        try:
            b.push_uci(alt.pv[1])
        except ValueError:
            return None
        if b.is_game_over():
            return None
        gain_after = _gain(b, solver, start_balance)
        if gain_now >= target and gain_after >= target:
            accepted.append(alt.move)
        else:
            return None
    return accepted


def _pv_never_materializes(
    board: chess.Board, pv: tuple[str, ...], target: int, start_balance: int,
    solver: chess.Color, max_solver_moves: int,
) -> bool:
    """True se a PV (>=4 lances) percorre até max_solver_moves lances do solver sem o ganho se
    materializar em nenhum ponto (mesma condição de _final_alternatives). PV curta, lance ilegal na
    PV, ou fim de jogo inesperado são inconclusivos (False): deixa o laço normal decidir."""
    if len(pv) < 4:
        return False
    b = board.copy()
    pairs = min(max_solver_moves, len(pv) // 2)
    for i in range(pairs):
        try:
            b.push_uci(pv[2 * i])
        except ValueError:
            return False
        if b.is_checkmate():
            return False  # materializa via mate
        if b.is_game_over():
            return False  # inconclusivo
        gain_now = _gain(b, solver, start_balance)
        reply_index = 2 * i + 1
        if reply_index >= len(pv):
            return False  # PV termina no lance do solver: inconclusivo
        try:
            b.push_uci(pv[reply_index])
        except ValueError:
            return False
        if b.is_game_over():
            return False
        gain_after = _gain(b, solver, start_balance)
        if gain_now >= target and gain_after >= target:
            return False  # materializou
    if pairs < max_solver_moves and len(pv) % 2 == 1:
        # a PV tem um lance do solver a mais além dos pares completos (ex.: termina numa
        # captura do solver) que o laço acima nunca chega a examinar; sem olhar esse lance
        # final não dá para afirmar que o ganho nunca materializa -- inconclusivo.
        return False
    return True


def _draft(board: chess.Board, moves: list[SolutionMove], end_reason: str) -> PuzzleDraft:
    return PuzzleDraft(
        fen_start=board.fen(),
        side_to_move=_color_name(board.turn),
        moves=moves,
        end_reason=end_reason,
        solver_moves=sum(1 for m in moves if m.by == "solver"),
    )


def generate_punish(board: chess.Board, drop_cp: int, engine: EngineLike, cfg: PuzzleConfig) -> PuzzleDraft | None:
    solver = board.turn
    start_balance = material_balance(board, solver)

    lines: list[LineEval] | None = engine.analyse(board, cfg.depth, multipv=3)
    if not lines:
        return None
    mate_mode = is_mate_for(lines[0].score)
    target = 0
    if not mate_mode:
        if lines[0].score < cfg.min_solver_eval_cp:
            return None
        # o alvo é o menor entre a queda e a avaliação do solver: uma queda enorme
        # (mate perdido) não pode exigir ganho de dama se a posição só vale +3
        target = floor_to_piece(min(clamp(drop_cp), lines[0].score) / 100)
        if target <= 0:
            return None
        # Pré-checagem barata: pode descartar puzzles que o laço completo abaixo teria encontrado,
        # quando a resposta rasa (reply_depth) do laço se desvia da PV usada aqui. Isso é aceito:
        # a linha profunda (multipv=3, depth cheio) já disse que o ganho não se sustenta ao longo
        # dessa PV, então vale a pena economizar as chamadas de engine do laço nesse caso.
        if _pv_never_materializes(board, lines[0].pv, target, start_balance, solver, cfg.max_solver_moves):
            return None

    limit = cfg.max_mate_moves if mate_mode else cfg.max_solver_moves
    moves: list[SolutionMove] = []
    current = board.copy()

    for _ in range(limit):
        if lines is None:
            lines = engine.analyse(current, cfg.depth, multipv=3)
            if not lines:
                return None
        best = lines[0]
        close_alts = [alt for alt in lines[1:] if _is_close(best, alt, cfg, mate_mode)]

        after = current.copy()
        after.push_uci(best.move)
        if after.is_checkmate():
            alts = _final_alternatives(current, close_alts, mate_mode, target, start_balance, solver)
            if alts is None:
                return None
            moves.append(SolutionMove(best.move, "solver", alts))
            return _draft(board, moves, "mate")
        if after.is_game_over():
            return None

        # modo mate exige profundidade cheia na resposta: uma defesa mal calculada por
        # profundidade rasa (reply_depth) quebra a linha de mate inteira.
        reply_depth = cfg.depth if mate_mode else cfg.reply_depth
        reply_lines = engine.analyse(after, reply_depth, multipv=1)
        if not reply_lines:
            return None
        reply = reply_lines[0]
        after_reply = after.copy()
        after_reply.push_uci(reply.move)

        if not mate_mode and _gain(after, solver, start_balance) >= target \
                and _gain(after_reply, solver, start_balance) >= target:
            if after_reply.is_game_over():
                return None
            alts = _final_alternatives(current, close_alts, mate_mode, target, start_balance, solver)
            if alts is None:
                return None
            moves.append(SolutionMove(best.move, "solver", alts))
            return _draft(board, moves, "material_gain")

        if close_alts:
            return None  # ambiguidade em lance intermediário

        moves.append(SolutionMove(best.move, "solver"))
        moves.append(SolutionMove(reply.move, "engine"))
        current = after_reply
        if current.is_game_over():
            return None
        lines = None

    return None


def generate_avoid(
    board_before: chess.Board, engine: EngineLike, cfg: PuzzleConfig, played_uci: str | None = None,
) -> PuzzleDraft | None:
    lines = engine.analyse(board_before, cfg.depth, multipv=2)
    if len(lines) < 2:
        return None
    best, second = lines[0], lines[1]
    if played_uci is not None and best.move == played_uci:
        return None  # o lance jogado já era o melhor; não há o que evitar
    if best.score - second.score < cfg.avoid_gap_cp:
        return None
    return PuzzleDraft(
        fen_start=board_before.fen(),
        side_to_move=_color_name(board_before.turn),
        moves=[SolutionMove(best.move, "solver")],
        end_reason="explanation",
        solver_moves=1,
        explanation_pv=list(best.pv[:6]),
    )
