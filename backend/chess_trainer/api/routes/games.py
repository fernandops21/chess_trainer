from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from chess_trainer.api.deps import get_db
from chess_trainer.api.schemas import GameDetail, GameOut, MistakeOut, PositionOut, PuzzleRef
from chess_trainer.core.models import Game, Position, Puzzle

router = APIRouter(prefix="/api")


def _my_mistakes_map(db: Session, game_ids: list[str]) -> dict[str, int]:
    if not game_ids:
        return {}
    rows = db.execute(
        select(Position.game_id, func.count(Position.id))
        .where(Position.game_id.in_(game_ids), Position.is_mistake.is_(True), Position.mistake_by == "me")
        .group_by(Position.game_id)
    ).all()
    return {game_id: n for game_id, n in rows}


def _game_out(game: Game, my_mistakes: int) -> GameOut:
    out = GameOut.model_validate(game)
    out.my_mistakes = my_mistakes
    return out


@router.get("/games", response_model=list[GameOut])
def list_games(
    category: str | None = None,
    color: str | None = None,
    result: str | None = None,
    analyzed: bool | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    stmt = select(Game).order_by(Game.played_at.desc()).limit(limit).offset(offset)
    if category:
        stmt = stmt.where(Game.category == category)
    if color:
        stmt = stmt.where(Game.my_color == color)
    if result:
        stmt = stmt.where(Game.result == result)
    if analyzed is True:
        stmt = stmt.where(Game.analyzed_at.is_not(None))
    elif analyzed is False:
        stmt = stmt.where(Game.analyzed_at.is_(None))
    games = db.scalars(stmt).all()
    counts = _my_mistakes_map(db, [g.id for g in games])
    return [_game_out(g, counts.get(g.id, 0)) for g in games]


@router.get("/games/{game_id}", response_model=GameDetail)
def get_game(game_id: str, db: Session = Depends(get_db)):
    game = db.get(Game, game_id, options=[selectinload(Game.positions).selectinload(Position.puzzles)])
    if game is None:
        raise HTTPException(404, "partida não encontrada")
    positions = []
    for pos in game.positions:
        out = PositionOut.model_validate(pos)
        out.puzzle_ids = [p.id for p in pos.puzzles]
        positions.append(out)
    base = _game_out(game, _my_mistakes_map(db, [game.id]).get(game.id, 0))
    return GameDetail(**base.model_dump(), pgn=game.pgn, positions=positions)


@router.get("/mistakes", response_model=list[MistakeOut])
def list_mistakes(
    level: str | None = None,
    theme: str | None = None,
    category: str | None = None,
    by: str = "me",
    limit: int = 200,
    db: Session = Depends(get_db),
):
    stmt = (
        select(Position, Game)
        .join(Game, Game.id == Position.game_id)
        .where(Position.is_mistake.is_(True))
        .order_by(Game.played_at.desc(), Position.ply)
        .limit(limit)
        .options(selectinload(Position.puzzles))
    )
    if by in ("me", "opponent"):
        stmt = stmt.where(Position.mistake_by == by)
    if level:
        stmt = stmt.where(Position.mistake_level == level)
    if category:
        stmt = stmt.where(Game.category == category)
    if theme:
        stmt = stmt.where(Position.id.in_(select(Puzzle.position_id).where(Puzzle.theme == theme)))
    items = []
    for pos, game in db.execute(stmt).all():
        items.append(MistakeOut(
            position_id=pos.id, game_id=game.id, ply=pos.ply, fen=pos.fen, move_played=pos.move_played,
            move_uci=pos.move_uci, best_move=pos.best_move, eval_before=pos.eval_before,
            eval_after=pos.eval_after, mistake_level=pos.mistake_level, mistake_by=pos.mistake_by,
            category=game.category, played_at=game.played_at, white=game.white, black=game.black,
            my_color=game.my_color,
            puzzles=[PuzzleRef(id=p.id, kind=p.kind, theme=p.theme, is_leech=p.is_leech) for p in pos.puzzles],
        ))
    return items
