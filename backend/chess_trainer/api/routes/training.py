import json
from collections.abc import Sequence
from datetime import timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from chess_trainer.api.deps import get_db
from chess_trainer.api.schemas import (
    DashboardOut, GameRef, MistakeRef, MyReplyInfo, PuzzleOut, PuzzleSibling, QueueIn, QueueOut, ReviewIn,
    ReviewOut, SessionIn, SessionOut, SourceCount, SrsOut, StudyRef,
)
from chess_trainer.config import get_setting, load_settings
from chess_trainer.core.models import Game, Position, Puzzle, Review, TrainingSession, utcnow
from chess_trainer.core.srs.queue import MODES, QueueFilters, build_queue, local_day_start
from chess_trainer.core.srs.reviews import record_review, unleech

router = APIRouter(prefix="/api")


SOURCES = ("own", "lichess", "study")


def _last_move(db: Session, p: Puzzle) -> tuple[str | None, str | None]:
    """Posição antes do lance do adversário e o lance (UCI), para a animação de entrada.

    Em `own` o lance vem da partida: punir parte do próprio erro do adversário;
    evitar, do lance anterior ao erro do usuário (no ply 1 não há nenhum). Nas
    outras fontes o lance foi gravado no puzzle ao guardá-lo.
    """
    pos = p.position
    if p.source != "own" or pos is None:
        return p.fen_before, p.last_move
    if p.kind == "punish":
        return pos.fen, pos.move_uci
    prev = db.scalar(select(Position).where(Position.game_id == pos.game_id, Position.ply == pos.ply - 1))
    return (prev.fen, prev.move_uci) if prev is not None else (None, None)


def _study_ref(p: Puzzle) -> StudyRef | None:
    chapter = p.chapter
    if chapter is None:
        return None
    study = chapter.study
    return StudyRef(id=chapter.study_id, title=study.title if study is not None else "",
                    chapter_id=chapter.id, chapter_name=chapter.name, lichess_url=chapter.lichess_url)


def _my_replies(db: Session, puzzles: Sequence[Puzzle]) -> dict[str, MyReplyInfo]:
    """A resposta do usuário ao erro do adversário, por id de exercício.

    É a posição da mesma partida no ply seguinte ao do erro; fica de fora quem
    não é "punir" (o erro é do próprio usuário) e quem errou no último lance da
    partida. Vai em lote de propósito: `_puzzle_out` roda para a fila inteira e
    uma consulta por exercício viraria N+1.
    """
    alvos = {p.id: (p.position.game_id, p.position.ply + 1)
             for p in puzzles if p.position is not None and p.position.mistake_by == "opponent"}
    if not alvos:
        return {}
    pares = set(alvos.values())
    # uma condição por par faria a árvore da consulta crescer com a fila (a
    # lista de leeches não tem limite, e o SQLite recusa com "Expression tree
    # is too large"): pede as posições das partidas envolvidas e peneira aqui
    jogos = {game_id for game_id, _ in pares}
    rows = db.scalars(select(Position).where(Position.game_id.in_(jogos))).all()
    por_par = {(r.game_id, r.ply): r for r in rows if (r.game_id, r.ply) in pares}
    out: dict[str, MyReplyInfo] = {}
    for puzzle_id, par in alvos.items():
        r = por_par.get(par)
        if r is not None:
            out[puzzle_id] = MyReplyInfo(ply=r.ply, move_played=r.move_played, move_uci=r.move_uci,
                                         eval_before=r.eval_before, eval_after=r.eval_after)
    return out


def _puzzle_out(db: Session, p: Puzzle, my_replies: dict[str, MyReplyInfo] | None = None) -> PuzzleOut:
    """Um exercício como a API o entrega. `my_replies` é o resultado de
    `_my_replies` para o lote todo; sem ele, a consulta é feita só para este."""
    pos = p.position
    if my_replies is None:
        my_replies = _my_replies(db, [p])
    fen_before, last_move = _last_move(db, p)
    game = None
    if p.game is not None:
        game = GameRef(id=p.game.id, white=p.game.white, black=p.game.black, played_at=p.game.played_at,
                       source_id=p.game.source_id, my_color=p.game.my_color)
    mistake = None
    if pos is not None:
        mistake = MistakeRef(ply=pos.ply, move_played=pos.move_played, move_uci=pos.move_uci,
                             eval_before=pos.eval_before, eval_after=pos.eval_after,
                             mistake_level=pos.mistake_level, mistake_by=pos.mistake_by,
                             my_reply=my_replies.get(p.id))
    return PuzzleOut(
        id=p.id, kind=p.kind, fen_start=p.fen_start, side_to_move=p.side_to_move,
        solution=p.solution_data, end_reason=p.end_reason, theme=p.theme, category=p.category,
        solver_moves=p.solver_moves, is_leech=p.is_leech, source=p.source, in_queue=p.in_queue,
        srs=SrsOut(ease=p.srs_ease, interval_days=p.srs_interval_days, lapses=p.srs_lapses,
                   due_at=p.srs_due_at, last_reviewed_at=p.srs_last_reviewed_at),
        fen_before=fen_before, last_move=last_move, game=game,
        ply=pos.ply if pos is not None else None,
        move_played=pos.move_played if pos is not None else None,
        mistake=mistake, study=_study_ref(p),
        siblings=[PuzzleSibling(id=s.id, kind=s.kind) for s in (pos.puzzles if pos is not None else []) if s.id != p.id],
    )


def _puzzles_out(db: Session, puzzles: Sequence[Puzzle]) -> list[PuzzleOut]:
    """Uma lista de exercícios com as respostas da partida buscadas de uma vez."""
    my_replies = _my_replies(db, puzzles)
    return [_puzzle_out(db, p, my_replies) for p in puzzles]


def _get_puzzle(db: Session, puzzle_id: str) -> Puzzle:
    puzzle = db.get(Puzzle, puzzle_id)
    if puzzle is None:
        raise HTTPException(404, "puzzle não encontrado")
    return puzzle


@router.get("/puzzles/{puzzle_id}", response_model=PuzzleOut)
def get_puzzle(puzzle_id: str, db: Session = Depends(get_db)):
    return _puzzle_out(db, _get_puzzle(db, puzzle_id))


@router.get("/queue", response_model=QueueOut)
def get_queue(
    category: str | None = None, theme: str | None = None, kind: str | None = None, color: str | None = None,
    sources: str | None = None, study_id: str | None = None,
    mode: Literal[MODES] = "review",
    count_only: bool = False,
    db: Session = Depends(get_db),
):
    """Fila de treino no modo pedido: `review` (repetição espaçada, só o que já
    foi feito e venceu), `new` (a primeira vez dos meus erros) ou `study` (um
    estudo inteiro, na ordem dos capítulos).

    Com `count_only`, a fila é montada do mesmo jeito e as contagens são as
    mesmas, mas a resposta vem com `items` vazio: para quem só quer os números
    (um badge, por exemplo) não vale o custo de serializar cada exercício."""
    filters = QueueFilters(category, theme, kind, color,
                           sources=tuple(v.strip() for v in (sources or "").split(",") if v.strip()),
                           study_id=study_id, mode=mode)
    try:
        result = build_queue(db, filters, load_settings(db), utcnow())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return QueueOut(mode=mode, due_count=result.due_count, new_available=result.new_available,
                    new_remaining_today=result.new_remaining_today,
                    items=[] if count_only else _puzzles_out(db, result.items))


@router.get("/leeches", response_model=list[PuzzleOut])
def get_leeches(db: Session = Depends(get_db)):
    puzzles = db.scalars(select(Puzzle).where(Puzzle.is_leech.is_(True)).order_by(Puzzle.leech_since.desc())).all()
    return _puzzles_out(db, puzzles)


@router.post("/puzzles/{puzzle_id}/unleech", response_model=PuzzleOut)
def post_unleech(puzzle_id: str, db: Session = Depends(get_db)):
    puzzle = _get_puzzle(db, puzzle_id)
    unleech(db, puzzle, utcnow())
    return _puzzle_out(db, puzzle)


@router.post("/puzzles/{puzzle_id}/queue", response_model=PuzzleOut)
def post_queue_toggle(puzzle_id: str, body: QueueIn, db: Session = Depends(get_db)):
    """Tira o exercício da repetição ou o traz de volta. Nada é apagado: o
    histórico continua e ele volta exatamente como estava."""
    puzzle = _get_puzzle(db, puzzle_id)
    if puzzle.in_queue != body.in_queue:
        puzzle.in_queue = body.in_queue
        db.commit()
    return _puzzle_out(db, puzzle)


def _session_out(db: Session, s: TrainingSession) -> SessionOut:
    rows = db.execute(
        select(func.count(Review.id), func.sum(Review.duration_ms),
               func.sum(case((Review.result == "correct", 1), else_=0)))
        .where(Review.session_id == s.id)
    ).one()
    return SessionOut(id=s.id, started_at=s.started_at, ended_at=s.ended_at, planned_minutes=s.planned_minutes,
                      filters=json.loads(s.filters or "{}"), reviews=int(rows[0] or 0),
                      correct=int(rows[2] or 0), total_duration_ms=int(rows[1] or 0))


@router.post("/sessions", response_model=SessionOut, status_code=201)
def post_session(body: SessionIn, db: Session = Depends(get_db)):
    s = TrainingSession(planned_minutes=body.planned_minutes, filters=json.dumps(body.filters))
    db.add(s)
    db.commit()
    return _session_out(db, s)


@router.post("/sessions/{session_id}/end", response_model=SessionOut)
def end_session(session_id: str, db: Session = Depends(get_db)):
    s = db.get(TrainingSession, session_id)
    if s is None:
        raise HTTPException(404, "sessão não encontrada")
    if s.ended_at is None:
        s.ended_at = utcnow()
        db.commit()
    return _session_out(db, s)


@router.post("/reviews", response_model=ReviewOut, status_code=201)
def post_review(body: ReviewIn, db: Session = Depends(get_db)):
    puzzle = _get_puzzle(db, body.puzzle_id)
    if body.session_id is not None and db.get(TrainingSession, body.session_id) is None:
        raise HTTPException(404, "sessão não encontrada")
    review = record_review(db, puzzle, session_id=body.session_id, correct=body.correct,
                           used_hint=body.used_hint, duration_ms=body.duration_ms,
                           now=utcnow(), settings=load_settings(db))
    return ReviewOut(id=review.id, puzzle_id=puzzle.id, result=review.result, used_hint=review.used_hint,
                     ease=review.ease, interval_days=review.interval_days, due_at=review.due_at,
                     lapses=review.lapses, is_leech=puzzle.is_leech)


def _streak_days(db: Session, now) -> int:
    stamps = db.scalars(select(Review.reviewed_at)).all()
    days = {ts.replace(tzinfo=timezone.utc).astimezone().date() for ts in stamps}
    today = now.replace(tzinfo=timezone.utc).astimezone().date()
    cursor = today if today in days else today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _by_source(db: Session, now) -> dict[str, SourceCount]:
    """Guardados e vencidos por fonte, com o mesmo recorte da fila (na fila e sem sanguessuga)."""
    rows = db.execute(
        select(Puzzle.source, func.count(Puzzle.id),
               func.sum(case((Puzzle.srs_due_at <= now, 1), else_=0)))
        .where(Puzzle.in_queue.is_(True), Puzzle.is_leech.is_(False))
        .group_by(Puzzle.source)
    ).all()
    counts = {source: SourceCount(in_queue=int(total or 0), due=int(due or 0)) for source, total, due in rows}
    return {source: counts.get(source, SourceCount()) for source in SOURCES}


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db)):
    """Números da tela inicial.

    Atenção ao `puzzles_total`: é o total de exercícios de todas as fontes
    (erros próprios, táticas e estudos), inclusive os que estão fora da fila —
    não é o tamanho do que se vai treinar. Quem quer isso olha `due_today` e
    `new_available`."""
    now = utcnow()
    settings = load_settings(db)
    queue = build_queue(db, QueueFilters(), settings, now)
    day_start = local_day_start(now)
    reviews_today = db.scalar(select(func.count(Review.id)).where(Review.reviewed_at >= day_start)) or 0
    last_import = get_setting(db, "last_import_at")
    return DashboardOut(
        due_today=queue.due_count,
        new_available=queue.new_available,
        new_remaining_today=queue.new_remaining_today,
        streak_days=_streak_days(db, now),
        reviews_today=int(reviews_today),
        last_import_at=last_import,
        games_total=int(db.scalar(select(func.count(Game.id))) or 0),
        games_analyzed=int(db.scalar(select(func.count(Game.id)).where(Game.analyzed_at.is_not(None))) or 0),
        puzzles_total=int(db.scalar(select(func.count(Puzzle.id))) or 0),
        leeches=int(db.scalar(select(func.count(Puzzle.id)).where(Puzzle.is_leech.is_(True))) or 0),
        by_source=_by_source(db, now),
    )
