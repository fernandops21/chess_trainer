import io
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import chess.pgn
from sqlalchemy import select
from sqlalchemy.orm import Session

from chess_trainer.config import AppSettings, get_setting, set_setting
from chess_trainer.core.importers.chesscom import ChessComClient
from chess_trainer.core.models import Game

ProgressFn = Callable[[str, int, int, str], None]
LAST_ARCHIVE_KEY = "last_imported_archive"


@dataclass
class ParsedGame:
    source_id: str
    pgn: str
    white: str
    black: str
    result: str
    time_control: str
    category: str
    played_at: datetime
    my_color: str


@dataclass
class ImportResult:
    imported: int = 0
    skipped: int = 0
    filtered: int = 0
    months: int = 0


def parse_game(raw: dict, username: str) -> ParsedGame | None:
    if raw.get("rules", "chess") != "chess":
        return None
    white = raw["white"]["username"]
    black = raw["black"]["username"]
    headers = chess.pgn.read_headers(io.StringIO(raw["pgn"])) or {}
    result = headers.get("Result", "*")
    played_at = datetime.fromtimestamp(int(raw["end_time"]), tz=timezone.utc).replace(tzinfo=None)
    my_color = "white" if white.lower() == username.lower() else "black"
    return ParsedGame(
        source_id=raw["url"],
        pgn=raw["pgn"],
        white=white,
        black=black,
        result=result,
        time_control=str(raw.get("time_control", "")),
        category=raw.get("time_class", "rapid"),
        played_at=played_at,
        my_color=my_color,
    )


def _month_label(archive_url: str) -> str:
    parts = archive_url.rstrip("/").rsplit("/", 2)
    return f"{parts[-2]}/{parts[-1]}"


def import_games(
    db: Session,
    client: ChessComClient,
    settings: AppSettings,
    progress: ProgressFn | None = None,
) -> ImportResult:
    username = settings.chesscom_username.strip().lower()
    if not username:
        raise ValueError("configure o usuário do chess.com antes de importar")

    archives = client.list_archives(username)
    last = get_setting(db, LAST_ARCHIVE_KEY)
    start = archives.index(last) if last in archives else 0
    pending = archives[start:]

    result = ImportResult()
    for i, archive_url in enumerate(pending):
        if progress:
            progress("import", i, len(pending), _month_label(archive_url))
        set_setting(db, LAST_ARCHIVE_KEY, archive_url)  # ponto de retomada, gravado antes de buscar
        raw_games = client.fetch_month(archive_url)
        for raw in raw_games:
            parsed = parse_game(raw, username)
            if parsed is None or parsed.category not in settings.categories:
                result.filtered += 1
                continue
            exists = db.scalar(select(Game.id).where(Game.source_id == parsed.source_id))
            if exists:
                result.skipped += 1
                continue
            db.add(Game(**parsed.__dict__))
            result.imported += 1
        db.commit()
        result.months += 1
    if progress:
        progress("import", len(pending), len(pending), "concluído")
    return result
