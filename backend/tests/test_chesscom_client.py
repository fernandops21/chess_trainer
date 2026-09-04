import json
from pathlib import Path

import httpx
import pytest

from chess_trainer.core.importers.chesscom import ChessComClient, ChessComError

FIXTURES = Path(__file__).parent / "fixtures"


def _client(handler):
    transport = httpx.MockTransport(handler)
    return ChessComClient("chess-trainer-tests", http=httpx.Client(transport=transport))


def _ok_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["user-agent"] == "chess-trainer-tests"
    if request.url.path.endswith("/games/archives"):
        return httpx.Response(200, json=json.loads((FIXTURES / "chesscom_archives.json").read_text()))
    if request.url.path.endswith("/games/2026/08"):
        return httpx.Response(200, json=json.loads((FIXTURES / "chesscom_month.json").read_text()))
    return httpx.Response(404, json={"message": "not found"})


def test_list_archives_uses_lowercase_username():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return _ok_handler(request)

    archives = _client(handler).list_archives("TheRealZibs")
    assert seen == ["https://api.chess.com/pub/player/therealzibs/games/archives"]
    assert archives[-1].endswith("/2026/08")


def test_fetch_month_returns_raw_games():
    games = _client(_ok_handler).fetch_month("https://api.chess.com/pub/player/therealzibs/games/2026/08")
    assert [g["url"].rsplit("/", 1)[1] for g in games] == ["1001", "1002", "1003"]
    assert games[0]["time_class"] == "rapid"


def test_404_raises_user_not_found():
    with pytest.raises(ChessComError, match="não encontrado"):
        _client(lambda r: httpx.Response(404, json={})).list_archives("nobody")


def test_429_raises_rate_limited():
    with pytest.raises(ChessComError, match="limite"):
        _client(lambda r: httpx.Response(429)).list_archives("x")


def test_network_error_is_wrapped():
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(ChessComError, match="rede"):
        _client(handler).list_archives("x")
