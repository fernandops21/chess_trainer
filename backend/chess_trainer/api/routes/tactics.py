import json
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from chess_trainer.api.deps import get_db
from chess_trainer.api.routes.training import _puzzle_out
from chess_trainer.api.schemas import (
    AttemptIn, AttemptOut, PuzzleOut, TacticOut, TacticsStatusOut, ThemeCountOut, ThemeStatOut,
)
from chess_trainer.config import get_setting, load_settings, set_setting
from chess_trainer.core.models import LichessPuzzle, Puzzle, TrainingSession, utcnow
from chess_trainer.core.stats import theme_stats
from chess_trainer.core.tactics.convert import to_tactic
from chess_trainer.core.tactics.importer import DownloadCancelled, ImportFilter, download_file, import_csv_zst
from chess_trainer.core.tactics.service import (
    pick_next,
    record_attempt,
    refresh_counts_cache,
    tactics_status,
    theme_counts,
)
from chess_trainer.core.tactics.themes import THEME_FILTER_EXCLUDE, THEME_LABELS

router = APIRouter(prefix="/api")


def _csv(value: str | None) -> list[str]:
    return [item for item in (v.strip() for v in (value or "").split(",")) if item]


@router.get("/tactics/status", response_model=TacticsStatusOut)
def get_status(db: Session = Depends(get_db)):
    return tactics_status(db, utcnow())


@router.post("/tactics/import", status_code=202)
def post_import(request: Request):
    app = request.app
    source = app.state.tactics_source
    dest = app.state.tactics_dest

    def job(progress):
        session = app.state.session_factory()
        started = False  # a importação chegou a gravar lotes? só então o cache precisa mudar
        try:
            s = load_settings(session)
            path = Path(source)
            if not path.is_file():
                path = download_file(str(source), Path(dest), progress, should_stop=app.state.jobs.should_stop)
            flt = ImportFilter(min_plays=s.lichess_min_plays, min_popularity=s.lichess_min_popularity)
            started = True
            stats = import_csv_zst(session, path, flt, progress, should_stop=app.state.jobs.should_stop)
            if not stats.cancelled:
                set_setting(session, "lichess_imported_at", utcnow().isoformat())
                set_setting(session, "lichess_source_rows", stats.rows_read)
            progress("import", stats.rows_read, stats.rows_read,
                     f"{stats.imported} táticas novas de {stats.rows_read} linhas" + (" (cancelado)" if stats.cancelled else ""))
        except DownloadCancelled:
            # cancelar não é erro: o JobRunner encerra em "idle" com a mensagem "cancelado"
            progress("download", 0, 0, "download cancelado")
            return
        finally:
            # total e temas ficam em cache: contar milhões de linhas a cada tela de status é caro.
            # Cancelada ou interrompida por erro, a importação já gravou lotes: o cache tem de
            # acompanhar, senão o status fica mentindo até a próxima importação completa.
            if started:
                try:
                    session.rollback()  # descarta o lote pela metade se a importação caiu no meio
                    refresh_counts_cache(session)
                except Exception:  # noqa: BLE001 - não mascarar o erro original da importação
                    pass
            session.close()

    if not app.state.jobs.submit("import_lichess", job):
        raise HTTPException(409, "já existe uma tarefa em andamento")
    return {"queued": True, "job": "import_lichess"}


@router.get("/tactics/next", response_model=TacticOut)
def get_next(themes: str | None = None, exclude: str | None = None, db: Session = Depends(get_db)):
    # checagem barata: um COUNT(*) na tabela de milhões de táticas custaria caro por requisição
    if db.scalar(select(LichessPuzzle.id).limit(1)) is None:
        raise HTTPException(404, "banco de táticas não importado; baixe em Configurações")
    settings = load_settings(db)
    skip = _csv(exclude)
    last: ValueError | None = None
    # uma linha corrompida no banco do Lichess (lance ilegal) não pode derrubar a sessão:
    # exclui a que veio e sorteia de novo, poucas vezes, antes de desistir
    for _ in range(3):
        row = pick_next(db, settings, utcnow(), themes=_csv(themes), exclude=skip)
        if row is None:
            raise HTTPException(404, "nenhuma tática disponível com esses filtros")
        try:
            tactic = asdict(to_tactic(row))
        except ValueError as exc:
            last = exc
            skip = [*skip, row.id]
            continue
        tactic["saved"] = _is_saved(db, row.id, tactic["fen_start"])
        return tactic
    raise HTTPException(500, str(last)) from last


def _is_saved(db: Session, lichess_id: str, fen_start: str) -> bool:
    """A tática já virou exercício da repetição e continua na fila?

    A gêmea conta: duas táticas que transpõem para a mesma posição inicial
    dividem um único exercício (a única (fen_start, kind, source)), então
    guardar uma guarda a outra — e a tela precisa dizer isso."""
    return db.scalar(
        select(Puzzle.id).where(
            Puzzle.in_queue.is_(True), Puzzle.source == "lichess",
            (Puzzle.external_id == lichess_id) | (Puzzle.fen_start == fen_start),
        )
    ) is not None


@router.post("/tactics/{lichess_id}/save", response_model=PuzzleOut)
def post_save_tactic(lichess_id: str, response: Response, db: Session = Depends(get_db)):
    """Guarda a tática do Lichess como exercício da repetição espaçada.

    Idempotente: se já foi guardada devolve a mesma (200), trazendo-a de volta
    à fila se estava fora; nada é apagado nem recriado."""
    row = db.get(LichessPuzzle, lichess_id)
    if row is None:
        raise HTTPException(404, "tática não encontrada")
    existing = db.scalar(select(Puzzle).where(Puzzle.external_id == lichess_id))
    if existing is not None:
        return _back_to_queue(db, existing)
    try:
        t = to_tactic(row)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    # `kind="punish"` por compatibilidade da interface: o solucionador é o lado
    # a mover na posição inicial, como nos puzzles de punir os erros do adversário
    puzzle = Puzzle(
        source="lichess", in_queue=True, external_id=lichess_id, kind="punish",
        fen_start=t.fen_start, side_to_move=t.side_to_move, solution=json.dumps(t.solution),
        end_reason=t.end_reason, theme=t.theme, category="lichess", solver_moves=t.solver_moves,
        fen_before=row.fen, last_move=row.moves.split()[0],
    )
    db.add(puzzle)
    try:
        db.commit()
    except IntegrityError:
        # duas táticas diferentes do Lichess com a mesma posição inicial: a única
        # (fen_start, kind, source) barra a segunda; devolve a que já está guardada
        db.rollback()
        twin = db.scalar(select(Puzzle).where(Puzzle.fen_start == t.fen_start, Puzzle.kind == "punish",
                                              Puzzle.source == "lichess"))
        if twin is None:
            raise
        return _back_to_queue(db, twin)
    response.status_code = 201
    return _puzzle_out(db, puzzle)


def _back_to_queue(db: Session, puzzle: Puzzle) -> PuzzleOut:
    if not puzzle.in_queue:
        puzzle.in_queue = True
        db.commit()
    return _puzzle_out(db, puzzle)


@router.post("/tactics/attempts", response_model=AttemptOut, status_code=201)
def post_attempt(body: AttemptIn, db: Session = Depends(get_db)):
    if body.session_id is not None and db.get(TrainingSession, body.session_id) is None:
        raise HTTPException(404, "sessão não encontrada")
    try:
        a = record_attempt(db, body.puzzle_id, correct=body.correct, used_hint=body.used_hint,
                           duration_ms=body.duration_ms, session_id=body.session_id, now=utcnow(), settings=load_settings(db))
    except KeyError as exc:
        raise HTTPException(404, "tática não encontrada") from exc
    return AttemptOut(id=a.id, puzzle_id=a.puzzle_id, correct=a.correct, used_hint=a.used_hint,
                      rating_before=a.rating_before, rating_after=a.rating_after,
                      delta=a.rating_after - a.rating_before, puzzle_rating=a.puzzle_rating)


@router.get("/tactics/themes", response_model=list[ThemeCountOut])
def get_themes(request: Request, db: Session = Depends(get_db)):
    jobs = request.app.state.jobs
    # sem cache e com a importação em curso, o GROUP BY varreria uma tabela de milhões de
    # linhas que ainda está crescendo; a lista chega quando a importação termina
    if get_setting(db, "lichess_theme_counts") is None and jobs.is_busy and jobs.status.job == "import_lichess":
        return []
    return [ThemeCountOut(theme=t, label=THEME_LABELS.get(t, t), count=n)
            for t, n in theme_counts(db) if t not in THEME_FILTER_EXCLUDE]


@router.get("/stats/themes", response_model=list[ThemeStatOut])
def get_theme_stats(days: int = Query(30, ge=1, le=3650), db: Session = Depends(get_db)):
    return theme_stats(db, since=utcnow() - timedelta(days=days))
