"""Rotas dos estudos: importar, listar, detalhar, editar, exportar e remover."""

import json
import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chess_trainer.api.deps import get_db
from chess_trainer.api.schemas import (
    ChapterCreateIn,
    ChapterDetail,
    ChapterOut,
    ChapterSaveIn,
    QueueIn,
    StudyCreateIn,
    StudyDetail,
    StudyImportIn,
    StudyOut,
    StudyUpdateIn,
)
from chess_trainer.core.models import Puzzle, Study, StudyChapter, utcnow
from chess_trainer.core.studies.parser import parse_study_pgn
from chess_trainer.core.studies.service import (
    STUDY_URL,
    ChapterOrderError,
    StudyImportCancelled,
    StudyNotFound,
    TreeInvalid,
    chapter_detail,
    create_chapter,
    create_study,
    delete_chapter,
    delete_study,
    duplicate_chapter,
    fetch_study_pgn,
    parse_lichess_url,
    save_chapter,
    set_study_queue,
    update_study,
    upsert_study,
)
from chess_trainer.core.studies.tree import chapter_pgn, study_pgn

router = APIRouter(prefix="/api")

ESTUDO_PRIVADO = "estudo privado ou inexistente; exporte o PGN no Lichess e cole aqui"

_NAO_ALFANUMERICO = re.compile(r"[^a-z0-9]+")


def _get_study(db: Session, study_id: str) -> Study:
    study = db.get(Study, study_id)
    if study is None:
        raise HTTPException(404, "estudo não encontrado")
    return study


def _get_chapter(db: Session, study: Study, chapter_id: str) -> StudyChapter:
    chapter = db.get(StudyChapter, chapter_id)
    if chapter is None or chapter.study_id != study.id:
        raise HTTPException(404, "capítulo não encontrado")
    return chapter


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
                    lichess_id=study.lichess_id, origin=study.origin, imported_at=study.imported_at,
                    updated_at=study.updated_at,
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
                                            intro_comment=c.intro_comment, updated_at=c.updated_at)
                                 for c in study.chapters])


def _submit(request: Request, *, lichess_id: str | None, pgn: str, source_url: str,
            title: str = "") -> dict:
    """Põe o job `import_study` na fila: baixa (ou usa o PGN colado) e faz o upsert."""
    app = request.app

    def job(progress):
        db = app.state.session_factory()
        try:
            text = pgn or _download(app, lichess_id)
            parsed = parse_study_pgn(text)
            if title:
                # título escolhido por quem importa vence o que o PGN diz
                parsed.title = title
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
                study, report = upsert_study(db, parsed, source_url, utcnow(), on_chapter=on_chapter)
            except StudyImportCancelled:
                db.rollback()
                progress("import_study", 0, total, "cancelado")
                return
            app.state.coach_index.indexar_estudo(db, study)
            db.commit()
            progress("import_study", total, total, report.message())
        finally:
            db.close()

    if not app.state.jobs.submit("import_study", job):
        raise HTTPException(409, "já existe uma tarefa em andamento")
    return {"queued": True, "job": "import_study"}


def _download(app, lichess_id: str | None) -> str:
    if lichess_id is None:
        # guarda: aqui só se chega quando não há PGN colado, e sem o id não há de
        # onde baixar. As rotas já barram isso antes; o erro é para uma chamada
        # indevida não virar uma URL de download com "None" no meio
        raise RuntimeError("sem id do Lichess nem PGN")
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
    return _submit(request, lichess_id=lichess_id, pgn=pgn, source_url=source_url,
                   title=(body.title or "").strip())


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
def del_study(study_id: str, request: Request, db: Session = Depends(get_db)):
    study = _get_study(db, study_id)
    request.app.state.coach_index.remover_estudo(db, study)
    delete_study(db, study)
    return Response(status_code=204)


# --- editor: estudos e capítulos -----------------------------------------


@router.post("/studies", status_code=201, response_model=StudyOut)
def post_study(body: StudyCreateIn, db: Session = Depends(get_db)):
    return _study_out(db, create_study(db, body.title, body.author))


@router.put("/studies/{study_id}", response_model=StudyOut)
def put_study(study_id: str, body: StudyUpdateIn, request: Request, db: Session = Depends(get_db)):
    study = _get_study(db, study_id)
    try:
        update_study(db, study, body.title, body.author, body.chapter_order)
    except ChapterOrderError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
    # o título do estudo entra no texto indexado de cada trecho: renomear muda o hash
    # do conteúdo e `indexar_estudo` reembute só o que mudou
    request.app.state.coach_index.indexar_estudo(db, study)
    db.commit()
    return _study_out(db, study)


def _chapter_response(dados: dict, status_code: int = 200) -> JSONResponse:
    """Resposta de um capítulo.

    A árvore é montada à parte de propósito: a de um capítulo longo aninha
    centenas de dicionários, bem mais fundo do que o serializador do pydantic
    aceita (ele acusa "circular reference"). O modelo cuida do resto dos campos
    e continua valendo como contrato da rota.
    """
    modelo = ChapterDetail(**dados)
    corpo = json.loads(modelo.model_dump_json(exclude={"tree"}))
    corpo["tree"] = dados["tree"]
    return JSONResponse(corpo, status_code=status_code)


@router.get("/studies/{study_id}/chapters/{chapter_id}", response_model=ChapterDetail)
def get_chapter(study_id: str, chapter_id: str, db: Session = Depends(get_db)):
    chapter = _get_chapter(db, _get_study(db, study_id), chapter_id)
    dados = chapter_detail(chapter)
    # capítulo importado antes do editor ganha a árvore aqui, na primeira abertura
    db.commit()
    return _chapter_response(dados)


def _indexar(request: Request, db: Session, chapter: StudyChapter) -> None:
    """Põe o capítulo no índice do treinador. Sem o modelo de embeddings baixado
    não faz nada: o capítulo só fica marcado como desatualizado."""
    request.app.state.coach_index.indexar_capitulo(db, chapter)
    db.commit()


@router.post("/studies/{study_id}/chapters", status_code=201, response_model=ChapterDetail)
def post_chapter(study_id: str, body: ChapterCreateIn, request: Request, db: Session = Depends(get_db)):
    study = _get_study(db, study_id)
    try:
        chapter = create_chapter(db, study, body.name, body.fen or "",
                                 body.orientation or "white", body.mode or "read")
    except TreeInvalid as exc:
        db.rollback()
        raise HTTPException(422, exc.errors) from exc
    dados = chapter_detail(chapter)
    _indexar(request, db, chapter)
    return _chapter_response(dados, status_code=201)


@router.put("/studies/{study_id}/chapters/{chapter_id}", response_model=ChapterDetail)
def put_chapter(study_id: str, chapter_id: str, body: ChapterSaveIn, request: Request,
                db: Session = Depends(get_db)):
    chapter = _get_chapter(db, _get_study(db, study_id), chapter_id)
    try:
        save_chapter(db, chapter, body.name, body.mode, body.orientation, body.tree)
    except TreeInvalid as exc:
        db.rollback()
        raise HTTPException(422, exc.errors) from exc
    dados = chapter_detail(chapter)
    _indexar(request, db, chapter)
    return _chapter_response(dados)


@router.delete("/studies/{study_id}/chapters/{chapter_id}", status_code=204)
def del_chapter(study_id: str, chapter_id: str, request: Request, db: Session = Depends(get_db)):
    chapter = _get_chapter(db, _get_study(db, study_id), chapter_id)
    request.app.state.coach_index.remover_capitulo(db, chapter.id)
    delete_chapter(db, chapter)
    return Response(status_code=204)


@router.post("/studies/{study_id}/chapters/{chapter_id}/duplicate", status_code=201,
             response_model=ChapterDetail)
def post_duplicate(study_id: str, chapter_id: str, request: Request, db: Session = Depends(get_db)):
    chapter = _get_chapter(db, _get_study(db, study_id), chapter_id)
    copia = duplicate_chapter(db, chapter)
    dados = chapter_detail(copia)
    _indexar(request, db, copia)
    return _chapter_response(dados, status_code=201)


# --- exportação ----------------------------------------------------------


@router.get("/studies/{study_id}/pgn")
def get_study_pgn(study_id: str, db: Session = Depends(get_db)):
    study = _get_study(db, study_id)
    return _pgn_response(study_pgn(study), study.title)


@router.get("/studies/{study_id}/chapters/{chapter_id}/pgn")
def get_chapter_pgn(study_id: str, chapter_id: str, db: Session = Depends(get_db)):
    study = _get_study(db, study_id)
    chapter = _get_chapter(db, study, chapter_id)
    return _pgn_response(chapter_pgn(chapter, study), chapter.name)


def _pgn_response(texto: str, nome: str) -> Response:
    """PGN como download, com um nome de arquivo que qualquer sistema aceita."""
    return Response(content=texto, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{_slug(nome)}.pgn"'})


def _slug(texto: str) -> str:
    """Título vira nome de arquivo: sem acentos, só letras, números e hífens."""
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return _NAO_ALFANUMERICO.sub("-", sem_acento.lower())[:60].strip("-") or "estudo"
