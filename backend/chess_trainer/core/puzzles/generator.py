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
    end_reason: str  # "mate" | "material_gain" ("explanation": puzzles antigos de "evitar")
    solver_moves: int
    explanation_pv: list[str] = field(default_factory=list)  # legado; hoje sempre vazio

    def to_json(self) -> str:
        return json.dumps({"moves": [m.to_dict() for m in self.moves], "explanation_pv": self.explanation_pv})


@dataclass(frozen=True)
class PuzzleConfig:
    depth: int = 22
    alt_window_cp: int = 50
    max_solver_moves: int = 10
    max_mate_moves: int = 15
    min_solver_eval_cp: int = 100
    avoid_gap_cp: int = 150
    unique_gap_cp: int = 150
    search_seconds: float = 20.0


# Proteção contra laço, não regra: a regra é o exercício continuar enquanto o lance do aluno
# for único, sem teto de lances. Este limite só existe para a linha não crescer sem fim.
MAX_EXTENSION_PLIES = 60


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


def extend_unique_line(
    board_after_solution: chess.Board, engine: EngineLike, cfg: PuzzleConfig, solver: chess.Color,
    known_reply: SolutionMove | None = None,
) -> list[SolutionMove]:
    """Continua a linha depois da solução enquanto o lance do aluno for único.

    Na vez do adversário joga a primeira linha da engine. Na vez do aluno pede três linhas:
    o lance só entra no exercício se estiver à frente do segundo por `cfg.unique_gap_cp` (dois
    lances bons seriam técnica, não tática) e se ainda ganhar (`cfg.min_solver_eval_cp`). Em
    mate, posição terminal ou engine sem linha a extensão acaba ali, e a linha devolvida nunca
    termina com lance do adversário.

    `known_reply` é a resposta do adversário que o chamador já buscou e validou para a posição
    inicial: evita a segunda busca e garante que a linha siga a mesma resposta com que o ganho
    foi conferido (outra busca poderia escolher uma defesa diferente). Sem ele — o job que
    alonga exercícios já gravados — a resposta é buscada normalmente."""
    extra: list[SolutionMove] = []
    current = board_after_solution.copy()
    if known_reply is not None and not current.is_game_over() and current.turn != solver:
        try:
            current.push_uci(known_reply.uci)
        except ValueError:
            return []
        extra.append(SolutionMove(known_reply.uci, known_reply.by))
    for _ in range(MAX_EXTENSION_PLIES):
        if current.is_game_over():
            break
        if current.turn != solver:
            lines = engine.analyse(current, cfg.depth, multipv=1, max_seconds=cfg.search_seconds)
            if not lines:
                break
            try:
                current.push_uci(lines[0].move)
            except ValueError:
                break
            extra.append(SolutionMove(lines[0].move, "engine"))
            continue
        lines = engine.analyse(current, cfg.depth, multipv=3, max_seconds=cfg.search_seconds)
        if not lines:
            break
        best = lines[0]
        # uma linha só: não há segundo lance para comparar, o gap é infinito
        gap = 10**6 if len(lines) < 2 else best.score - lines[1].score
        if gap < cfg.unique_gap_cp:
            # dois lances bons: daqui para a frente é técnica. Duas linhas de mate entram aqui
            # (mesmo score, gap 0) e param a extensão de propósito: as duas ganham, então não há
            # lance único a cobrar, e a solução fica na conquista já validada. Diferente do
            # `avoid`, que trata mate categoricamente.
            break
        if best.score < cfg.min_solver_eval_cp:
            break  # o lance único já não ganha; a solução fica como estava até aqui
        try:
            current.push_uci(best.move)
        except ValueError:
            break
        extra.append(SolutionMove(best.move, "solver", []))
        if current.is_checkmate():
            break  # em mate a linha termina com o lance que dá mate
    if extra and extra[-1].by == "engine":
        extra.pop()  # a solução nunca termina com lance do adversário
    return extra


def _draft(board: chess.Board, moves: list[SolutionMove], end_reason: str) -> PuzzleDraft:
    return PuzzleDraft(
        fen_start=board.fen(),
        side_to_move=_color_name(board.turn),
        moves=moves,
        end_reason=end_reason,
        solver_moves=sum(1 for m in moves if m.by == "solver"),
    )


def _materializing_line(
    board: chess.Board, engine: EngineLike, cfg: PuzzleConfig,
    first_lines: list[LineEval], mate_mode: bool, target: int,
) -> PuzzleDraft | None:
    """Joga a linha da engine a partir de `board` (com a primeira análise já feita em
    `first_lines`) até o ganho se materializar: mate, ou captura que atinge `target` e
    sobrevive à melhor resposta. Descarta em empate, ambiguidade intermediária ou limite
    de lances. Compartilhado pelos puzzles "punir" e "evitar"."""
    solver = board.turn
    start_balance = material_balance(board, solver)
    lines: list[LineEval] | None = first_lines
    limit = cfg.max_mate_moves if mate_mode else cfg.max_solver_moves
    moves: list[SolutionMove] = []
    current = board.copy()

    for _ in range(limit):
        if lines is None:
            lines = engine.analyse(current, cfg.depth, multipv=3, max_seconds=cfg.search_seconds)
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

        # a resposta usa a mesma busca funda do lance do solver: a primeira linha da busca
        # do lado a jogar já é a defesa mais resistente. Uma busca mais rasa aqui discordaria
        # da Análise entre defesas quase iguais (e quebraria a linha de mate inteira).
        reply_lines = engine.analyse(after, cfg.depth, multipv=1, max_seconds=cfg.search_seconds)
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
            # o ganho já está de pé; se o aluno ainda tem lance único a seguir, o exercício continua
            extra = extend_unique_line(after, engine, cfg, solver,
                                       known_reply=SolutionMove(reply.move, "engine"))
            # só o último lance da solução pode ter alternativas: com extensão, a captura deixa de
            # ser o fim da linha e a continuação gravada vale só para o lance principal
            moves.append(SolutionMove(best.move, "solver", [] if extra else alts))
            moves.extend(extra)
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


def generate_punish(board: chess.Board, drop_cp: int, engine: EngineLike, cfg: PuzzleConfig) -> PuzzleDraft | None:
    solver = board.turn
    lines = engine.analyse(board, cfg.depth, multipv=3, max_seconds=cfg.search_seconds)
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
        # quando a resposta do laço (multipv=1) se desvia da PV usada aqui. Isso é aceito:
        # a linha profunda (multipv=3, depth cheio) já disse que o ganho não se sustenta ao longo
        # dessa PV, então vale a pena economizar as chamadas de engine do laço nesse caso.
        if _pv_never_materializes(board, lines[0].pv, target, material_balance(board, solver),
                                  solver, cfg.max_solver_moves):
            return None
    return _materializing_line(board, engine, cfg, lines, mate_mode, target)


def generate_avoid(
    board_before: chess.Board, engine: EngineLike, cfg: PuzzleConfig, played_uci: str | None = None,
) -> PuzzleDraft | None:
    """O "evitar" é a linha que o usuário deixou de jogar, levada até o ganho se materializar
    (mesma máquina do "punir"): o lance certo tem de ser único o bastante (gap) e concreto."""
    solver = board_before.turn
    lines = engine.analyse(board_before, cfg.depth, multipv=3, max_seconds=cfg.search_seconds)
    if len(lines) < 2:
        return None  # sem segunda linha não dá para medir o gap
    best, second = lines[0], lines[1]
    if played_uci is not None and best.move == played_uci:
        return None  # o lance jogado já era o melhor; não há o que evitar
    mate_mode = is_mate_for(best.score)
    # mate a favor no melhor lance conta como gap infinito, mesmo se a segunda linha também
    # mata (mate-in diferente): a diferença categórica é ter mate ou não, não a distância entre
    # mates -- alternativas de mate próximas ficam por conta de _is_close/_final_alternatives.
    gap = 10**6 if mate_mode else best.score - second.score
    if gap < cfg.avoid_gap_cp:
        return None
    target = 0
    if not mate_mode:
        if best.score < cfg.min_solver_eval_cp:
            return None
        # o alvo é o menor entre o gap e a avaliação do lance certo, como no "punir"
        target = floor_to_piece(min(clamp(gap), clamp(best.score)) / 100)
        if target <= 0:
            return None
        if _pv_never_materializes(board_before, best.pv, target, material_balance(board_before, solver),
                                  solver, cfg.max_solver_moves):
            return None
    return _materializing_line(board_before, engine, cfg, lines, mate_mode, target)
