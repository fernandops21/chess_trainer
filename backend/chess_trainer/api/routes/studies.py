"""Rotas dos estudos do Lichess: importar, listar, detalhar, fila e remover."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chess_trainer.api.deps import get_db
from chess_trainer.api.schemas import ChapterOut, QueueIn, StudyDetail, StudyImportIn, StudyOut
from chess_trainer.core.models import Puzzle, Study, StudyChapter, utcnow
from chess_trainer.core.studies.parser import parse_study_pgn
from chess_trainer.core.studies.service import (
    STUDY_URL,
    StudyImportCancelled,
    StudyNotFound,
    delete_study,
    fetch_study_pgn,
    parse_lichess_url,
    set_study_queue,
    upsert_study,
)

router = APIRouter(prefix="/api")

ESTUDO_PRIVADO = "estudo privado ou inexistente; exporte o PGN no Lichess e cole aqui"


def _get_study(db: Session, study_id: str) -> Study:
    study = db.get(Study, study_id)
    if study is None:
        raise HTTPException(404, "estudo não encontrado")
    return study


def _counts(db: Session, study: Study) -> tuple[int, int, int, int]:
    """Capítulos, capítulos com exercício, exercícios na repetição e vencidos hoje.

    As duas últimas saem dos exercícios com os mesmos filtros da fila
    (`core/srs/queue.py`), para bater com o que `/api/queue?study_id=` serve.
    `exercise_count` é diferente: conta os capítulos que têm exercício, estejam
    eles na repetição ou não — é o que diz se há algo para devolver à fila."""
    chapters = list(study.chapters)
    do_estudo = select(StudyChapter.id).where(StudyChapter.study_id == study.id)
    na_fila = select(func.count(Puzzle.id)).where(
        Puzzle.chapter_id.in_(do_estudo),
        Puzzle.in_queue.is_(True),
        Puzzle.is_leech.is_(False),
    )
    in_queue = db.scalar(na_fila)
    due = db.scalar(na_fila.where(Puzzle.srs_due_at <= utcnow()))
    com_exercicio = sum(1 for c in chapters if c.puzzle_id is not None)
    return len(chapters), com_exercicio, int(in_queue or 0), int(due or 0)


def _study_out(db: Session, study: Study) -> StudyOut:
    chapters, exercises, in_queue, due = _counts(db, study)
    return StudyOut(id=study.id, title=study.title, author=study.author, source_url=study.source_url,
                    lichess_id=study.lichess_id, imported_at=study.imported_at,
                    chapter_count=chapters, exercise_count=exercises, in_queue=in_queue, due_today=due)


@router.get("/studies", response_model=list[StudyOut])
def get_studies(db: Session = Depends(get_db)):
    studies = db.scalars(select(Study).order_by(Study.created_at)).all()
    return [_study_out(db, s) for s in studies]


@router.get("/studies/{study_id}", response_model=StudyDetail)
def get_study(study_id: str, db: Session = Depends(get_db)):
    study = _get_study(db, study_id)
    base = _study_out(db, study)
    return StudyDetail(**base.model_dump(),
                       chapters=[ChapterOut(id=c.id, order=c.order, name=c.name, lichess_url=c.lichess_url,
                                            mode=c.mode, in_queue=c.in_queue, puzzle_id=c.puzzle_id,
                                            intro_comment=c.intro_comment)
                                 for c in study.chapters])


def _submit(request: Request, *, lichess_id: str | None, pgn: str, source_url: str) -> dict:
    """Põe o job `import_study` na fila: baixa (ou usa o PGN colado) e faz o upsert."""
    app = request.app

    def job(progress):
        db = app.state.session_factory()
        try:
            text = pgn or _download(app, lichess_id)
            parsed = parse_study_pgn(text)
            if not parsed.chapters:
                raise RuntimeError("o PGN não tem nenhum capítulo")
            total = len(parsed.chapters)
            progress("import_study", 0, total, f"0/{total} capítulos")

            def on_chapter(done: int, tot: int) -> None:
                # o cancelamento é checado aqui, capítulo a capítulo, e ainda dentro da
                # transação de `upsert_study`: cancelar deixa o estudo inteiro de fora,
                # nunca metade dos capítulos gravados
                if app.state.jobs.should_stop():
                    raise StudyImportCancelled
                progress("import_study", done, tot, f"{done}/{tot} capítulos")

            try:
                _, report = upsert_study(db, parsed, source_url, utcnow(), on_chapter=on_chapter)
            except StudyImportCancelled:
                db.rollback()
                progress("import_study", 0, total, "cancelado")
                return
            progress("import_study", total, total, report.message())
        finally:
            db.close()

    if not app.state.jobs.submit("import_study", job):
        raise HTTPException(409, "já existe uma tarefa em andamento")
    return {"queued": True, "job": "import_study"}


def _download(app, lichess_id: str | None) -> str:
    http = app.state.study_http_factory()
    try:
        return fetch_study_pgn(lichess_id, http)
    except StudyNotFound as exc:
        raise RuntimeError(ESTUDO_PRIVADO) from exc
    finally:
        http.close()


@router.post("/studies/import", status_code=202)
def post_import(body: StudyImportIn, request: Request):
    pgn = (body.pgn or "").strip()
    url = (body.url or "").strip()
    if not pgn and not url:
        raise HTTPException(400, "informe a URL do estudo ou o PGN")
    lichess_id = parse_lichess_url(url) if url else None
    if url and lichess_id is None:
        raise HTTPException(400, "URL de estudo inválida")
    source_url = STUDY_URL.format(lichess_id=lichess_id) if lichess_id else ""
    return _submit(request, lichess_id=lichess_id, pgn=pgn, source_url=source_url)


@router.post("/studies/{study_id}/reimport", status_code=202)
def post_reimport(study_id: str, request: Request, db: Session = Depends(get_db)):
    study = _get_study(db, study_id)
    if not study.lichess_id:
        raise HTTPException(400, "este estudo não veio do Lichess; importe de novo colando o PGN")
    return _submit(request, lichess_id=study.lichess_id, pgn="",
                   source_url=study.source_url or STUDY_URL.format(lichess_id=study.lichess_id))


@router.post("/studies/{study_id}/queue", response_model=StudyOut)
def post_queue(study_id: str, body: QueueIn, db: Session = Depends(get_db)):
    study = set_study_queue(db, _get_study(db, study_id), body.in_queue)
    return _study_out(db, study)


@router.delete("/studies/{study_id}", status_code=204)
def del_study(study_id: str, db: Session = Depends(get_db)):
    delete_study(db, _get_study(db, study_id))
    return Response(status_code=204)
