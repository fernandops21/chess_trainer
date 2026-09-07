"""Parser puro do PGN exportado de um estudo do Lichess.

O export de um estudo traz um "jogo" PGN por capítulo, com headers próprios
(`[StudyName]`, `[ChapterName]`, `[ChapterURL]`, `[ChapterMode]`, `[FEN]`,
`[Orientation]`, `[Annotator]`). Aqui esse texto vira um `ParsedStudy` com a
lista de `ParsedChapter`, e os capítulos em modo `gamebook` ganham uma
`solution` no mesmo formato dos puzzles do app:

    {
      "moves": [{"uci": str, "by": "solver"|"engine", "alternatives": []}],
      "explanation_pv": [],
      "wrong_moves": {uci: comentário},          # opcional
      "comments": {"<i>": comentário},            # opcional
      "shapes": {"start"|"<i>": [forma, ...]},    # opcional
      "intro": comentário                         # opcional
    }

Convenções das chaves de `comments` e `shapes`:

- `"<i>"` é o índice do lance dentro de `moves`; `"0"` é o estado **depois**
  do primeiro lance da solução.
- as setas e casas desenhadas na posição inicial (comentário do nó raiz, antes
  de qualquer lance) ficam sob a chave `"start"`, nunca sob `"0"`.

Cada forma é `{"orig", "dest", "brush"}` para uma seta (`[%cal …]`) e
`{"orig", "brush"}` para o destaque de uma casa (`[%csl …]`, que o
python-chess representa como uma seta com `tail == head`). O pincel usa os
nomes do python-chess: `green`, `red`, `blue`, `yellow`.

Este módulo não acessa rede nem banco: recebe texto e devolve dados.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import chess
import chess.pgn

AUTHOR_PREFIX = "https://lichess.org/@/"

_COMMAND_RE = re.compile(r"\[%[^\]]*\]")
_WHITESPACE_RE = re.compile(r"\s+")
_STUDY_ID_RE = re.compile(r"/study/([A-Za-z0-9]+)")
_ORIENTATIONS = ("white", "black")


@dataclass
class ParsedChapter:
    """Um capítulo do estudo já interpretado."""

    order: int
    name: str
    lichess_url: str | None
    fen: str
    orientation: str
    mode: str  # "gamebook" ou "read"
    pgn: str
    intro_comment: str = ""
    solution: dict | None = None
    skipped_reason: str | None = None


@dataclass
class ParsedStudy:
    """Um estudo do Lichess já interpretado."""

    title: str
    author: str
    lichess_id: str | None
    chapters: list[ParsedChapter] = field(default_factory=list)


def clean_comment(text: str) -> str:
    """Remove os comandos `[%…]` (cal, csl, eval, clk, …) e normaliza espaços."""
    if not text:
        return ""
    return _WHITESPACE_RE.sub(" ", _COMMAND_RE.sub(" ", text)).strip()


def parse_study_pgn(text: str) -> ParsedStudy:
    """Interpreta o PGN de um estudo inteiro (um jogo por capítulo)."""
    stream = io.StringIO(text)
    chapters: list[ParsedChapter] = []
    title = ""
    author = ""
    lichess_id: str | None = None
    order = 0
    while True:
        game = chess.pgn.read_game(stream)
        if game is None:
            break
        order += 1
        headers = game.headers
        title = title or _study_title(headers)
        author = author or _author(headers)
        lichess_id = lichess_id or _study_id(headers.get("ChapterURL", ""))
        chapters.append(_chapter(game, order))
    return ParsedStudy(title=title, author=author, lichess_id=lichess_id, chapters=chapters)


# --- estudo --------------------------------------------------------------


def _study_title(headers) -> str:
    name = headers.get("StudyName", "").strip()
    if name:
        return name
    prefix, sep, _ = headers.get("Event", "").strip().partition(": ")
    return prefix if sep else ""


def _author(headers) -> str:
    annotator = headers.get("Annotator", "").strip()
    if annotator.startswith(AUTHOR_PREFIX):
        return annotator[len(AUTHOR_PREFIX) :]
    return annotator


def _study_id(url: str) -> str | None:
    match = _STUDY_ID_RE.search(url or "")
    return match.group(1) if match else None


# --- capítulo ------------------------------------------------------------


def _chapter(game: chess.pgn.Game, order: int) -> ParsedChapter:
    headers = game.headers
    url = headers.get("ChapterURL", "").strip()
    fen = headers.get("FEN", "").strip() or chess.STARTING_FEN
    mode = "gamebook" if headers.get("ChapterMode", "").strip() == "gamebook" else "read"
    chapter = ParsedChapter(
        order=order,
        name=_chapter_name(headers),
        lichess_url=url or None,
        fen=fen,
        orientation="white",
        mode=mode,
        pgn="",
        intro_comment=clean_comment(game.comment),
    )
    try:
        board = chess.Board(fen)
        # o exportador reproduz os lances, então também depende da FEN válida
        chapter.pgn = str(game)
    except ValueError as exc:
        chapter.pgn = _headers_only(game)
        chapter.skipped_reason = f"FEN inválida: {exc}"
        return chapter
    chapter.fen = board.fen()
    chapter.orientation = _orientation(headers, board)
    if game.errors:
        chapter.skipped_reason = f"lance ilegal: {game.errors[0]}"
        return chapter
    if mode == "gamebook":
        chapter.solution = _solution(game)
        if chapter.solution is None:
            chapter.mode = "read"
    return chapter


def _headers_only(game: chess.pgn.Game) -> str:
    """Só os headers, para capítulos cuja FEN impede exportar os lances."""
    return "\n".join(f'[{key} "{value}"]' for key, value in game.headers.items())


def _chapter_name(headers) -> str:
    name = headers.get("ChapterName", "").strip()
    if name:
        return name
    event = headers.get("Event", "").strip()
    _, sep, suffix = event.partition(": ")
    return suffix if sep else event


def _orientation(headers, board: chess.Board) -> str:
    declared = headers.get("Orientation", "").strip().lower()
    if declared in _ORIENTATIONS:
        return declared
    return "white" if board.turn == chess.WHITE else "black"


# --- solução -------------------------------------------------------------


def _solution(game: chess.pgn.Game) -> dict | None:
    """Monta a solução do capítulo. Devolve None se não houver lances."""
    mainline = list(game.mainline())
    if not mainline:
        return None
    moves: list[dict] = []
    comments: dict[str, str] = {}
    shapes: dict[str, list[dict]] = {}
    wrong_moves: dict[str, str] = {}

    root_shapes = _shapes(game.arrows())
    if root_shapes:
        shapes["start"] = root_shapes

    for i, node in enumerate(mainline):
        by = "solver" if i % 2 == 0 else "engine"
        moves.append({"uci": node.move.uci(), "by": by, "alternatives": []})
        comment = clean_comment(node.comment)
        if comment:
            comments[str(i)] = comment
        node_shapes = _shapes(node.arrows())
        if node_shapes:
            shapes[str(i)] = node_shapes
        if by == "solver":
            wrong_moves.update(_wrong_moves(node))

    solution: dict = {"moves": moves, "explanation_pv": []}
    if wrong_moves:
        solution["wrong_moves"] = wrong_moves
    if comments:
        solution["comments"] = comments
    if shapes:
        solution["shapes"] = shapes
    intro = clean_comment(game.comment)
    if intro:
        solution["intro"] = intro
    return solution


def _wrong_moves(node: chess.pgn.ChildNode) -> dict[str, str]:
    """Variações irmãs de um lance do solver que trazem comentário.

    Variações sem comentário são ignoradas (não há o que mostrar ao aluno),
    assim como os lances mais fundos dentro de cada variação."""
    parent = node.parent
    if parent is None:
        return {}
    found: dict[str, str] = {}
    for sibling in parent.variations:
        if sibling is node or sibling.move is None:
            continue
        comment = clean_comment(sibling.comment)
        if comment:
            found[sibling.move.uci()] = comment
    return found


def _shapes(arrows) -> list[dict]:
    """Converte as setas do python-chess para o formato do app."""
    shapes = []
    for arrow in arrows:
        shape = {"orig": chess.square_name(arrow.tail)}
        if arrow.head != arrow.tail:
            shape["dest"] = chess.square_name(arrow.head)
        shape["brush"] = arrow.color
        shapes.append(shape)
    return shapes
