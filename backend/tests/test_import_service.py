import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from chess_trainer.config import AppSettings, get_setting
from chess_trainer.core.importers.chesscom import ChessComClient, ChessComError
from chess_trainer.core.importers.service import import_games, parse_game
from chess_trainer.core.models import Game

FIXTURES = Path(__file__).parent / "fixtures"
MONTH = json.loads((FIXTURES / "chesscom_month.json").read_text())["games"]
ARCHIVES = json.loads((FIXTURES / "chesscom_archives.json").read_text())


def _client(month_by_suffix: dict[str, list[dict]], calls: list[str] | None = None):
    def handler(request: httpx.Request):
        if calls is not None:
            calls.append(str(request.url))
        if request.url.path.endswith("/games/archives"):
            return httpx.Response(200, json=ARCHIVES)
        for suffix, games in month_by_suffix.items():
            if request.url.path.endswith(suffix):
                return httpx.Response(200, json={"games": games})
        return httpx.Response(500)

    return ChessComClient("t", http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_parse_game_white_and_black():
    g = parse_game(MONTH[0], "therealzibs")
    assert g.source_id == "https://www.chess.com/game/live/1001"
    assert g.my_color == "white" and g.result == "1-0" and g.category == "rapid"
    assert g.played_at == datetime(2026, 8, 2, 12, 0)
    g2 = parse_game(MONTH[1], "therealzibs")
    assert g2.my_color == "black" and g2.result == "0-1" and g2.category == "blitz"


def test_parse_game_skips_variants():
    assert parse_game(MONTH[2], "therealzibs") is None


def test_import_filters_categories_and_dedups(db_session):
    settings = AppSettings(chesscom_username="therealzibs")  # rapid/daily/classical
    client = _client({"/2026/07": [], "/2026/08": MONTH})
    result = import_games(db_session, client, settings)
    assert (result.imported, result.filtered, result.skipped, result.months) == (1, 2, 0, 2)
    games = db_session.scalars(select(Game)).all()
    assert [g.source_id for g in games] == ["https://www.chess.com/game/live/1001"]
    assert get_setting(db_session, "last_imported_archive").endswith("/2026/08")

    again = import_games(db_session, client, settings)
    assert (again.imported, again.skipped, again.months) == (0, 1, 1)  # retoma do último mês


def test_import_with_blitz_enabled(db_session):
    settings = AppSettings(chesscom_username="therealzibs", categories=["rapid", "blitz"])
    result = import_games(db_session, _client({"/2026/07": [], "/2026/08": MONTH}), settings)
    assert result.imported == 2


def test_import_resumes_from_last_archive(db_session):
    settings = AppSettings(chesscom_username="therealzibs")
    calls: list[str] = []
    import_games(db_session, _client({"/2026/07": [], "/2026/08": MONTH}, calls), settings)
    calls.clear()
    import_games(db_session, _client({"/2026/07": [], "/2026/08": MONTH}, calls), settings)
    assert not any(c.endswith("/2026/07") for c in calls)


def test_import_reports_progress_and_propagates_errors(db_session):
    settings = AppSettings(chesscom_username="therealzibs")
    events = []
    client = _client({"/2026/07": []})  # /2026/08 devolve 500
    with pytest.raises(ChessComError):
        import_games(db_session, client, settings, progress=lambda *a: events.append(a))
    assert events[0][0] == "import" and events[0][2] == 2
    # o mês que falhou fica como próximo ponto de retomada
    assert get_setting(db_session, "last_imported_archive").endswith("/2026/08")


def test_import_requires_username(db_session):
    with pytest.raises(ValueError):
        import_games(db_session, _client({}), AppSettings(chesscom_username=""))
