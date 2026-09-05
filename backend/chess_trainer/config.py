import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any

from sqlalchemy.orm import Session

from chess_trainer.core.analysis.mistakes import Thresholds
from chess_trainer.core.models import Setting
from chess_trainer.core.puzzles.generator import PuzzleConfig


@dataclass
class AppSettings:
    chesscom_username: str = ""
    categories: list[str] = field(default_factory=lambda: ["rapid", "daily", "classical"])
    stockfish_path: str = ""
    analysis_depth: int = 18
    puzzle_depth: int = 20
    mistake_threshold_cp: int = 100
    blunder_threshold_cp: int = 200
    avoid_gap_cp: int = 150
    new_per_day: int = 10
    leech_lapses: int = 5
    analysis_seconds: int = 15
    puzzle_search_seconds: int = 20
    puzzle_reply_seconds: int = 10


def get_setting(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(Setting, key)
    return json.loads(row.value) if row else default


def set_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=json.dumps(value)))
    else:
        row.value = json.dumps(value)
    db.commit()


def load_settings(db: Session) -> AppSettings:
    values: dict[str, Any] = {}
    for f in fields(AppSettings):
        stored = get_setting(db, f.name, None)
        if stored is not None:
            values[f.name] = stored
    return AppSettings(**values)


def save_settings(db: Session, settings: AppSettings) -> AppSettings:
    settings.chesscom_username = settings.chesscom_username.strip().lower()
    for key, value in asdict(settings).items():
        set_setting(db, key, value)
    return settings


def thresholds_from(settings: AppSettings) -> Thresholds:
    return Thresholds(
        mistake_cp=settings.mistake_threshold_cp,
        blunder_cp=settings.blunder_threshold_cp,
    )


def puzzle_config_from(settings: AppSettings) -> PuzzleConfig:
    return PuzzleConfig(
        depth=settings.puzzle_depth,
        # nunca mais fundo que depth: com puzzle_depth abaixo do mínimo prático (12),
        # o piso de 12 poderia ultrapassar a própria profundidade principal.
        reply_depth=min(settings.puzzle_depth, max(12, settings.puzzle_depth - 6)),
        avoid_gap_cp=settings.avoid_gap_cp,
        search_seconds=settings.puzzle_search_seconds,
        reply_seconds=settings.puzzle_reply_seconds,
    )
