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

Quem é o aluno (`solver`) não é necessariamente o lado a jogar na FEN: muitos
capítulos abrem com um lance do adversário e o aluno joga a partir do segundo
(ver `_solver_side`). Nesse caso esse primeiro lance vira o *lance de
introdução* (`ParsedExercise.intro_move`), fora da solução: a tela de treino
abre na FEN do capítulo, anima o lance e só então libera as peças.

Cada forma é `{"orig", "dest", "brush"}` para uma seta (`[%cal …]`) e
`{"orig", "brush"}` para o destaque de uma casa (`[%csl …]`, que o
python-chess representa como uma seta com `tail == head`). O pincel usa os
nomes do python-chess: `green`, `red`, `blue`, `yellow`.

Cada capítulo também traz a `tree`: a árvore de lances no formato do editor
(ver `tree.py`), que a importação grava em `study_chapters.tree_json`.

Este módulo não acessa rede nem banco: recebe texto e devolve dados.
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field

import chess
import chess.pgn

# `clean_comment`, as formas e a árvore moram em `tree.py` (o editor também
# precisa delas); aqui elas continuam disponíveis com os nomes de sempre
from chess_trainer.core.studies.tree import (
    clean_comment,
    game_to_tree,
    orientation_of,
    shapes_from_arrows,
)

AUTHOR_PREFIX = "https://lichess.org/@/"

# título de um PGN comum que nem torneio tem
PGN_IMPORTADO = "PGN importado"

_STUDY_ID_RE = re.compile(r"/study/([A-Za-z0-9]+)")

__all__ = [
    "ParsedChapter",
    "ParsedExercise",
    "ParsedStudy",
    "clean_comment",
    "parse_study_pgn",
    "solution_from_game",
]


@dataclass
class ParsedExercise:
    """O exercício de um capítulo gamebook.

    `intro_move` é o lance (UCI) do adversário que abre o capítulo quando o
    aluno não é o lado a jogar na FEN; ele fica **fora** de `solution` e o
    exercício começa na posição depois dele. `None` quando o aluno já é o lado
    a jogar (a maioria dos capítulos).
    """

    solution: dict
    intro_move: str | None = None


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
    #: lance de introdução do adversário (UCI), quando há; ver `ParsedExercise`
    intro_move: str | None = None
    tree: dict | None = None
    skipped_reason: str | None = None


@dataclass
class ParsedStudy:
    """Um estudo do Lichess já interpretado."""

    title: str
    author: str
    lichess_id: str | None
    chapters: list[ParsedChapter] = field(default_factory=list)


def parse_study_pgn(text: str) -> ParsedStudy:
    """Interpreta o PGN de um estudo inteiro (um jogo por capítulo).

    Serve tanto para o export de um estudo do Lichess quanto para um PGN comum
    (coleção de partidas): sem os headers do estudo, cada partida vira um
    capítulo de leitura e os nomes saem dos jogadores, do torneio e do ano.
    """
    stream = io.StringIO(text)
    chapters: list[ParsedChapter] = []
    title = ""
    author = ""
    lichess_id: str | None = None
    primeiros_headers = None
    order = 0
    while True:
        game = chess.pgn.read_game(stream)
        if game is None:
            break
        order += 1
        headers = game.headers
        if primeiros_headers is None:
            primeiros_headers = headers
        title = title or _study_title(headers)
        author = author or _author(headers)
        lichess_id = lichess_id or _study_id(headers.get("ChapterURL", ""))
        chapters.append(_chapter(game, order))
    if not title and primeiros_headers is not None:
        title = _titulo_de_pgn_comum(primeiros_headers)
    return ParsedStudy(title=title, author=author, lichess_id=lichess_id, chapters=chapters)


# --- estudo --------------------------------------------------------------


def _unescape(text: str) -> str:
    """Desfaz o escape de aspas e barras dos headers PGN (`\\"` e `\\`), que o
    python-chess devolve como estão no arquivo."""
    return text.replace('\\"', '"').replace("\\\\", "\\")


def _preenchido(valor: str) -> bool:
    """Header com conteúdo de verdade ("?" é o valor que o PGN usa para "não sei")."""
    return bool(valor) and valor != "?"


def _study_title(headers) -> str:
    """Título vindo dos headers de estudo; "" quando o PGN não diz nada."""
    name = _unescape(headers.get("StudyName", "").strip())
    if name:
        return name
    prefix, sep, _ = _unescape(headers.get("Event", "").strip()).partition(": ")
    return prefix if sep else ""


def _titulo_de_pgn_comum(headers) -> str:
    """PGN sem headers de estudo: vale o torneio do primeiro jogo."""
    event = _unescape(headers.get("Event", "").strip())
    return event if _preenchido(event) else PGN_IMPORTADO


def _author(headers) -> str:
    annotator = _unescape(headers.get("Annotator", "").strip())
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
    modo_declarado = headers.get("ChapterMode", "").strip()
    mode = "gamebook" if modo_declarado == "gamebook" else "read"
    chapter = ParsedChapter(
        order=order,
        name=_chapter_name(headers, order),
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
        # sem posição inicial não há exercício possível: vale como leitura
        chapter.mode = "read"
        return chapter
    chapter.fen = board.fen()
    chapter.orientation = orientation_of(headers, board)
    chapter.tree = game_to_tree(game)
    if game.errors:
        chapter.skipped_reason = f"lance ilegal: {game.errors[0]}"
        # a linha não pôde ser lida até o fim: nada de gamebook, o capítulo fica como leitura
        chapter.mode = "read"
        return chapter
    # sem header ChapterMode (exportação do Lichess para capítulos comuns) vale a
    # heurística; um modo declarado que não seja gamebook (ex.: "normal", que a
    # nossa exportação escreve) é respeitado.
    if not modo_declarado and _parece_exercicio(game, board):
        # muitos autores montam exercícios como capítulos comuns: posição
        # própria (não a inicial) e uma linha curta. Tratamos como exercício.
        mode = chapter.mode = "gamebook"
    if mode == "gamebook":
        exercicio = solution_from_game(game)
        if exercicio is None:
            chapter.mode = "read"
        else:
            chapter.solution = exercicio.solution
            chapter.intro_move = exercicio.intro_move
    return chapter


# capítulo comum vira exercício quando parte de uma posição própria com uma
# linha principal de até este tanto de meios-lances (partidas anotadas inteiras
# continuam como leitura)
MAX_PLIES_EXERCICIO = 24


def _parece_exercicio(game: chess.pgn.Game, board: chess.Board) -> bool:
    posicao_inicial = board.board_fen() == chess.Board().board_fen()
    if posicao_inicial:
        return False
    n = sum(1 for _ in game.mainline())
    return 1 <= n <= MAX_PLIES_EXERCICIO


def _headers_only(game: chess.pgn.Game) -> str:
    """Só os headers, para capítulos cuja FEN impede exportar os lances."""
    return "\n".join(f'[{key} "{value}"]' for key, value in game.headers.items())


def _chapter_name(headers, order: int) -> str:
    name = _unescape(headers.get("ChapterName", "").strip())
    if name:
        return name
    event = _unescape(headers.get("Event", "").strip())
    _, sep, suffix = event.partition(": ")
    if sep:
        return suffix
    # PGN comum: um capítulo por partida, com o nome tirado dos jogadores
    white = _unescape(headers.get("White", "").strip())
    black = _unescape(headers.get("Black", "").strip())
    torneio = event if _preenchido(event) else ""
    ano = _unescape(headers.get("Date", "").strip())[:4]
    if not _preenchido(ano) or ano == "????":
        ano = ""
    if _preenchido(white) and _preenchido(black):
        detalhes = ", ".join(parte for parte in (torneio, ano) if parte)
        return f"{white} × {black}" + (f" ({detalhes})" if detalhes else "")
    return torneio or f"Capítulo {order}"


# --- solução -------------------------------------------------------------


def solution_from_game(game: chess.pgn.Game) -> ParsedExercise | None:
    """Monta o exercício do capítulo. Devolve None se não houver lances.

    Quando o aluno não é o lado a jogar na FEN (ver `_solver_side`), o primeiro
    lance da linha principal é do adversário: ele sai da solução e volta como
    `intro_move`; os índices de `comments` e `shapes` acompanham o
    deslocamento, e o que o autor escreveu e desenhou nesse lance passa a valer
    para a posição em que o aluno começa (`intro` e `shapes["start"]`).

    Uma linha que termina com um lance do adversário mantém esse lance como
    `engine` final na solução — a tela de treino o joga e encerra o exercício.
    """
    mainline = list(game.mainline())
    if not mainline:
        return None
    board = game.board()
    intro_node: chess.pgn.ChildNode | None = None
    # com um lance só não há o que deslocar: virar tudo introdução deixaria o
    # aluno sem nada para jogar, então a linha fica como está
    if _solver_side(game, mainline, board) != board.turn and len(mainline) > 1:
        intro_node, mainline = mainline[0], mainline[1:]

    moves: list[dict] = []
    comments: dict[str, str] = {}
    shapes: dict[str, list[dict]] = {}
    wrong_moves: dict[str, str] = {}

    intro = clean_comment(game.comment)
    root_shapes = shapes_from_arrows(game.arrows())
    if intro_node is not None:
        # o lance de introdução já está na tela quando o aluno chega: o
        # comentário dele é enunciado, e as marcações são as da posição inicial
        comentario = clean_comment(intro_node.comment)
        intro = "\n\n".join(parte for parte in (intro, comentario) if parte)
        root_shapes = root_shapes + shapes_from_arrows(intro_node.arrows())
    if root_shapes:
        shapes["start"] = root_shapes

    for i, node in enumerate(mainline):
        by = "solver" if i % 2 == 0 else "engine"
        moves.append({"uci": node.move.uci(), "by": by, "alternatives": []})
        comment = clean_comment(node.comment)
        if comment:
            comments[str(i)] = comment
        node_shapes = shapes_from_arrows(node.arrows())
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
    if intro:
        solution["intro"] = intro
    return ParsedExercise(solution=solution,
                          intro_move=intro_node.move.uci() if intro_node is not None else None)


# textos que dizem de quem é a vez, sem maiúsculas nem acentos
_PRETAS_RE = re.compile(r"jogam as (pretas|negras)|(pretas|negras) jogam|black to (play|move)")
_BRANCAS_RE = re.compile(r"jogam as brancas|brancas jogam|white to (play|move)")

_RESULTADOS = {"1-0": chess.WHITE, "0-1": chess.BLACK}


def _solver_side(game: chess.pgn.Game, mainline: list[chess.pgn.ChildNode],
                 board: chess.Board) -> chess.Color:
    """De quem é o exercício, na ordem; a primeira regra que decide vence.

    1. o enunciado ou o comentário do primeiro lance dizem de quem é a vez
       ("Jogam as pretas", "White to move"…);
    2. o `[Result]` do capítulo: `1-0` é das brancas, `0-1` das pretas
       (`1/2-1/2` e `*` não decidem);
    3. o lado que joga o último lance da linha principal — o autor para depois
       do lance do aluno;
    4. sem nenhum sinal, o lado a jogar na FEN. É o que a regra 3 devolve
       quando a linha tem um número ímpar de meios-lances.
    """
    pelo_texto = _lado_pelo_texto(clean_comment(game.comment))
    if pelo_texto is None:
        pelo_texto = _lado_pelo_texto(clean_comment(mainline[0].comment))
    if pelo_texto is not None:
        return pelo_texto
    pelo_resultado = _RESULTADOS.get(game.headers.get("Result", "").strip())
    if pelo_resultado is not None:
        return pelo_resultado
    # linha com número par de meios-lances termina no lado oposto ao da FEN
    return board.turn if len(mainline) % 2 else not board.turn


def _lado_pelo_texto(texto: str) -> chess.Color | None:
    """Lado anunciado por um texto do autor; None quando ele não diz nada.
    Se as duas fórmulas aparecerem, vale a primeira do texto."""
    limpo = _sem_acentos(texto)
    pretas = _PRETAS_RE.search(limpo)
    brancas = _BRANCAS_RE.search(limpo)
    if pretas is not None and (brancas is None or pretas.start() < brancas.start()):
        return chess.BLACK
    if brancas is not None:
        return chess.WHITE
    return None


def _sem_acentos(texto: str) -> str:
    """Minúsculas e sem acentos, para comparar texto do autor."""
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


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
