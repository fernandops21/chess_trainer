from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    # "random" (sorteada) ou "recent" (partida mais recente primeiro)
    new_order: str
    leech_lapses: int
    analysis_seconds: int
    puzzle_search_seconds: int
    puzzle_reply_seconds: int
    tactics_rating: int
    tactics_window: int
    lichess_min_plays: int
    lichess_min_popularity: int
    # o valor do token nunca sai daqui: só se há um configurado
    lichess_token_set: bool
    classify_moves: bool


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
    new_order: Literal["random", "recent"] | None = None
    leech_lapses: int | None = None
    analysis_seconds: int | None = None
    puzzle_search_seconds: int | None = None
    puzzle_reply_seconds: int | None = None
    # mesmos limites validados no formulário de Configurações: o servidor não pode
    # confiar só no cliente (a API também é chamada direto)
    tactics_rating: int | None = Field(None, ge=400, le=3200)
    tactics_window: int | None = Field(None, ge=50)
    lichess_min_plays: int | None = Field(None, ge=0)
    lichess_min_popularity: int | None = Field(None, ge=-100, le=100)
    # ausente mantém o token guardado; string vazia apaga
    lichess_token: str | None = None
    classify_moves: bool | None = None


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
    in_queue: bool = True


class MistakeRef(BaseModel):
    ply: int
    move_played: str
    move_uci: str
    eval_before: int
    eval_after: int
    mistake_level: str | None
    mistake_by: str | None


class PuzzleSibling(BaseModel):
    id: str
    kind: str


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


class StudyRef(BaseModel):
    id: str
    title: str
    chapter_id: str
    chapter_name: str
    lichess_url: str | None = None


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
    source: str = "own"
    in_queue: bool = True
    # posição antes do último lance do adversário e o lance em si (UCI), para animar
    # a entrada do exercício; nulos quando a fonte não guarda esse lance
    fen_before: str | None = None
    last_move: str | None = None
    # partida, erro e estudo só existem conforme a fonte: fora de `own` não há partida
    game: GameRef | None = None
    ply: int | None = None
    move_played: str | None = None
    mistake: MistakeRef | None = None
    study: StudyRef | None = None
    siblings: list[PuzzleSibling] = []


class QueueIn(BaseModel):
    in_queue: bool


class QueueOut(BaseModel):
    # o modo que respondeu: "review" (repetição), "new" (novos) ou "study" (um estudo)
    mode: str
    due_count: int
    new_available: int
    new_remaining_today: int
    items: list[PuzzleOut]


class SaveTacticIn(BaseModel):
    """Resultado da tentativa ao guardar a tática: com `correct`, a tática já
    entra agendada (resolver é a primeira revisão dela). Sem corpo, só guarda."""

    correct: bool | None = None
    used_hint: bool = False
    duration_ms: int = 0
    session_id: str | None = None


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


class AnalyseIn(BaseModel):
    fen: str
    multipv: int = Field(3, ge=1, le=5)


class AnalyseLine(BaseModel):
    move: str
    san: str
    score: int
    pv: list[str]
    pv_san: list[str]


class AnalyseOut(BaseModel):
    fen: str
    turn: str
    terminal: str | None
    lines: list[AnalyseLine]


class SourceCount(BaseModel):
    in_queue: int = 0
    due: int = 0


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
    # contagem por fonte ("own", "lichess", "study"), sempre com as três chaves
    by_source: dict[str, SourceCount] = {}


class StudyOut(BaseModel):
    id: str
    title: str
    author: str
    source_url: str
    lichess_id: str | None
    # "lichess" (importado) ou "local" (criado aqui)
    origin: str = "lichess"
    imported_at: datetime | None
    updated_at: datetime | None = None
    # contagens: capítulos do estudo, capítulos com exercício (na fila ou fora),
    # exercícios na repetição e vencidos hoje
    chapter_count: int = 0
    exercise_count: int = 0
    in_queue: int = 0
    due_today: int = 0


class ChapterOut(BaseModel):
    id: str
    order: int
    name: str
    lichess_url: str | None
    mode: str
    in_queue: bool
    puzzle_id: str | None
    intro_comment: str = ""
    # nulo nos capítulos importados antes do editor
    updated_at: datetime | None = None


class ChapterDetail(ChapterOut):
    """O capítulo inteiro, como o editor precisa dele."""

    fen: str
    orientation: str
    # árvore de lances (ver `core/studies/tree.py`)
    tree: dict
    pgn: str


class StudyDetail(StudyOut):
    chapters: list[ChapterOut] = []


class StudyImportIn(BaseModel):
    url: str | None = None
    pgn: str | None = None


class StudyCreateIn(BaseModel):
    title: str = ""
    author: str = ""


class StudyUpdateIn(BaseModel):
    """Campo ausente fica como está; `chapter_order` tem de listar cada capítulo
    do estudo exatamente uma vez."""

    title: str | None = None
    author: str | None = None
    chapter_order: list[str] | None = None


class ChapterCreateIn(BaseModel):
    name: str = ""
    fen: str | None = None
    orientation: str | None = None
    mode: str | None = None


class ChapterSaveIn(BaseModel):
    name: str = ""
    mode: str = "read"
    orientation: str = "white"
    # obrigatória: salvar sem árvore apagaria o capítulo inteiro sem querer
    tree: dict


class TacticOut(BaseModel):
    id: str
    kind: str = "tactic"
    fen_start: str
    side_to_move: str
    solution: dict
    end_reason: str
    theme: str
    themes: list[str]
    category: str = "lichess"
    rating: int
    solver_moves: int
    lichess_url: str
    # posição de antes do lance do adversário e o lance em si: a tela abre nela e anima o lance
    fen_before: str
    last_move: str
    popularity: int
    nb_plays: int
    opening_tags: list[str] = []
    # já guardada como exercício da repetição (e ainda na fila)
    saved: bool = False


class AttemptIn(BaseModel):
    puzzle_id: str
    session_id: str | None = None
    correct: bool
    used_hint: bool = False
    duration_ms: int = 0


class AttemptOut(BaseModel):
    id: str
    puzzle_id: str
    correct: bool
    used_hint: bool
    rating_before: int
    rating_after: int
    delta: int
    puzzle_rating: int


class TacticsStatusOut(BaseModel):
    imported: bool
    count: int
    imported_at: str | None
    source_rows: int | None
    rating: int
    window: int
    attempts_total: int
    attempts_today: int
    attempts_30d: int
    correct_30d: int


class ThemeCountOut(BaseModel):
    theme: str
    label: str
    count: int


class ThemeStatOut(BaseModel):
    theme: str
    label: str
    attempts: int
    correct: int
    accuracy: float
    own: int
    lichess: int
