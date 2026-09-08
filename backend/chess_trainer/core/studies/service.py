"""Serviço dos estudos: baixar, importar (upsert), editar, exportar e remover.

O parser (`parser.py`) só interpreta texto; aqui o `ParsedStudy` vira linhas de
`studies`, `study_chapters` e `puzzles`. Reimportar é um upsert: capítulos são
reconhecidos pela `lichess_url` (sem URL, pelo nome e só depois pela ordem), o
exercício de um capítulo é atualizado no lugar — mesmo id, mesmo histórico de
repetição espaçada — e capítulos que sumiram do estudo saem da fila sem serem
apagados.

A segunda metade do arquivo é o editor: estudos criados aqui (`origin="local"`)
e a edição de qualquer capítulo. Ao salvar, a árvore (`tree.py`) é a fonte da
verdade — dela saem o PGN, a FEN, o enunciado e o exercício, que é recriado
pelas mesmas regras da reimportação.
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
from chess_trainer.core.studies.tree import (
    ORIENTATIONS,
    chapter_pgn,
    chapter_tree,
    empty_tree,
    solution_from_tree,
    validate_tree,
)

STUDY_PGN_URL = "https://lichess.org/api/study/{lichess_id}.pgn"
STUDY_URL = "https://lichess.org/study/{lichess_id}"

# `/study/<id>` com ou sem host e com ou sem o capítulo depois do id
_STUDY_URL_RE = re.compile(r"(?:^|/)study/([A-Za-z0-9]{8})(?:/[A-Za-z0-9]{8})?$")

# limite da lista de capítulos pulados na mensagem final do job
DETALHE_MAX = 300


class StudyNotFound(Exception):
    """O Lichess respondeu 404: estudo privado ou inexistente."""


class TreeInvalid(Exception):
    """A árvore não passou na validação. `errors` traz as mensagens em
    português, prontas para o corpo da resposta 422."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


class ChapterOrderError(Exception):
    """A nova ordem não é uma permutação dos capítulos do estudo."""


class StudyImportCancelled(Exception):
    """O usuário cancelou a importação antes de ela gravar. Levantada de dentro
    do `on_chapter` de `upsert_study`, ou seja, antes do commit: o chamador dá
    rollback e o estudo não entra pela metade."""


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
        if self.chapters and not self.puzzles and not self.skipped:
            # sem isto o usuário lê "0 exercícios" e acha que a importação falhou
            texto += " (só capítulos de leitura; nenhum exercício)"
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
        study = Study(id=new_id(), title=parsed.title, author=parsed.author, origin="lichess",
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

    existing = list(db.scalars(
        select(StudyChapter).where(StudyChapter.study_id == study.id).order_by(StudyChapter.order)
    ))
    matches = _match_chapters(existing, parsed.chapters)

    report = ImportReport(chapters=len(parsed.chapters))
    seen: set[str] = set()
    total = len(parsed.chapters)
    for done, parsed_chapter in enumerate(parsed.chapters, start=1):
        chapter = _upsert_chapter(db, study, matches[done - 1], parsed_chapter, report)
        seen.add(chapter.id)
        if on_chapter is not None:
            on_chapter(done, total)

    for chapter in existing:
        if chapter.id not in seen:
            _out_of_queue(db, chapter)

    db.commit()
    db.expire_all()
    return study, report


def _match_chapters(existing: list[StudyChapter],
                    parsed_chapters: list[ParsedChapter]) -> list[StudyChapter | None]:
    """Diz, para cada capítulo do PGN, qual capítulo já gravado ele atualiza (ou
    `None`, quando é capítulo novo).

    As regras valem nesta ordem, e cada capítulo existente é casado uma vez só:
    quem tem `ChapterURL` casa pela URL (e nada mais); quem não tem casa pelo
    nome e, só se não achar, pela ordem. O passo do nome roda para todos antes do
    passo da ordem: assim, num PGN sem URLs, um capítulo novo inserido no meio
    não toma o lugar — nem o exercício e o histórico — de quem já existia.
    """
    by_url = {c.lichess_url: c for c in existing if c.lichess_url}
    by_name: dict[str, list[StudyChapter]] = {}
    for chapter in existing:
        by_name.setdefault(chapter.name, []).append(chapter)
    by_order = {c.order: c for c in existing}

    matches: list[StudyChapter | None] = [None] * len(parsed_chapters)
    taken: set[str] = set()

    def take(chapter: StudyChapter | None) -> StudyChapter | None:
        if chapter is None or chapter.id in taken:
            return None
        taken.add(chapter.id)
        return chapter

    for i, parsed in enumerate(parsed_chapters):
        if parsed.lichess_url:
            matches[i] = take(by_url.get(parsed.lichess_url))
    for i, parsed in enumerate(parsed_chapters):
        if matches[i] is None and not parsed.lichess_url and parsed.name:
            # nomes repetidos: vale o primeiro ainda livre, na ordem do estudo
            for candidato in by_name.get(parsed.name, ()):
                if candidato.id not in taken:
                    matches[i] = take(candidato)
                    break
    for i, parsed in enumerate(parsed_chapters):
        if matches[i] is None and not parsed.lichess_url:
            matches[i] = take(by_order.get(parsed.order))
    return matches


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
    # a árvore do parser é a fonte da verdade do editor; capítulo cuja FEN o
    # parser não leu fica sem árvore e o editor a monta na primeira abertura
    chapter.tree_json = json.dumps(parsed.tree, ensure_ascii=False) if parsed.tree else ""
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

    _upsert_puzzle(db, chapter, parsed.fen, parsed.solution, report,
                   intro_move=parsed.intro_move)
    return chapter


def _upsert_puzzle(db: Session, chapter: StudyChapter, fen: str, solution: dict,
                   report: ImportReport, editor: bool = False,
                   intro_move: str | None = None) -> None:
    """Cria ou atualiza o exercício do capítulo. Serve tanto à importação quanto
    ao editor: o que muda entre eles é só de onde vêm a FEN e a solução — e o
    que fazer quando outro capítulo já usa esta posição inicial. Na importação
    (`editor=False`) o capítulo fica sem exercício e a colisão vai para o
    relatório, porque um estudo grande não pode parar por causa de um capítulo;
    no editor o salvamento é recusado com `TreeInvalid`, para o usuário não sair
    da tela achando que gravou um exercício que não existe."""
    dados = _puzzle_fields(fen, solution, intro_move)
    puzzle = db.get(Puzzle, chapter.puzzle_id) if chapter.puzzle_id else None
    if puzzle is not None:
        # atualiza no lugar: id e histórico da repetição espaçada continuam
        try:
            # o SAVEPOINT protege a edição inteira: mudar a posição inicial para
            # uma que outro capítulo já usa esbarra na única (fen_start, kind,
            # source), e sem ele o erro derrubaria a transação toda
            with db.begin_nested():
                for campo, valor in dados.items():
                    setattr(puzzle, campo, valor)
                puzzle.chapter_id = chapter.id
                db.flush()
        except IntegrityError as exc:
            raise TreeInvalid(["posição inicial já usada por outro capítulo"]) from exc
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
            # roubaria o exercício e o histórico de quem já é dono
            if editor:
                # no editor a edição inteira é recusada: um capítulo salvo em
                # silêncio sem o exercício que o usuário pediu é pior que o 422
                raise TreeInvalid([
                    "posição inicial já usada por outro capítulo; "
                    "use outra posição inicial ou o modo leitura"
                ])
            # na importação o capítulo fica sem exercício e a colisão vai para o relatório
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


def _puzzle_fields(fen: str, solution: dict | None, intro_move: str | None = None) -> dict:
    """Campos do exercício a partir da posição inicial do capítulo e da solução.

    Com `intro_move` (o lance do adversário que abre o capítulo, quando o aluno
    não é o lado a jogar na FEN), o exercício começa **depois** dele:
    `fen_before` e `last_move` guardam a posição de antes e o lance, que a tela
    de treino anima antes de liberar as peças — os mesmos campos que as táticas
    do Lichess usam. Sem lance de introdução os dois voltam a ser nulos, para
    que reimportar um capítulo corrigido não deixe resto do que havia."""
    solution = solution or {}
    moves = solution.get("moves", [])
    board = chess.Board(fen)
    fen_before: str | None = None
    last_move: str | None = None
    if intro_move:
        fen_before, last_move = board.fen(), intro_move
        board.push_uci(intro_move)
        fen = board.fen()
    return {
        "fen_start": fen,
        "fen_before": fen_before,
        "last_move": last_move,
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


# --- árvore do capítulo --------------------------------------------------


def ensure_tree(chapter: StudyChapter) -> dict:
    """Árvore do capítulo, montada a partir do PGN e gravada quando ainda não
    havia uma (capítulos importados antes do editor). Quem chama dá o commit."""
    tree = chapter_tree(chapter)
    if not chapter.tree_json:
        chapter.tree_json = json.dumps(tree, ensure_ascii=False)
    return tree


def chapter_detail(chapter: StudyChapter) -> dict:
    """Tudo o que o editor precisa de um capítulo. A árvore vem garantida por
    `ensure_tree`, então quem chama tem de dar o commit."""
    tree = ensure_tree(chapter)
    return {
        "id": chapter.id,
        "order": chapter.order,
        "name": chapter.name,
        "lichess_url": chapter.lichess_url,
        "mode": chapter.mode,
        "in_queue": chapter.in_queue,
        "puzzle_id": chapter.puzzle_id,
        "intro_comment": chapter.intro_comment,
        "updated_at": chapter.updated_at,
        "fen": chapter.fen or tree["fen"],
        "orientation": chapter.orientation or tree["orientation"],
        "tree": tree,
        "pgn": chapter.pgn,
    }


# --- editor: estudos e capítulos locais ----------------------------------

MODES = ("gamebook", "read")

SEM_TITULO = "Estudo sem título"


def create_study(db: Session, title: str, author: str = "", now: datetime | None = None) -> Study:
    """Cria um estudo vazio feito aqui (nunca baixado do Lichess)."""
    now = now or utcnow()
    study = Study(id=new_id(), title=(title or "").strip() or SEM_TITULO,
                  author=(author or "").strip(), origin="local", source_url="", lichess_id=None,
                  imported_at=None, created_at=now, updated_at=now)
    db.add(study)
    db.commit()
    db.expire_all()
    return study


def update_study(db: Session, study: Study, title: str | None = None, author: str | None = None,
                 chapter_order: list[str] | None = None, now: datetime | None = None) -> Study:
    """Renomeia o estudo e/ou reordena os capítulos. Campo ausente fica como
    está — e um corpo sem campo algum não mexe nem no `updated_at`."""
    mudou = False
    if title is not None and title.strip():
        study.title = title.strip()
        mudou = True
    if author is not None:
        study.author = author.strip()
        mudou = True
    if chapter_order is not None:
        _reorder_chapters(study, chapter_order)
        mudou = True
    if mudou:
        study.updated_at = now or utcnow()
    db.commit()
    db.expire_all()
    return study


def _reorder_chapters(study: Study, chapter_order: list[str]) -> None:
    atuais = {c.id: c for c in study.chapters}
    if len(chapter_order) != len(atuais) or set(chapter_order) != set(atuais):
        raise ChapterOrderError("a nova ordem tem de listar cada capítulo do estudo exatamente uma vez")
    for posicao, chapter_id in enumerate(chapter_order, start=1):
        atuais[chapter_id].order = posicao


def create_chapter(db: Session, study: Study, name: str, fen: str = "", orientation: str = "white",
                   mode: str = "read", now: datetime | None = None) -> StudyChapter:
    """Cria um capítulo com a árvore vazia da posição dada. FEN inválida levanta
    `TreeInvalid` (é a mesma validação do salvamento)."""
    now = now or utcnow()
    tree = _normalized_tree(empty_tree(fen or chess.STARTING_FEN, orientation), orientation)
    _check_tree(tree)
    ordem = max((c.order for c in study.chapters), default=0) + 1
    chapter = StudyChapter(id=new_id(), study_id=study.id, order=ordem,
                           name=(name or "").strip() or f"Capítulo {ordem}",
                           fen=tree["fen"], orientation=tree["orientation"], mode=_mode(mode),
                           in_queue=True, updated_at=now)
    db.add(chapter)
    db.flush()
    _write_tree(chapter, tree, study)
    study.updated_at = now
    db.commit()
    db.expire_all()
    return chapter


def save_chapter(db: Session, chapter: StudyChapter, name: str, mode: str, orientation: str,
                 tree: dict, now: datetime | None = None) -> StudyChapter:
    """Salva a árvore do capítulo e recria o exercício a partir dela. Árvore
    inválida levanta `TreeInvalid` e nada é gravado."""
    now = now or utcnow()
    # tudo o que pode ser recusado é conferido antes de mexer no capítulo
    modo = _mode(mode)
    tree = _normalized_tree(tree, orientation)
    _check_tree(tree)
    study = chapter.study
    modo_antes = chapter.mode
    chapter.name = (name or "").strip() or chapter.name
    chapter.mode = modo
    _write_tree(chapter, tree, study)
    chapter.updated_at = now
    study.updated_at = now
    db.flush()
    _recreate_exercise(db, chapter, tree, modo_antes)
    db.commit()
    db.expire_all()
    return chapter


def delete_chapter(db: Session, chapter: StudyChapter, now: datetime | None = None) -> None:
    """Apaga o capítulo, o exercício dele e as revisões desse exercício, e
    renumera os capítulos que ficam para a ordem não ter buracos."""
    study = chapter.study
    puzzle_ids = set(db.scalars(select(Puzzle.id).where(Puzzle.chapter_id == chapter.id)))
    if chapter.puzzle_id:
        puzzle_ids.add(chapter.puzzle_id)
    chapter.puzzle_id = None
    db.flush()
    if puzzle_ids:
        db.execute(delete(Review).where(Review.puzzle_id.in_(puzzle_ids)))
        # nenhum outro capítulo pode ficar apontando para um exercício que sumiu
        db.execute(update(StudyChapter).where(StudyChapter.puzzle_id.in_(puzzle_ids)).values(puzzle_id=None))
        db.execute(delete(Puzzle).where(Puzzle.id.in_(puzzle_ids)))
    db.delete(chapter)
    db.flush()
    restantes = db.scalars(
        select(StudyChapter).where(StudyChapter.study_id == study.id).order_by(StudyChapter.order)
    ).all()
    for posicao, outro in enumerate(restantes, start=1):
        outro.order = posicao
    study.updated_at = now or utcnow()
    db.commit()
    db.expire_all()


def duplicate_chapter(db: Session, chapter: StudyChapter, now: datetime | None = None) -> StudyChapter:
    """Copia o capítulo logo depois dele.

    A cópia entra como leitura, sem exercício: ela começa com a mesma posição
    inicial do original e a única (fen_start, kind, source) não deixa dois
    exercícios de estudo partirem da mesma FEN. Quem duplicou muda a posição (ou
    a linha) e escolhe o modo gamebook ao salvar a cópia.
    """
    now = now or utcnow()
    study = chapter.study
    tree = ensure_tree(chapter)
    for outro in study.chapters:
        if outro.order > chapter.order:
            outro.order += 1
    db.flush()
    copia = StudyChapter(id=new_id(), study_id=study.id, order=chapter.order + 1,
                         name=f"{chapter.name} (cópia)", fen=chapter.fen,
                         orientation=chapter.orientation, mode="read",
                         in_queue=chapter.in_queue, updated_at=now)
    db.add(copia)
    db.flush()
    _write_tree(copia, tree, study)
    study.updated_at = now
    db.commit()
    db.expire_all()
    return copia


def _mode(mode: str) -> str:
    """Modo do capítulo. Valor fora de `MODES` é recusado (422) em vez de virar
    "read" caladamente: salvar um gamebook escrito errado não pode transformá-lo
    em capítulo de leitura sem o usuário saber."""
    if mode not in MODES:
        raise TreeInvalid(["modo inválido"])
    return mode


def _orientation(orientation: str) -> str:
    """Orientação do tabuleiro; valor desconhecido é recusado (422)."""
    if orientation not in ORIENTATIONS:
        raise TreeInvalid(["orientação inválida"])
    return orientation


def _normalized_tree(tree: dict, orientation: str) -> dict:
    """Cópia rasa da árvore com os campos do topo saneados. A orientação que o
    editor manda vale sobre a que veio dentro da árvore: é a que está na tela.

    FEN, enunciado e `root` que não são o que deveriam ficam como vieram: quem
    os recusa é `validate_tree`, com mensagem em português. Pôr aqui a posição
    inicial padrão ou uma raiz vazia salvaria outro capítulo, não o que o
    usuário editou — uma árvore que chegou quebrada apagaria os lances dele."""
    novo = dict(tree or {})
    fen = novo.get("fen")
    if fen is None or isinstance(fen, str):
        novo["fen"] = (fen or "").strip() or chess.STARTING_FEN
    novo["orientation"] = _orientation(orientation or novo.get("orientation") or "white")
    intro = novo.get("intro")
    if intro is None or isinstance(intro, str):
        novo["intro"] = (intro or "").strip()
    return novo


def _check_tree(tree: dict) -> None:
    """Valida e normaliza a FEN da árvore (a mesma que vai para o exercício)."""
    erros = validate_tree(tree)
    if erros:
        raise TreeInvalid(erros)
    tree["fen"] = chess.Board(tree["fen"]).fen()


def _write_tree(chapter: StudyChapter, tree: dict, study: Study | None) -> None:
    """A árvore manda: dela saem `tree_json`, a FEN, a orientação, o enunciado e
    o PGN do capítulo."""
    chapter.tree_json = json.dumps(tree, ensure_ascii=False)
    chapter.fen = tree["fen"]
    chapter.orientation = tree["orientation"]
    chapter.intro_comment = tree["intro"]
    chapter.pgn = chapter_pgn(chapter, study)


def _recreate_exercise(db: Session, chapter: StudyChapter, tree: dict, modo_antes: str) -> None:
    """Recria o exercício do capítulo a partir da árvore recém-salva.

    Capítulo de leitura (ou gamebook ainda sem lances) não tem exercício: o que
    havia sai da fila, sem ser apagado, para não perder o histórico de quem já o
    treinou. Voltar de leitura para gamebook devolve o exercício à fila — e só
    nessa passagem: `modo_antes` é o modo que o capítulo tinha antes deste
    salvamento, para que um exercício tirado da repetição na tela de treino
    continue fora depois de uma edição qualquer do capítulo.

    Se outro capítulo já usa esta posição inicial, o salvamento é recusado com
    `TreeInvalid` (a única (fen_start, kind, source)) — tanto ao criar quanto ao
    mudar a posição de um capítulo que já tem exercício.
    """
    antes = db.get(Puzzle, chapter.puzzle_id) if chapter.puzzle_id else None
    # a árvore não guarda o `[Result]`, então salvar sem editar nada poderia
    # inverter o lado do aluno: o exercício que já existe manda quem ele é
    solver = None
    if antes is not None:
        solver = chess.WHITE if antes.side_to_move == "white" else chess.BLACK
    exercicio = solution_from_tree(tree, solver) if chapter.mode == "gamebook" else None
    if exercicio is None:
        _puzzle_out_of_queue(db, chapter)
        return
    estava_fora = antes is not None and not antes.in_queue
    voltou_da_leitura = modo_antes != "gamebook"
    _upsert_puzzle(db, chapter, chapter.fen, exercicio.solution, ImportReport(), editor=True,
                   intro_move=exercicio.intro_move)
    if estava_fora and voltou_da_leitura and chapter.in_queue and chapter.puzzle_id:
        puzzle = db.get(Puzzle, chapter.puzzle_id)
        if puzzle is not None:
            puzzle.in_queue = True
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
