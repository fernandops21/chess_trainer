from typing import Callable

import chess
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from chess_trainer.config import AppSettings, puzzle_config_from, thresholds_from
from chess_trainer.core.analysis.engine import EngineLike
from chess_trainer.core.analysis.mistakes import classify_positions
from chess_trainer.core.models import Game, Position, Puzzle, Review
from chess_trainer.core.puzzles.generator import PuzzleConfig, PuzzleDraft, generate_avoid, generate_punish
from chess_trainer.core.puzzles.themes import infer_theme

ProgressFn = Callable[[str, int, int, str], None]


def build_drafts(pos: Position, engine: EngineLike, cfg: PuzzleConfig) -> list[tuple[str, PuzzleDraft]]:
    board_before = chess.Board(pos.fen)
    board_after = board_before.copy()
    board_after.push_uci(pos.move_uci)
    drafts: list[tuple[str, PuzzleDraft]] = []
    if not board_after.is_game_over():
        punish = generate_punish(board_after, pos.eval_before - pos.eval_after, engine, cfg)
        if punish is not None:
            drafts.append(("punish", punish))
    if pos.mistake_by == "me":
        avoid = generate_avoid(board_before, engine, cfg)
        if avoid is not None:
            drafts.append(("avoid", avoid))
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


def generate_puzzles_for_game(db: Session, game: Game, engine: EngineLike, cfg: PuzzleConfig) -> int:
    created = 0
    for pos in game.positions:
        if not pos.is_mistake:
            continue
        for kind, draft in build_drafts(pos, engine, cfg):
            if persist_draft(db, pos, game, kind, draft) is not None:
                created += 1
    return created


def regenerate_all(db: Session, engine: EngineLike, settings: AppSettings, progress: ProgressFn | None = None) -> int:
    db.execute(delete(Review))
    db.execute(delete(Puzzle))
    db.commit()
    thresholds = thresholds_from(settings)
    cfg = puzzle_config_from(settings)
    games = db.scalars(select(Game).where(Game.analyzed_at.is_not(None)).order_by(Game.played_at.desc())).all()
    total = 0
    for i, game in enumerate(games):
        if progress:
            progress("regenerate", i, len(games), f"{game.white} x {game.black}")
        classify_positions(game.positions, game.my_color, thresholds)
        total += generate_puzzles_for_game(db, game, engine, cfg)
        db.commit()
    if progress:
        progress("regenerate", len(games), len(games), "concluído")
    return total
