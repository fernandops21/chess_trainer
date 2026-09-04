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
from chess_trainer.core.puzzles.themes import infer_theme

ProgressFn = Callable[[str, int, int, str], None]
StopFn = Callable[[], bool]
Draft = tuple[Position, str, PuzzleDraft]


def build_drafts(pos: Position, engine: EngineLike, cfg: PuzzleConfig) -> list[tuple[str, PuzzleDraft]]:
    board_before = chess.Board(pos.fen)
    board_after = board_before.copy()
    board_after.push_uci(pos.move_uci)
    drafts: list[tuple[str, PuzzleDraft]] = []
    if not board_after.is_game_over():
        solver_eval = -pos.eval_after
        if is_mate_for(solver_eval) or solver_eval >= cfg.min_solver_eval_cp:
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
