from typing import Callable, Iterable

import chess
import chess.engine
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from chess_trainer.config import AppSettings, puzzle_config_from, thresholds_from
from chess_trainer.core.analysis.engine import EngineLike
from chess_trainer.core.analysis.mistakes import classify_positions
from chess_trainer.core.evals import is_mate_for
from chess_trainer.core.models import Game, Position, Puzzle, Review
from chess_trainer.core.puzzles.generator import PuzzleConfig, PuzzleDraft, generate_avoid, generate_punish
from chess_trainer.core.puzzles.material import PIECE_VALUES
from chess_trainer.core.puzzles.themes import infer_theme

ProgressFn = Callable[[str, int, int, str], None]
StopFn = Callable[[], bool]
Draft = tuple[Position, str, PuzzleDraft]


def _is_trivial_punish(board_after: chess.Board, move_uci: str, solver_eval: int) -> bool:
    """Peça de valor >= 3 deixada de graça na própria casa de destino, sem nada maior por trás
    (avaliação do solver não indica mate nem vantagem além do ganho líquido dessa captura).

    Só conta atacantes cuja captura é de fato legal: `is_attacked_by`/`attackers` são puramente
    geométricos e ignoram cravadas (peça presa ao próprio rei) e reis que capturariam entrando em
    xeque -- um "atacante" nessas condições não pode de fato punir, então não torna o puzzle trivial.
    """
    to_sq = chess.Move.from_uci(move_uci).to_square
    piece = board_after.piece_at(to_sq)
    if piece is None:
        return False
    value = PIECE_VALUES[piece.piece_type]
    if value < 3:
        return False
    solver = board_after.turn
    mover = not solver

    def _legal_capture_value(from_sq: chess.Square) -> int | None:
        attacker = board_after.piece_at(from_sq)
        promotion = chess.QUEEN if attacker.piece_type == chess.PAWN and chess.square_rank(to_sq) in (0, 7) else None
        move = chess.Move(from_sq, to_sq, promotion=promotion)
        if move not in board_after.legal_moves:
            return None
        return PIECE_VALUES[attacker.piece_type]

    attacker_values = [
        v for a in board_after.attackers(solver, to_sq) if (v := _legal_capture_value(a)) is not None
    ]
    if not attacker_values:
        return False  # nenhum atacante consegue capturar de fato (preso ou rei entraria em xeque)

    undefended = not board_after.is_attacked_by(mover, to_sq)
    # o rei nunca conta na comparação de "atacante mais barato": ele só pode capturar
    # legalmente uma casa indefesa, caso já coberto pelo ramo `undefended` abaixo.
    cheaper_values = [v for v in attacker_values if v > 0]
    cheaper_attacker = bool(cheaper_values) and min(cheaper_values) < value
    if not (undefended or cheaper_attacker):
        return False
    if is_mate_for(solver_eval):
        return False
    net = value if undefended else value - min(cheaper_values)
    return solver_eval <= net * 100 + 200


def build_drafts(pos: Position, engine: EngineLike, cfg: PuzzleConfig) -> list[tuple[str, PuzzleDraft]]:
    board_before = chess.Board(pos.fen)
    board_after = board_before.copy()
    board_after.push_uci(pos.move_uci)
    drafts: list[tuple[str, PuzzleDraft]] = []
    if not board_after.is_game_over():
        solver_eval = -pos.eval_after
        if is_mate_for(solver_eval) or solver_eval >= cfg.min_solver_eval_cp:
            if not _is_trivial_punish(board_after, pos.move_uci, solver_eval):
                punish = generate_punish(board_after, pos.eval_before - pos.eval_after, engine, cfg)
                if punish is not None:
                    drafts.append(("punish", punish))
    if pos.mistake_by == "me":
        avoid = generate_avoid(board_before, engine, cfg, played_uci=pos.move_uci)
        if avoid is not None:
            drafts.append(("avoid", avoid))
    return drafts


def draft_puzzles(
    positions: Iterable[Position], engine: EngineLike, cfg: PuzzleConfig, should_stop: StopFn | None = None,
) -> list[Draft] | None:
    """Fase pura de engine: nenhum acesso ao banco, para rodar fora da transação de escrita.

    Se `should_stop` virar verdadeiro entre um erro e o próximo, devolve None: o chamador não
    deve persistir nada desta partida.
    """
    drafts: list[Draft] = []
    for pos in positions:
        if not pos.is_mistake:
            continue
        for kind, draft in build_drafts(pos, engine, cfg):
            drafts.append((pos, kind, draft))
        if should_stop is not None and should_stop():
            return None
    return drafts


def persist_draft(db: Session, pos: Position, game: Game, kind: str, draft: PuzzleDraft) -> Puzzle | None:
    exists = db.scalar(select(Puzzle.id).where(Puzzle.fen_start == draft.fen_start, Puzzle.kind == kind))
    if exists:
        return None
    puzzle = Puzzle(
        position_id=pos.id,
        game_id=game.id,
        kind=kind,
        fen_start=draft.fen_start,
        side_to_move=draft.side_to_move,
        solution=draft.to_json(),
        end_reason=draft.end_reason,
        theme=infer_theme(draft.fen_start, draft.moves, draft.end_reason),
        category=game.category,
        solver_moves=draft.solver_moves,
    )
    db.add(puzzle)
    db.flush()
    return puzzle


def persist_drafts(db: Session, game: Game, drafts: Iterable[Draft]) -> int:
    """Fase curta de escrita: assume que a engine já terminou."""
    created = 0
    for pos, kind, draft in drafts:
        if persist_draft(db, pos, game, kind, draft) is not None:
            created += 1
    return created


def regenerate_all(
    db: Session,
    engine: EngineLike,
    settings: AppSettings,
    progress: ProgressFn | None = None,
    should_stop: StopFn | None = None,
) -> int:
    db.execute(delete(Review))
    db.execute(delete(Puzzle))
    db.commit()
    thresholds = thresholds_from(settings)
    cfg = puzzle_config_from(settings)
    games = db.scalars(select(Game).where(Game.analyzed_at.is_not(None)).order_by(Game.played_at.desc())).all()
    total = 0
    for i, game in enumerate(games):
        if should_stop is not None and should_stop():
            if progress:
                progress("regenerate", i, len(games), "cancelado")
            return total
        if progress:
            progress("regenerate", i, len(games), f"{game.white} x {game.black}")
        try:
            # sem autoflush: reclassificar suja as posições, mas a escrita só acontece no commit abaixo,
            # depois que a engine terminou — nunca com a engine pensando e o banco travado
            with db.no_autoflush:
                positions = list(game.positions)
                classify_positions(positions, game.my_color, thresholds)
                drafts = draft_puzzles(positions, engine, cfg, should_stop=should_stop)
            if drafts is None:
                db.rollback()
                if progress:
                    progress("regenerate", i, len(games), "cancelado")
                return total
            total += persist_drafts(db, game, drafts)
            db.commit()
        except chess.engine.EngineError:
            db.rollback()
            engine.restart()
            continue
    if progress:
        progress("regenerate", len(games), len(games), "concluído")
    return total
