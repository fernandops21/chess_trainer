"""Importa o banco de puzzles do Lichess (CSV comprimido com zstd) em streaming."""
import csv
import io
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import zstandard
from sqlalchemy import insert
from sqlalchemy.orm import Session

from chess_trainer.core.models import LichessPuzzle, LichessPuzzleTheme

LICHESS_PUZZLE_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"
COLUMNS = ["PuzzleId", "FEN", "Moves", "Rating", "RatingDeviation", "Popularity", "NbPlays", "Themes", "GameUrl", "OpeningTags"]
ProgressFn = Callable[[str, int, int, str], None]
StopFn = Callable[[], bool]


class DownloadCancelled(RuntimeError):
    """Download interrompido a pedido do usuário: não é erro, é cancelamento."""


@dataclass(frozen=True)
class ImportFilter:
    min_plays: int
    min_popularity: int
    min_rating: int = 400
    max_rating: int = 3000

    def accepts(self, row: dict) -> bool:
        return (row["nb_plays"] >= self.min_plays and row["popularity"] >= self.min_popularity
                and self.min_rating <= row["rating"] <= self.max_rating)


@dataclass
class ImportStats:
    rows_read: int = 0
    imported: int = 0
    skipped: int = 0
    malformed: int = 0
    cancelled: bool = False


def parse_rows(lines: Iterable[str], on_malformed: Callable[[], None] | None = None) -> Iterator[dict]:
    """Linhas de texto do CSV → dicts com os tipos certos. A primeira linha é o cabeçalho.
    `on_malformed`, se dado, é chamado para cada linha corrompida (que é descartada)."""
    reader = csv.DictReader(lines)
    for raw in reader:
        try:
            yield {
                "id": raw["PuzzleId"], "fen": raw["FEN"], "moves": raw["Moves"],
                "rating": int(raw["Rating"]), "rating_deviation": int(raw["RatingDeviation"]),
                "popularity": int(raw["Popularity"]), "nb_plays": int(raw["NbPlays"]),
                "themes": raw["Themes"] or "", "opening_tags": raw.get("OpeningTags") or "",
            }
        except (KeyError, ValueError, TypeError):
            if on_malformed is not None:
                on_malformed()
            continue  # linha corrompida: pula sem derrubar a importação


def _open_zst_text(path: Path) -> io.TextIOWrapper:
    fh = open(path, "rb")
    reader = zstandard.ZstdDecompressor().stream_reader(fh)
    # errors="replace": um byte inválido isolado não pode derrubar uma importação de 300 MB
    return io.TextIOWrapper(reader, encoding="utf-8", newline="", errors="replace")


def import_csv_zst(db: Session, path: Path, flt: ImportFilter, progress: ProgressFn,
                   should_stop: StopFn | None = None, batch_size: int = 5000) -> ImportStats:
    stats = ImportStats()
    batch: list[dict] = []
    themes: list[dict] = []

    def flush() -> int:
        if not batch:
            return 0
        # INSERT OR IGNORE: rodar de novo completa o que faltou sem duplicar.
        # rowcount da inserção é exato sob OR IGNORE (via a tabela Core, não o ORM).
        res = db.execute(insert(LichessPuzzle.__table__).prefix_with("OR IGNORE"), batch)
        if themes:  # lista vazia faria um INSERT sem linhas e geraria SAWarning
            db.execute(insert(LichessPuzzleTheme.__table__).prefix_with("OR IGNORE"), themes)
        db.commit()
        batch.clear()
        themes.clear()
        return res.rowcount

    def on_malformed() -> None:
        stats.malformed += 1

    with _open_zst_text(path) as text:
        for row in parse_rows(text, on_malformed):
            stats.rows_read += 1
            if flt.accepts(row):
                batch.append(row)
                themes.extend({"theme": t, "puzzle_id": row["id"]} for t in row["themes"].split())
            else:
                stats.skipped += 1
            # tica também por linhas lidas: com um filtro restritivo, o lote de aceitos
            # pode nunca encher, e sem isso o progress()/should_stop() nunca rodariam
            if stats.rows_read % batch_size == 0 or len(batch) >= batch_size:
                stats.imported += flush()
                progress("import", stats.rows_read, 0, f"{stats.rows_read:,} linhas lidas · {stats.imported:,} táticas novas".replace(",", "."))
                if should_stop is not None and should_stop():
                    stats.cancelled = True  # o que já foi commitado no flush acima permanece
                    return stats
    stats.imported += flush()
    progress("import", stats.rows_read, 0, f"{stats.rows_read:,} linhas lidas · {stats.imported:,} táticas novas".replace(",", "."))
    return stats


def download_file(url: str, dest: Path, progress: ProgressFn, should_stop: StopFn | None = None,
                  http: httpx.Client | None = None) -> Path:
    """Baixa `url` para `dest` em streaming (via `.part`), pulando se o arquivo já tem o tamanho remoto."""
    client = http or httpx.Client(follow_redirects=True, timeout=httpx.Timeout(30.0, read=120.0))
    try:
        head = client.head(url, follow_redirects=True)
        remote_size = int(head.headers.get("content-length", "0") or 0)
        if dest.exists() and remote_size and dest.stat().st_size == remote_size:
            progress("download", remote_size, remote_size, "arquivo já baixado")
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        done = 0
        with client.stream("GET", url, follow_redirects=True) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", "0") or 0) or remote_size
            with open(part, "wb") as out:
                for chunk in resp.iter_bytes(1 << 20):
                    out.write(chunk)
                    done += len(chunk)
                    progress("download", done, total, f"{done / 2**20:.0f} MB baixados")
                    if should_stop is not None and should_stop():
                        raise DownloadCancelled("download cancelado")
        part.replace(dest)
        return dest
    finally:
        if http is None:
            client.close()


def write_csv_zst(path: Path, rows: list[dict]) -> None:
    """Escreve um CSV no formato do Lichess comprimido com zstd (fixtures e testes)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(zstandard.ZstdCompressor().compress(buf.getvalue().encode("utf-8")))
