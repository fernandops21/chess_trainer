"""Serviço dos estudos do Lichess: baixar, importar (upsert), fila e remoção.

O parser (`parser.py`) só interpreta texto; aqui o `ParsedStudy` vira linhas de
`studies`, `study_chapters` e `puzzles`. Reimportar é um upsert: capítulos são
reconhecidos pela `lichess_url` (sem URL, pela ordem dentro do estudo), o
exercício de um capítulo é atualizado no lugar — mesmo id, mesmo histórico de
repetição espaçada — e capítulos que sumiram do estudo saem da fila sem serem
apagados.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

import chess
import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from chess_trainer.core.models import Puzzle, Review, Study, StudyChapter, new_id, utcnow
from chess_trainer.core.studies.parser import ParsedChapter, ParsedStudy

STUDY_PGN_URL = "https://lichess.org/api/study/{lichess_id}.pgn"
STUDY_URL = "https://lichess.org/study/{lichess_id}"

# `/study/<id>` com ou sem host e com ou sem o capítulo depois do id
_STUDY_URL_RE = re.compile(r"(?:^|/)study/([A-Za-z0-9]{8})(?:/[A-Za-z0-9]{8})?$")

# limite da lista de capítulos pulados na mensagem final do job
DETALHE_MAX = 300


class StudyNotFound(Exception):
    """O Lichess respondeu 404: estudo privado ou inexistente."""


@dataclass
class ImportReport:
    """O que a importação fez, para a mensagem final do job."""

    chapters: int = 0
    created: int = 0
    updated: int = 0
    skipped: list[str] = field(default_factory=list)

    @property
    def puzzles(self) -> int:
        return self.created + self.updated

    def message(self) -> str:
        texto = f"{self.chapters} capítulos, {self.puzzles} exercícios, {len(self.skipped)} pulados"
        if not self.skipped:
            return texto
        # os pulados vão nomeados na mensagem final para o usuário saber o que rever
        detalhe = "; ".join(self.skipped)
        if len(detalhe) > DETALHE_MAX:
            detalhe = detalhe[: DETALHE_MAX - 1] + "…"
        return f"{texto}: {detalhe}"


# --- URL e download ------------------------------------------------------


def parse_lichess_url(url: str | None) -> str | None:
    """Id do estudo a partir da URL colada pelo usuário; None se não for uma."""
    text = (url or "").strip()
    if not text:
        return None
    text = text.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    match = _STUDY_URL_RE.search(text)
    return match.group(1) if match else None


def fetch_study_pgn(lichess_id: str, http: httpx.Client | None = None) -> str:
    """Baixa o PGN do estudo. 404 (privado ou inexistente) vira `StudyNotFound`."""
    client = http or httpx.Client(follow_redirects=True, timeout=30.0)
    try:
        try:
            resp = client.get(STUDY_PGN_URL.format(lichess_id=lichess_id))
        except httpx.HTTPError as exc:
            raise RuntimeError(f"erro de rede ao baixar o estudo: {exc}") from exc
        if resp.status_code == 404:
            raise StudyNotFound(lichess_id)
        if resp.status_code >= 400:
            raise RuntimeError(f"o Lichess respondeu HTTP {resp.status_code} ao baixar o estudo")
        return resp.text
    finally:
        if http is None:
            client.close()


# --- importação ----------------------------------------------------------


def upsert_study(
    db: Session,
    parsed: ParsedStudy,
    source_url: str = "",
    now: datetime | None = None,
    on_chapter: Callable[[int, int], None] | None = None,
) -> tuple[Study, ImportReport]:
    """Grava (ou atualiza) o estudo interpretado e devolve o estudo e o relatório."""
    now = now or utcnow()
    study = _find_study(db, parsed, source_url)
    if study is None:
        study = Study(id=new_id(), title=parsed.title, author=parsed.author,
                      source_url=source_url or _default_url(parsed), lichess_id=parsed.lichess_id)
        db.add(study)
    else:
        study.title = parsed.title or study.title
        study.author = parsed.author or study.author
        study.source_url = source_url or study.source_url or _default_url(parsed)
        study.lichess_id = study.lichess_id or parsed.lichess_id
    study.imported_at = now
    study.updated_at = now
    db.flush()

    existing = list(db.scalars(select(StudyChapter).where(StudyChapter.study_id == study.id)))
    by_url = {c.lichess_url: c for c in existing if c.lichess_url}
    by_order = {c.order: c for c in existing}

    report = ImportReport(chapters=len(parsed.chapters))
    seen: set[str] = set()
    total = len(parsed.chapters)
    for done, parsed_chapter in enumerate(parsed.chapters, start=1):
        chapter = by_url.get(parsed_chapter.lichess_url) if parsed_chapter.lichess_url else by_order.get(parsed_chapter.order)
        chapter = _upsert_chapter(db, study, chapter, parsed_chapter, report)
        seen.add(chapter.id)
        if on_chapter is not None:
            on_chapter(done, total)

    for chapter in existing:
        if chapter.id not in seen:
            _out_of_queue(db, chapter)

    db.commit()
    db.expire_all()
    return study, report


def _find_study(db: Session, parsed: ParsedStudy, source_url: str) -> Study | None:
    if parsed.lichess_id:
        found = db.scalar(select(Study).where(Study.lichess_id == parsed.lichess_id))
        if found is not None:
            return found
    if source_url:
        return db.scalar(select(Study).where(Study.source_url == source_url))
    return None


def _default_url(parsed: ParsedStudy) -> str:
    return STUDY_URL.format(lichess_id=parsed.lichess_id) if parsed.lichess_id else ""


def _upsert_chapter(db: Session, study: Study, chapter: StudyChapter | None,
                    parsed: ParsedChapter, report: ImportReport) -> StudyChapter:
    if chapter is None:
        chapter = StudyChapter(id=new_id(), study_id=study.id, in_queue=True)
        db.add(chapter)
    # de propósito: um capítulo que já existia mantém o `in_queue` que tinha. Se ele
    # sumiu do estudo e voltou, ou se o usuário o tirou da repetição, a decisão dele
    # continua valendo — quem devolve tudo à fila é o botão "voltar" do estudo
    chapter.order = parsed.order
    chapter.name = parsed.name
    # PGN colado (sem `ChapterURL`) sobre um estudo já baixado: a URL que havia fica
    chapter.lichess_url = parsed.lichess_url or chapter.lichess_url
    chapter.fen = parsed.fen
    chapter.orientation = parsed.orientation
    chapter.mode = parsed.mode
    chapter.pgn = parsed.pgn
    chapter.intro_comment = parsed.intro_comment
    db.flush()

    if parsed.skipped_reason:
        # capítulo que o parser não conseguiu ler: fica registrado como leitura e
        # entra na mensagem final; um exercício antigo dele não é mexido
        report.skipped.append(f"{parsed.order}. {parsed.name}: {parsed.skipped_reason}")
        return chapter
    if parsed.solution is None:
        # virou capítulo de leitura: o exercício de antes sai da fila (nada é apagado)
        _puzzle_out_of_queue(db, chapter)
        return chapter

    _upsert_puzzle(db, chapter, parsed, report)
    return chapter


def _upsert_puzzle(db: Session, chapter: StudyChapter, parsed: ParsedChapter, report: ImportReport) -> None:
    dados = _puzzle_fields(parsed)
    puzzle = db.get(Puzzle, chapter.puzzle_id) if chapter.puzzle_id else None
    if puzzle is not None:
        # atualiza no lugar: id e histórico da repetição espaçada continuam
        for campo, valor in dados.items():
            setattr(puzzle, campo, valor)
        puzzle.chapter_id = chapter.id
        db.flush()
        report.updated += 1
        return

    puzzle = Puzzle(id=new_id(), source="study", in_queue=chapter.in_queue, chapter_id=chapter.id,
                    kind="punish", theme="study", category="study", **dados)
    try:
        # o SAVEPOINT só existe porque o `flush()` de `_upsert_chapter` já abriu a
        # transação (o pysqlite não emite BEGIN sozinho antes do primeiro comando)
        with db.begin_nested():
            db.add(puzzle)
            db.flush()
    except IntegrityError:
        # a única (fen_start, kind, source) impede dois exercícios de estudo com a
        # mesma posição inicial
        gemeo = db.scalar(select(Puzzle).where(Puzzle.fen_start == dados["fen_start"],
                                               Puzzle.kind == "punish", Puzzle.source == "study"))
        if gemeo is None:
            raise
        if gemeo.chapter_id not in (None, chapter.id):
            # o gêmeo é de outro capítulo (deste ou de outro estudo): mexer nele
            # roubaria o exercício e o histórico de quem já é dono, então este
            # capítulo fica sem exercício e a colisão vai para o relatório
            chapter.puzzle_id = None
            db.flush()
            report.skipped.append(f"{chapter.order}. {chapter.name}: posição inicial já usada por outro capítulo")
            return
        # gêmeo sem dono (ou já deste capítulo): o capítulo o adota
        for campo, valor in dados.items():
            setattr(gemeo, campo, valor)
        gemeo.chapter_id = chapter.id
        chapter.puzzle_id = gemeo.id
        db.flush()
        report.updated += 1
        return
    chapter.puzzle_id = puzzle.id
    db.flush()
    report.created += 1


def _puzzle_fields(parsed: ParsedChapter) -> dict:
    solution = parsed.solution or {}
    moves = solution.get("moves", [])
    board = chess.Board(parsed.fen)
    return {
        "fen_start": parsed.fen,
        "side_to_move": "white" if board.turn == chess.WHITE else "black",
        "solution": json.dumps(solution, ensure_ascii=False),
        "solver_moves": sum(1 for m in moves if m.get("by") == "solver"),
        "end_reason": _end_reason(board, moves),
    }


def _end_reason(board: chess.Board, moves: list[dict]) -> str:
    """Reproduz a linha principal: termina em mate ou em ganho de material."""
    board = board.copy()
    for move in moves:
        try:
            board.push_uci(move["uci"])
        except (ValueError, KeyError):
            return "material_gain"
    return "mate" if board.is_checkmate() else "material_gain"


def _out_of_queue(db: Session, chapter: StudyChapter) -> None:
    """Tira da fila o capítulo e o exercício dele. Nada é apagado."""
    chapter.in_queue = False
    _puzzle_out_of_queue(db, chapter)


def _puzzle_out_of_queue(db: Session, chapter: StudyChapter) -> None:
    if chapter.puzzle_id is None:
        return
    puzzle = db.get(Puzzle, chapter.puzzle_id)
    if puzzle is not None:
        puzzle.in_queue = False
    db.flush()


# --- fila e remoção ------------------------------------------------------


def set_study_queue(db: Session, study: Study, in_queue: bool) -> Study:
    """Põe ou tira da repetição espaçada todos os capítulos do estudo."""
    for chapter in study.chapters:
        chapter.in_queue = in_queue
        if chapter.puzzle_id is not None:
            puzzle = db.get(Puzzle, chapter.puzzle_id)
            if puzzle is not None:
                puzzle.in_queue = in_queue
    db.commit()
    db.expire_all()
    return study


def delete_study(db: Session, study: Study) -> None:
    """Apaga o estudo, seus capítulos, os exercícios que ele criou e as revisões
    desses exercícios — e mais nada. Os `delete` são explícitos porque um banco
    migrado pode não ter as cascatas do esquema atual."""
    chapter_ids = list(db.scalars(select(StudyChapter.id).where(StudyChapter.study_id == study.id)))
    puzzle_ids = list(db.scalars(select(Puzzle.id).where(Puzzle.chapter_id.in_(chapter_ids)))) if chapter_ids else []
    if puzzle_ids:
        db.execute(delete(Review).where(Review.puzzle_id.in_(puzzle_ids)))
        # rede de segurança para bancos importados antes da correção da colisão de
        # FEN, onde um capítulo de outro estudo podia apontar para um exercício
        # daqui: a referência é desfeita antes de o exercício sumir
        db.execute(update(StudyChapter).where(StudyChapter.puzzle_id.in_(puzzle_ids)).values(puzzle_id=None))
        db.execute(delete(Puzzle).where(Puzzle.id.in_(puzzle_ids)))
    if chapter_ids:
        db.execute(delete(StudyChapter).where(StudyChapter.id.in_(chapter_ids)))
    db.execute(delete(Study).where(Study.id == study.id))
    db.commit()
    db.expire_all()
