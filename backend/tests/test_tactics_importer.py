import csv
import io
from pathlib import Path

import httpx
import pytest
import zstandard
from sqlalchemy import func, select

from chess_trainer.core.models import LichessPuzzle, LichessPuzzleTheme
from chess_trainer.core.tactics.importer import (
    COLUMNS,
    DownloadCancelled,
    ImportFilter,
    download_file,
    import_csv_zst,
    write_csv_zst,
)

ROWS = [
    {"PuzzleId": "00sHx", "FEN": "q3k1nr/1pp1nQpp/3p4/1P2p3/4P3/B1PP1b2/B5PP/5K2 b k - 0 17", "Moves": "e8d7 a2e6 d7d8 f7f8",
     "Rating": "1760", "RatingDeviation": "80", "Popularity": "83", "NbPlays": "720", "Themes": "mate mateIn2 middlegame short",
     "GameUrl": "https://lichess.org/yyznGmXs/black#34", "OpeningTags": ""},
    {"PuzzleId": "00sJ9", "FEN": "r3r1k1/p4ppp/2p2n2/1p6/3P1qb1/2NQR3/PPB2PP1/R1B3K1 w - - 5 18", "Moves": "e3g3 e8e1 g1h2 e1c1 a1c1 f4h6 h2g1 h6c1",
     "Rating": "2671", "RatingDeviation": "105", "Popularity": "87", "NbPlays": "325", "Themes": "advantage attraction fork middlegame sacrifice veryLong",
     "GameUrl": "https://lichess.org/gyFeQsOE#35", "OpeningTags": "Kings_Pawn_Game Kings_Pawn_Game_Leonardis_Variation"},
    {"PuzzleId": "unpop", "FEN": "8/8/8/8/8/8/8/K6k w - - 0 1", "Moves": "a1a2 h1h2", "Rating": "1500", "RatingDeviation": "80",
     "Popularity": "10", "NbPlays": "900", "Themes": "endgame", "GameUrl": "", "OpeningTags": ""},
    {"PuzzleId": "rare", "FEN": "8/8/8/8/8/8/8/K6k w - - 0 1", "Moves": "a1a2 h1h2", "Rating": "1500", "RatingDeviation": "80",
     "Popularity": "95", "NbPlays": "12", "Themes": "endgame", "GameUrl": "", "OpeningTags": ""},
    {"PuzzleId": "tooHi", "FEN": "8/8/8/8/8/8/8/K6k w - - 0 1", "Moves": "a1a2 h1h2", "Rating": "3100", "RatingDeviation": "80",
     "Popularity": "95", "NbPlays": "900", "Themes": "endgame", "GameUrl": "", "OpeningTags": ""},
]
FLT = ImportFilter(min_plays=200, min_popularity=60)


@pytest.fixture
def csv_zst(tmp_path: Path) -> Path:
    path = tmp_path / "puzzles.csv.zst"
    write_csv_zst(path, ROWS)
    return path


def test_import_filters_and_indexes_themes(db_session, csv_zst):
    calls = []
    stats = import_csv_zst(db_session, csv_zst, FLT, lambda *a: calls.append(a), batch_size=2)
    assert (stats.rows_read, stats.imported, stats.skipped, stats.cancelled) == (5, 2, 3, False)
    assert db_session.scalar(select(func.count(LichessPuzzle.id))) == 2
    themes = set(db_session.scalars(select(LichessPuzzleTheme.theme).where(LichessPuzzleTheme.puzzle_id == "00sJ9")))
    assert themes == {"advantage", "attraction", "fork", "middlegame", "sacrifice", "veryLong"}
    assert db_session.get(LichessPuzzle, "00sJ9").opening_tags == "Kings_Pawn_Game Kings_Pawn_Game_Leonardis_Variation"
    assert calls and calls[-1][0] == "import" and calls[-1][1] == 5


def test_import_is_idempotent(db_session, csv_zst):
    import_csv_zst(db_session, csv_zst, FLT, lambda *a: None)
    again = import_csv_zst(db_session, csv_zst, FLT, lambda *a: None)
    assert again.imported == 0 and db_session.scalar(select(func.count(LichessPuzzle.id))) == 2
    assert db_session.scalar(select(func.count()).select_from(LichessPuzzleTheme)) == 10


def test_import_stops_between_batches(db_session, csv_zst):
    stats = import_csv_zst(db_session, csv_zst, FLT, lambda *a: None, should_stop=lambda: True, batch_size=1)
    assert stats.cancelled is True and stats.rows_read <= 2


def test_cancel_keeps_committed_rows(db_session, csv_zst):
    # should_stop segue False na 1ª chamada e True nas seguintes: o cancelamento
    # acontece depois de pelo menos um flush, e esse trabalho já commitado deve
    # permanecer no banco.
    calls = {"n": 0}

    def should_stop() -> bool:
        calls["n"] += 1
        return calls["n"] > 1

    stats = import_csv_zst(db_session, csv_zst, FLT, lambda *a: None, should_stop=should_stop, batch_size=1)
    assert stats.cancelled is True
    ids = set(db_session.scalars(select(LichessPuzzle.id)))
    assert ids and ids == {"00sHx", "00sJ9"}


def test_download_streams_and_reports_progress(tmp_path: Path):
    payload = b"x" * 10_000
    seen = []

    def handler(request: httpx.Request):
        return httpx.Response(200, content=payload, headers={"content-length": str(len(payload))})

    dest = tmp_path / "db.csv.zst"
    out = download_file("https://example.test/db.zst", dest, lambda *a: seen.append(a),
                        http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert out == dest and dest.read_bytes() == payload and not (tmp_path / "db.csv.zst.part").exists()
    assert seen[-1][0] == "download" and seen[-1][1] == len(payload) == seen[-1][2]


def test_download_skips_when_size_matches(tmp_path: Path):
    dest = tmp_path / "db.csv.zst"
    dest.write_bytes(b"abc")

    def handler(request: httpx.Request):
        if request.method == "HEAD":
            return httpx.Response(200, headers={"content-length": "3"})
        raise AssertionError("não deveria baixar de novo")

    download_file("https://example.test/db.zst", dest, lambda *a: None,
                  http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert dest.read_bytes() == b"abc"


def test_download_cancel_raises_download_cancelled(tmp_path: Path):
    # cancelar não é falha: o job precisa distinguir isso de um erro de rede
    payload = b"x" * (2 * 2**20)

    def handler(request: httpx.Request):
        return httpx.Response(200, content=payload, headers={"content-length": str(len(payload))})

    dest = tmp_path / "db.csv.zst"
    with pytest.raises(DownloadCancelled):
        download_file("https://example.test/db.zst", dest, lambda *a: None, should_stop=lambda: True,
                      http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert not dest.exists()
    # o parcial também some: cancelar não pode deixar lixo em disco
    assert not dest.with_name(dest.name + ".part").exists()


def test_import_survives_csv_error_in_the_middle(db_session, tmp_path: Path):
    # aspas abertas e nunca fechadas: o leitor engole o resto da linha até estourar o
    # limite de tamanho de campo e levanta csv.Error. Escrito na mão porque o
    # write_csv_zst escaparia as aspas. As linhas seguintes têm de continuar entrando.
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerow(ROWS[0])
    buf.write('quebrada,8/8/8/8/8/8/8/K6k w - - 0 1,a1a2 h1h2,1500,80,95,900,"' + "x" * 200_000 + "\n")
    writer.writerow(ROWS[1])
    path = tmp_path / "quebrado.csv.zst"
    path.write_bytes(zstandard.ZstdCompressor().compress(buf.getvalue().encode("utf-8")))

    stats = import_csv_zst(db_session, path, FLT, lambda *a: None)
    assert stats.malformed >= 1
    # a linha depois da corrompida continua sendo importada
    assert set(db_session.scalars(select(LichessPuzzle.id))) == {"00sHx", "00sJ9"}
