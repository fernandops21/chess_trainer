from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SettingsOut(BaseModel):
    chesscom_username: str
    categories: list[str]
    stockfish_path: str
    analysis_depth: int
    puzzle_depth: int
    mistake_threshold_cp: int
    blunder_threshold_cp: int
    avoid_gap_cp: int
    new_per_day: int
    leech_lapses: int


class SettingsIn(BaseModel):
    chesscom_username: str | None = None
    categories: list[str] | None = None
    stockfish_path: str | None = None
    analysis_depth: int | None = None
    puzzle_depth: int | None = None
    mistake_threshold_cp: int | None = None
    blunder_threshold_cp: int | None = None
    avoid_gap_cp: int | None = None
    new_per_day: int | None = None
    leech_lapses: int | None = None


class GameOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source_id: str
    white: str
    black: str
    result: str
    time_control: str
    category: str
    played_at: datetime
    my_color: str
    analyzed_at: datetime | None
    my_mistakes: int = 0


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    ply: int
    fen: str
    move_played: str
    move_uci: str
    eval_before: int
    eval_after: int
    best_move: str | None
    is_mistake: bool
    mistake_level: str | None
    mistake_by: str | None
    puzzle_ids: list[str] = []


class GameDetail(GameOut):
    pgn: str
    positions: list[PositionOut]


class PuzzleRef(BaseModel):
    id: str
    kind: str
    theme: str
    is_leech: bool


class MistakeOut(BaseModel):
    position_id: str
    game_id: str
    ply: int
    fen: str
    move_played: str
    move_uci: str
    best_move: str | None
    eval_before: int
    eval_after: int
    mistake_level: str
    mistake_by: str
    category: str
    played_at: datetime
    white: str
    black: str
    my_color: str
    puzzles: list[PuzzleRef]


class SrsOut(BaseModel):
    ease: float
    interval_days: int
    lapses: int
    due_at: datetime | None
    last_reviewed_at: datetime | None


class GameRef(BaseModel):
    id: str
    white: str
    black: str
    played_at: datetime
    source_id: str
    my_color: str


class PuzzleOut(BaseModel):
    id: str
    kind: str
    fen_start: str
    side_to_move: str
    solution: dict
    end_reason: str
    theme: str
    category: str
    solver_moves: int
    is_leech: bool
    srs: SrsOut
    game: GameRef
    ply: int
    move_played: str


class QueueOut(BaseModel):
    due_count: int
    new_available: int
    new_remaining_today: int
    items: list[PuzzleOut]


class SessionIn(BaseModel):
    planned_minutes: int | None = None
    filters: dict = {}


class SessionOut(BaseModel):
    id: str
    started_at: datetime
    ended_at: datetime | None
    planned_minutes: int | None
    filters: dict
    reviews: int = 0
    correct: int = 0
    total_duration_ms: int = 0


class ReviewIn(BaseModel):
    puzzle_id: str
    session_id: str | None = None
    correct: bool
    used_hint: bool = False
    duration_ms: int = 0


class ReviewOut(BaseModel):
    id: str
    puzzle_id: str
    result: str
    used_hint: bool
    ease: float
    interval_days: int
    due_at: datetime
    lapses: int
    is_leech: bool


class DashboardOut(BaseModel):
    due_today: int
    new_available: int
    new_remaining_today: int
    streak_days: int
    reviews_today: int
    last_import_at: datetime | None
    games_total: int
    games_analyzed: int
    puzzles_total: int
    leeches: int
