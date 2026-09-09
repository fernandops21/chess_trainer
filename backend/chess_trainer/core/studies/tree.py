"""Árvore de lances de um capítulo: JSON ⇄ `chess.pgn.Game`, validação e PGN.

A árvore é a fonte da verdade do editor de capítulos. Formato:

    {"fen": "<FEN inicial>", "orientation": "white|black", "intro": "...",
     "root": {"shapes": [forma, ...], "children": [node, ...]}}

    node = {"id": "n12", "uci": "e2e4", "san": "e4", "comment": "...",
            "shapes": [forma, ...], "nags": [1], "children": [node, ...]}

    forma = {"orig": "e2", "dest": "e4", "brush": "green"}   # seta
          | {"orig": "d5", "brush": "red"}                    # casa destacada

O primeiro filho é a linha principal; os demais são variações. Os `id` são
`n1, n2, …` em pré-ordem quando a árvore vem de um PGN (`game_to_tree`); vindos
do editor, são gerados no cliente e só precisam ser únicos dentro do capítulo.

No PGN as marcações viram `[%cal Ge2e4,…]` (setas) e `[%csl Rd5,…]` (casas) no
começo do comentário do nó; as da raiz, no comentário inicial, junto do
enunciado. A ordem das marcações é preservada nos dois sentidos: o Lichess
grava `[%csl …][%cal …]` em alguns nós e `[%cal …][%csl …]` em outros, e um
capítulo exportado e lido de novo tem de dar exatamente a mesma árvore.

Este módulo não acessa banco nem rede: recebe e devolve dados (as funções de
PGN de capítulo leem apenas os campos do `StudyChapter` que recebem).
"""

from __future__ import annotations

import io
import json
import re
from typing import TYPE_CHECKING

import chess
import chess.pgn

if TYPE_CHECKING:  # pragma: no cover - só para as anotações
    from chess_trainer.core.models import Study, StudyChapter
    from chess_trainer.core.studies.parser import ParsedExercise

# limites do editor (ver o plano do ciclo): árvore e comentário de um nó
MAX_NOS = 2000
MAX_COMENTARIO = 4000

# no máximo isto de erros é devolvido por `validate_tree`: uma árvore muito
# quebrada não precisa virar uma resposta gigante
MAX_ERROS = 20

ORIENTATIONS = ("white", "black")

# nomes de pincel do python-chess (e do chessground) e a letra usada no PGN
BRUSHES: dict[str, str] = {"green": "G", "red": "R", "blue": "B", "yellow": "Y"}

SITE = "chess-trainer"

# header próprio com o id do estudo neste app: é ele que faz o PGN exportado
# daqui, colado de volta, atualizar o estudo em vez de criar uma cópia
LOCAL_ID_HEADER = "ChessTrainerStudy"

_COMMAND_RE = re.compile(r"\[%[^\]]*\]")
_WHITESPACE_RE = re.compile(r"\s+")


def clean_comment(text: str) -> str:
    """Remove os comandos `[%…]` (cal, csl, eval, clk, …) e normaliza espaços."""
    if not text:
        return ""
    return _WHITESPACE_RE.sub(" ", _COMMAND_RE.sub(" ", text)).strip()


def shapes_from_arrows(arrows) -> list[dict]:
    """Converte as setas do python-chess para o formato do app. Uma casa
    destacada (`[%csl …]`) chega como seta com origem igual ao destino."""
    shapes = []
    for arrow in arrows:
        shape = {"orig": chess.square_name(arrow.tail)}
        if arrow.head != arrow.tail:
            shape["dest"] = chess.square_name(arrow.head)
        shape["brush"] = arrow.color
        shapes.append(shape)
    return shapes


def empty_tree(fen: str = chess.STARTING_FEN, orientation: str = "white") -> dict:
    """Árvore sem lances, para um capítulo novo."""
    return {
        "fen": fen or chess.STARTING_FEN,
        "orientation": orientation if orientation in ORIENTATIONS else "white",
        "intro": "",
        "root": {"shapes": [], "children": []},
    }


# --- PGN → árvore --------------------------------------------------------


def game_to_tree(game: chess.pgn.Game) -> dict:
    """Árvore de um jogo lido do PGN. Levanta `ValueError` se a FEN do header
    for inválida (o chamador decide o que fazer com o capítulo)."""
    board = game.board()
    tree = {
        "fen": board.fen(),
        "orientation": orientation_of(game.headers, board),
        "intro": clean_comment(game.comment),
        "root": {"shapes": shapes_from_arrows(game.arrows()), "children": []},
    }
    contador = 0
    # pilha de (nó do PGN, posição antes do lance, lista de filhos onde entra);
    # empilhar ao contrário faz a visita sair em pré-ordem (primeiro filho antes
    # dos irmãos), que é a ordem dos ids
    pilha = [(filho, board, tree["root"]["children"]) for filho in reversed(game.variations)]
    while pilha:
        pgn_node, antes, saida = pilha.pop()
        contador += 1
        node = {
            "id": f"n{contador}",
            "uci": pgn_node.move.uci(),
            "san": antes.san(pgn_node.move),
            "comment": clean_comment(pgn_node.comment),
            "shapes": shapes_from_arrows(pgn_node.arrows()),
            "nags": sorted(pgn_node.nags),
            "children": [],
        }
        saida.append(node)
        depois = antes.copy(stack=False)
        depois.push(pgn_node.move)
        pilha.extend((filho, depois, node["children"]) for filho in reversed(pgn_node.variations))
    return tree


def orientation_of(headers, board: chess.Board) -> str:
    """Orientação declarada no header; sem ela, o lado que joga."""
    declared = headers.get("Orientation", "").strip().lower()
    if declared in ORIENTATIONS:
        return declared
    return "white" if board.turn == chess.WHITE else "black"


def tree_from_pgn(pgn: str, fen: str = "", orientation: str = "") -> dict:
    """Árvore a partir do PGN guardado de um capítulo (capítulos importados
    antes do editor não têm `tree_json`). PGN ilegível vira árvore vazia."""
    game = chess.pgn.read_game(io.StringIO(pgn)) if (pgn or "").strip() else None
    if game is not None:
        try:
            tree = game_to_tree(game)
        except ValueError:
            tree = None
        if tree is not None:
            if orientation in ORIENTATIONS:
                # a coluna do capítulo manda: é o que o usuário vê na tela
                tree["orientation"] = orientation
            return tree
    try:
        chess.Board(fen or chess.STARTING_FEN)
    except ValueError:
        fen = chess.STARTING_FEN
    return empty_tree(fen or chess.STARTING_FEN, orientation or "white")


def chapter_tree(chapter: StudyChapter) -> dict:
    """Árvore do capítulo: a gravada, ou a que sai do PGN quando não há uma."""
    if chapter.tree_json:
        try:
            tree = json.loads(chapter.tree_json)
        except ValueError:
            tree = None
        if isinstance(tree, dict) and isinstance(tree.get("root"), dict):
            return tree
    return tree_from_pgn(chapter.pgn or "", chapter.fen or "", chapter.orientation or "")


# --- árvore → PGN --------------------------------------------------------


def tree_to_game(tree: dict, headers: dict[str, str] | None = None) -> chess.pgn.Game:
    """Jogo do python-chess equivalente à árvore. Levanta `ValueError` na
    primeira FEN inválida ou lance ilegal — use `validate_tree` antes para ter
    a lista completa de erros em português."""
    game = chess.pgn.Game()
    for chave, valor in (headers or {}).items():
        game.headers[chave] = valor
    board = chess.Board(_fen_of(tree))
    # cuida dos headers [FEN]/[SetUp] (e os tira quando é a posição inicial)
    game.setup(board)
    root = tree.get("root") or {}
    game.comment = _comment_pgn(root.get("shapes"), tree.get("intro", ""))

    pilha = [(node, game, board) for node in reversed(_children(root))]
    while pilha:
        node, pai, antes = pilha.pop()
        move = move_of(antes, node)
        filho = pai.add_variation(move)
        filho.comment = _comment_pgn(node.get("shapes"), node.get("comment", ""))
        filho.nags = {int(n) for n in node.get("nags") or []}
        depois = antes.copy(stack=False)
        depois.push(move)
        pilha.extend((neto, filho, depois) for neto in reversed(_children(node)))
    return game


def move_of(board: chess.Board, node: dict) -> chess.Move:
    """Lance do nó a partir da posição dada. `uci` manda; sem ele, vale o `san`.
    Lance ilegal levanta `ValueError` (o `IllegalMoveError` do python-chess)."""
    uci = (node.get("uci") or "").strip()
    if uci:
        return board.parse_uci(uci)
    san = (node.get("san") or "").strip()
    if san:
        return board.parse_san(san)
    raise chess.IllegalMoveError("nó sem lance")


def _comment_pgn(shapes, text: str) -> str:
    """Comentário do PGN: as marcações no começo, depois o texto."""
    prefixo = ""
    comando_anterior = ""
    tokens: list[str] = []
    for shape in shapes or []:
        token = _shape_pgn(shape)
        if token is None:
            continue
        # marcações seguidas do mesmo tipo entram num comando só, na ordem em
        # que estão na árvore — é o que devolve a mesma árvore na releitura
        comando = "cal" if shape.get("dest") else "csl"
        if comando != comando_anterior and tokens:
            prefixo += f"[%{comando_anterior} {','.join(tokens)}]"
            tokens = []
        comando_anterior = comando
        tokens.append(token)
    if tokens:
        prefixo += f"[%{comando_anterior} {','.join(tokens)}]"
    texto = (text or "").strip()
    if prefixo and texto:
        return f"{prefixo} {texto}"
    return prefixo or texto


def _shape_pgn(shape: dict) -> str | None:
    """`Ge2e4` (seta) ou `Rd5` (casa). Pincel ou casa desconhecidos são
    ignorados: a validação já os acusou antes de chegar aqui."""
    letra = BRUSHES.get(shape.get("brush", ""))
    orig = shape.get("orig", "")
    dest = shape.get("dest") or ""
    if letra is None or orig not in chess.SQUARE_NAMES:
        return None
    if dest and dest not in chess.SQUARE_NAMES:
        return None
    return f"{letra}{orig}{dest}"


def _fen_of(tree: dict) -> str:
    """FEN da árvore, sem confiar no tipo: o JSON vem do editor e a FEN pode
    chegar como número ou objeto. Quem valida é `validate_tree`; aqui só não se
    levanta `AttributeError`."""
    fen = tree.get("fen")
    fen = fen.strip() if isinstance(fen, str) else ""
    return fen or chess.STARTING_FEN


def _children(node: dict) -> list[dict]:
    if not isinstance(node, dict):
        return []
    filhos = node.get("children")
    return filhos if isinstance(filhos, list) else []


# --- validação -----------------------------------------------------------


def validate_tree(tree: dict) -> list[str]:
    """Erros da árvore, em português e prontos para mostrar ao usuário. Lista
    vazia quer dizer que dá para salvar. É total sobre entrada não confiável
    (o JSON vem direto do editor): nunca levanta exceção, mesmo com tipos
    errados, chaves ausentes ou nós que não são objetos — cada problema vira
    uma mensagem em vez de uma `KeyError`/`AttributeError`."""
    if not isinstance(tree, dict):
        return ["a árvore não é um objeto"]
    fen = tree.get("fen")
    if fen is not None and not isinstance(fen, str):
        # sem a posição inicial não dá para conferir lance nenhum
        return ["FEN inválida: a posição inicial precisa ser texto"]
    try:
        board = chess.Board(_fen_of(tree))
    except ValueError as exc:
        return [f"FEN inválida: {exc}"]
    root = tree.get("root")
    if not isinstance(root, dict):
        return ['a árvore não tem "root"']

    erros: list[str] = []

    intro = tree.get("intro")
    if intro is not None and not isinstance(intro, str):
        erros.append("o enunciado precisa ser texto")
        intro = ""
    intro = intro or ""
    if len(intro) > MAX_COMENTARIO:
        erros.append(f"enunciado com mais de {MAX_COMENTARIO} caracteres")
    if "}" in intro:
        erros.append("o enunciado não pode conter '}'")
    if "[%" in intro:
        erros.append("o enunciado não pode conter '[%'")

    erros.extend(_validar_marcacoes(root.get("shapes"), "na posição inicial"))

    total = count_nodes(tree)
    if total > MAX_NOS:
        # árvore grande demais não vai ser salva de jeito nenhum: percorrer os
        # milhares de nós só para juntar mais mensagens não ajuda ninguém
        erros.append(f"a árvore tem {total} lances; o máximo é {MAX_NOS}")
        return erros[:MAX_ERROS]

    pilha = [(node, board) for node in reversed(_children(root))]
    while pilha and len(erros) < MAX_ERROS:
        node, antes = pilha.pop()
        if not isinstance(node, dict):
            erros.append("há um nó que não é um objeto")
            continue
        node_id = node.get("id") or "?"

        comentario = node.get("comment")
        if comentario is not None and not isinstance(comentario, str):
            erros.append(f"comentário do nó {node_id} inválido")
            comentario = ""
        comentario = comentario or ""
        if len(comentario) > MAX_COMENTARIO:
            erros.append(
                f"o comentário do nó {node_id} tem {len(comentario)} caracteres; o máximo é {MAX_COMENTARIO}"
            )
        if "}" in comentario:
            erros.append(f"comentário do nó {node_id} não pode conter '}}'")
        if "[%" in comentario:
            # `[%cal …]` no texto viraria marcação ao reler o PGN: o comentário
            # deixaria de ser o que o usuário escreveu
            erros.append(f"comentário do nó {node_id} não pode conter '[%'")

        erros.extend(_validar_marcacoes(node.get("shapes"), f"no nó {node_id}"))

        nags = node.get("nags")
        if nags is not None and (
            not isinstance(nags, list)
            or any(not isinstance(nag, int) or isinstance(nag, bool) for nag in nags)
        ):
            erros.append(f"NAG inválido no nó {node_id}")

        children = node.get("children")
        if children is not None and not isinstance(children, list):
            erros.append(f"filhos inválidos no nó {node_id}")

        uci = node.get("uci")
        if uci is not None and not isinstance(uci, str):
            erros.append(f"lance inválido no nó {node_id}")
            uci = None
        san = node.get("san")
        if san is not None and not isinstance(san, str):
            erros.append(f"lance inválido no nó {node_id}")
            san = None

        try:
            move = move_of(antes, {"uci": uci, "san": san})
        except ValueError:
            # sem o lance não dá para seguir: o resto do ramo fica de fora
            erros.append(f"lance ilegal em {san or uci or '?'} do nó {node_id}")
            continue
        depois = antes.copy(stack=False)
        depois.push(move)
        pilha.extend((filho, depois) for filho in reversed(_children(node)))
    return erros[:MAX_ERROS]


def _validar_marcacoes(shapes, onde: str) -> list[str]:
    """Erros das marcações (`shapes`) de um nó ou da posição inicial: pincel
    conhecido e casas válidas. `onde` já vem escrito como aparece na mensagem
    (`"na posição inicial"` ou `"no nó n2"`) — o usuário não conhece "raiz"."""
    if shapes is None:
        return []
    if not isinstance(shapes, list):
        return [f"marcações inválidas {onde}"]
    erros: list[str] = []
    for shape in shapes:
        if not isinstance(shape, dict):
            erros.append(f"marcação inválida {onde}")
            continue
        brush = shape.get("brush")
        if brush not in BRUSHES:
            erros.append(f'marcação com pincel desconhecido "{brush}" {onde}')
        orig = shape.get("orig")
        dest = shape.get("dest")
        if orig not in chess.SQUARE_NAMES or (dest is not None and dest not in chess.SQUARE_NAMES):
            erros.append(f"marcação com casa inválida {onde}")
    return erros


def count_nodes(tree: dict) -> int:
    """Quantos lances a árvore tem (a raiz não conta)."""
    total = 0
    pilha = list(_children(tree.get("root") or {}))
    while pilha:
        node = pilha.pop()
        total += 1
        pilha.extend(_children(node))
    return total


def mainline_ucis(tree: dict) -> list[str]:
    """UCIs da linha principal (o primeiro filho de cada nó)."""
    ucis: list[str] = []
    filhos = _children(tree.get("root") or {})
    while filhos:
        node = filhos[0]
        ucis.append(node.get("uci") or "")
        filhos = _children(node)
    return ucis


# --- solução do exercício ------------------------------------------------


def solution_from_tree(tree: dict, solver: chess.Color | None = None) -> ParsedExercise | None:
    """Exercício (solução e lance de introdução) a partir da árvore. `None`
    quando não há lances.

    A árvore não guarda o `[Result]` da partida, então a regra do resultado não
    entra aqui; as outras (texto do autor, último lance, lado a jogar) valem
    igual à importação. Com `solver` (o lado que o exercício já tinha gravado)
    a falta do resultado deixa de importar: só o texto do autor o contraria."""
    # import tardio de propósito: o parser importa este módulo
    from chess_trainer.core.studies.parser import solution_from_game

    return solution_from_game(tree_to_game(tree, {}), solver)


# --- PGN do capítulo e do estudo -----------------------------------------


def chapter_pgn(chapter: StudyChapter, study: Study | None = None) -> str:
    """PGN de um capítulo, no formato que o Lichess importa."""
    tree = chapter_tree(chapter)
    game = tree_to_game(tree, chapter_headers(chapter, study))
    return str(game)


def chapter_headers(chapter: StudyChapter, study: Study | None = None) -> dict[str, str]:
    titulo = (study.title if study else "").strip()
    nome = (chapter.name or "").strip()
    autor = (study.author if study else "").strip()
    headers: dict[str, str] = {
        "Event": f"{titulo}: {nome}" if titulo else nome,
        "Site": SITE,
        "Result": "*",
        "StudyName": titulo,
        "ChapterName": nome,
        "Orientation": chapter.orientation or "white",
    }
    if study is not None and study.id:
        # colar este PGN de volta atualiza o estudo que o gerou (ver `_find_study`)
        headers[LOCAL_ID_HEADER] = study.id
    if autor:
        # o parser lê o autor do estudo daqui na volta
        headers["Annotator"] = autor
    if chapter.mode == "gamebook":
        headers["ChapterMode"] = "gamebook"
    else:
        # explícito para que a reimportação não aplique a heurística de exercício
        headers["ChapterMode"] = "normal"
    return headers


def study_pgn(study: Study) -> str:
    """PGN do estudo inteiro: um jogo por capítulo, na ordem, separados por
    linha em branco."""
    capitulos = sorted(study.chapters, key=lambda c: c.order)
    return "\n\n".join(chapter_pgn(chapter, study) for chapter in capitulos)
