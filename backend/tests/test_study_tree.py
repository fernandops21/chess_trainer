"""Testes da árvore de lances dos capítulos: JSON ⇄ `chess.pgn.Game`, validação
e exportação de PGN."""

import io
import json
from pathlib import Path

import chess
import chess.pgn
import pytest

from chess_trainer.core.models import Study, StudyChapter
from chess_trainer.core.studies.parser import parse_study_pgn, solution_from_game
from chess_trainer.core.studies.tree import (
    MAX_COMENTARIO,
    MAX_NOS,
    chapter_pgn,
    empty_tree,
    game_to_tree,
    solution_from_tree,
    study_pgn,
    tree_to_game,
    validate_tree,
)

FIXTURE = Path(__file__).parent / "fixtures" / "study_4JKVAfaE.pgn"


@pytest.fixture(scope="module")
def texto_do_estudo() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def jogos(texto_do_estudo: str) -> list[chess.pgn.Game]:
    stream = io.StringIO(texto_do_estudo)
    jogos = []
    while True:
        game = chess.pgn.read_game(stream)
        if game is None:
            return jogos
        jogos.append(game)


def game_de(pgn: str) -> chess.pgn.Game:
    game = chess.pgn.read_game(io.StringIO(pgn))
    assert game is not None
    return game


def nos(tree: dict) -> list[dict]:
    """Todos os nós da árvore em pré-ordem."""
    achados: list[dict] = []
    pilha = list(reversed(tree["root"]["children"]))
    while pilha:
        node = pilha.pop()
        achados.append(node)
        pilha.extend(reversed(node["children"]))
    return achados


# --- game_to_tree --------------------------------------------------------


def test_arvore_do_primeiro_capitulo(jogos):
    tree = game_to_tree(jogos[0])
    assert tree["fen"].endswith("b kq - 2 10")
    assert tree["orientation"] == "black"
    assert "acabaram de rocar" in tree["intro"]
    assert tree["root"]["shapes"] == []
    # ids em pré-ordem: linha principal inteira antes das variações do primeiro lance
    assert [n["id"] for n in nos(tree)] == [f"n{i}" for i in range(1, 10)]
    assert [n["san"] for n in nos(tree)] == [
        "Qb6+", "Kh1", "Qxb5", "O-O", "Bg6", "Be3", "f5", "Qe2", "O-O",
    ]
    primeiro = tree["root"]["children"][0]
    assert primeiro["uci"] == "d8b6"
    assert primeiro["nags"] == [1]  # o "!" do PGN
    assert primeiro["comment"] == "Aproveitando o alinhamento de intersecção."
    # as variações são os irmãos seguintes do primeiro lance
    assert [c["san"] for c in tree["root"]["children"]] == ["Qb6+", "O-O", "Bg6"]
    assert [c["san"] for c in primeiro["children"]] == ["Kh1"]


def test_comentario_do_no_vem_sem_os_comandos_de_colchete():
    game = game_de('[Event "x"]\n\n1. e4 { Avanço [%eval 0.2] [%cal Ge2e4] } *\n')
    node = game_to_tree(game)["root"]["children"][0]
    assert node["comment"] == "Avanço"
    assert node["shapes"] == [{"orig": "e2", "dest": "e4", "brush": "green"}]


def test_arvore_guarda_as_marcacoes_da_posicao_inicial():
    game = game_de('[Event "x"]\n\n{ Olhe [%csl Ge4][%cal Rd1h5] } 1. e4 *\n')
    tree = game_to_tree(game)
    assert tree["intro"] == "Olhe"
    assert tree["root"]["shapes"] == [
        {"orig": "e4", "brush": "green"},
        {"orig": "d1", "dest": "h5", "brush": "red"},
    ]


# --- round trip ----------------------------------------------------------


def test_round_trip_de_todos_os_capitulos_da_fixture(jogos):
    assert len(jogos) == 27
    for game in jogos:
        tree = game_to_tree(game)
        game2 = tree_to_game(tree, dict(game.headers))
        assert game_to_tree(game2) == tree
        # a linha principal e as variações continuam as mesmas (o texto de
        # `mainline_moves()` traz os comentários, e `[%eval]`/`[%clk]` saem da
        # árvore de propósito: a comparação é dos lances)
        assert [m.uci() for m in game2.mainline_moves()] == [m.uci() for m in game.mainline_moves()]
        assert [n["san"] for n in nos(game_to_tree(game2))] == [n["san"] for n in nos(tree)]


def test_round_trip_mantem_as_setas_do_capitulo_real(jogos):
    comgeral = [g for g in jogos if "%cal" in str(g) or "%csl" in str(g)]
    assert comgeral
    for game in comgeral:
        tree = game_to_tree(game)
        marcados = [n for n in nos(tree) if n["shapes"]]
        assert marcados
        assert game_to_tree(tree_to_game(tree, dict(game.headers))) == tree


def test_round_trip_mantem_a_ordem_de_csl_antes_de_cal():
    """No PGN do professor há comentários com `[%csl …]` antes de `[%cal …]`:
    a ordem das marcações não pode mudar no caminho de volta."""
    game = game_de('[Event "x"]\n\n1. e4 { [%csl Bd4][%cal Rf2f4] } *\n')
    tree = game_to_tree(game)
    assert tree["root"]["children"][0]["shapes"] == [
        {"orig": "d4", "brush": "blue"},
        {"orig": "f2", "dest": "f4", "brush": "red"},
    ]
    game2 = tree_to_game(tree, {})
    assert "[%csl Bd4][%cal Rf2f4]" in game2.variations[0].comment
    assert game_to_tree(game2) == tree


def test_tree_to_game_repoe_fen_setup_e_nags():
    fen = "r2qk2r/pp2nppp/2n1p3/1B1pPb2/5P2/2P5/PP4PP/RNBQ1RK1 b kq - 2 10"
    tree = {
        "fen": fen,
        "orientation": "black",
        "intro": "Enunciado",
        "root": {"shapes": [], "children": [
            {"id": "n1", "uci": "d8b6", "san": "Qb6+", "comment": "Nota", "shapes": [],
             "nags": [1], "children": []},
        ]},
    }
    game = tree_to_game(tree, {})
    assert game.headers["FEN"] == fen
    assert game.headers["SetUp"] == "1"
    assert game.comment == "Enunciado"
    filho = game.variations[0]
    assert filho.san() == "Qb6+" and filho.nags == {1}
    assert "[FEN " in str(game) and "$1" in str(game)


def test_tree_to_game_recusa_lance_ilegal():
    tree = empty_tree(chess.STARTING_FEN, "white")
    tree["root"]["children"].append(
        {"id": "n1", "uci": "e2e5", "san": "e5", "comment": "", "shapes": [], "nags": [], "children": []}
    )
    with pytest.raises(ValueError):
        tree_to_game(tree, {})


# --- solução -------------------------------------------------------------


def test_solution_from_tree_igual_a_do_parser(texto_do_estudo, jogos):
    estudo = parse_study_pgn(texto_do_estudo)
    cap = estudo.chapters[0]
    exercicio = solution_from_tree(game_to_tree(jogos[0]))
    assert exercicio.solution == cap.solution and exercicio.intro_move == cap.intro_move


def test_solution_from_tree_de_todos_os_gamebooks(texto_do_estudo, jogos):
    """A árvore não guarda o `[Result]`, mas nesta fixture as outras regras do
    lado do aluno bastam: o exercício sai igual ao da importação, lance de
    introdução incluído."""
    estudo = parse_study_pgn(texto_do_estudo)
    for cap, game in zip(estudo.chapters, jogos, strict=True):
        if cap.mode != "gamebook":
            continue
        exercicio = solution_from_tree(game_to_tree(game))
        assert exercicio.solution == cap.solution
        assert exercicio.intro_move == cap.intro_move


def test_solution_from_game_e_publico(jogos):
    assert solution_from_game(jogos[0]) == solution_from_tree(game_to_tree(jogos[0]))


def test_solution_from_tree_sem_lances_e_none():
    assert solution_from_tree(empty_tree(chess.STARTING_FEN, "white")) is None


# --- validate_tree -------------------------------------------------------


def arvore_de_sans(sans: list[str], fen: str = chess.STARTING_FEN) -> dict:
    """Árvore de uma linha só, a partir de lances em SAN."""
    tree = empty_tree(fen, "white")
    board = chess.Board(fen)
    filhos = tree["root"]["children"]
    for i, san in enumerate(sans, start=1):
        move = board.parse_san(san)
        node = {"id": f"n{i}", "uci": move.uci(), "san": san, "comment": "", "shapes": [],
                "nags": [], "children": []}
        filhos.append(node)
        filhos = node["children"]
        board.push(move)
    return tree


def test_validate_tree_aceita_arvore_boa(jogos):
    assert validate_tree(game_to_tree(jogos[0])) == []
    assert validate_tree(empty_tree(chess.STARTING_FEN, "white")) == []


def test_validate_tree_acusa_fen_invalida():
    tree = empty_tree(chess.STARTING_FEN, "white")
    tree["fen"] = "isso nao e uma fen"
    erros = validate_tree(tree)
    assert erros and "FEN inválida" in erros[0]


def test_validate_tree_acusa_lance_ilegal():
    tree = arvore_de_sans(["e4", "e5"])
    ilegal = tree["root"]["children"][0]["children"][0]
    ilegal["uci"] = "e7e4"
    ilegal["san"] = "e4"
    erros = validate_tree(tree)
    assert len(erros) == 1
    assert "lance ilegal" in erros[0] and "n2" in erros[0]


def test_validate_tree_acusa_arvore_grande_demais():
    tree = empty_tree(chess.STARTING_FEN, "white")
    filhos = tree["root"]["children"]
    board = chess.Board()
    ciclo = ["Nf3", "Nf6", "Ng1", "Ng8"]
    for i in range(MAX_NOS + 1):
        san = ciclo[i % 4]
        move = board.parse_san(san)
        node = {"id": f"n{i + 1}", "uci": move.uci(), "san": san, "comment": "", "shapes": [],
                "nags": [], "children": []}
        filhos.append(node)
        filhos = node["children"]
        board.push(move)
    erros = validate_tree(tree)
    assert erros and str(MAX_NOS) in erros[0]


def test_validate_tree_acusa_comentario_longo_demais():
    tree = arvore_de_sans(["e4"])
    tree["root"]["children"][0]["comment"] = "a" * (MAX_COMENTARIO + 1)
    erros = validate_tree(tree)
    assert len(erros) == 1 and "n1" in erros[0]


def test_validate_tree_acusa_pincel_desconhecido():
    tree = arvore_de_sans(["e4"])
    tree["root"]["children"][0]["shapes"] = [{"orig": "e2", "dest": "e4", "brush": "roxo"}]
    erros = validate_tree(tree)
    assert len(erros) == 1 and "roxo" in erros[0] and "n1" in erros[0]


# --- validate_tree é total sobre entrada não confiável --------------------


def test_validate_tree_nunca_levanta_excecao_com_arvore_que_nao_e_objeto():
    assert validate_tree("isso não é uma árvore") == ["a árvore não é um objeto"]
    assert validate_tree(None) == ["a árvore não é um objeto"]
    assert validate_tree(["a", "b"]) == ["a árvore não é um objeto"]


def test_validate_tree_acusa_arvore_sem_root():
    erros = validate_tree({"fen": chess.STARTING_FEN})
    assert erros == ['a árvore não tem "root"']


def test_validate_tree_nunca_levanta_excecao_com_no_que_nao_e_objeto():
    tree = arvore_de_sans(["e4"])
    tree["root"]["children"].append("isso não é um nó")
    erros = validate_tree(tree)
    assert erros  # acusa o problema em vez de levantar exceção


def test_validate_tree_acusa_comentario_com_tipo_errado():
    tree = arvore_de_sans(["e4"])
    tree["root"]["children"][0]["comment"] = 5
    erros = validate_tree(tree)
    assert erros and "n1" in erros[0]


def test_validate_tree_acusa_nag_invalido():
    tree = arvore_de_sans(["e4"])
    tree["root"]["children"][0]["nags"] = ["x"]
    erros = validate_tree(tree)
    assert erros and "NAG" in erros[0] and "n1" in erros[0]


def test_validate_tree_acusa_filhos_com_tipo_errado():
    tree = arvore_de_sans(["e4"])
    tree["root"]["children"][0]["children"] = "x"
    erros = validate_tree(tree)
    assert erros and "n1" in erros[0]


def test_validate_tree_acusa_marcacao_invalida_na_posicao_inicial():
    tree = empty_tree(chess.STARTING_FEN, "white")
    tree["root"]["shapes"] = [{"orig": "e2", "dest": "e4", "brush": "roxo"}]
    erros = validate_tree(tree)
    assert erros and "roxo" in erros[0] and "na posição inicial" in erros[0]


def test_validate_tree_acusa_casa_invalida_na_marcacao_da_posicao_inicial():
    tree = empty_tree(chess.STARTING_FEN, "white")
    tree["root"]["shapes"] = [{"orig": "z9", "brush": "green"}]
    erros = validate_tree(tree)
    assert erros and "casa inválida" in erros[0] and "na posição inicial" in erros[0]


def test_validate_tree_acusa_casa_invalida_na_marcacao_do_no():
    tree = arvore_de_sans(["e4"])
    tree["root"]["children"][0]["shapes"] = [{"orig": "e2", "dest": "z9", "brush": "green"}]
    erros = validate_tree(tree)
    assert erros and "casa inválida" in erros[0] and "n1" in erros[0]


def test_validate_tree_acusa_enunciado_longo_demais():
    tree = empty_tree(chess.STARTING_FEN, "white")
    tree["intro"] = "a" * (MAX_COMENTARIO + 1)
    erros = validate_tree(tree)
    assert erros and f"mais de {MAX_COMENTARIO}" in erros[0]


def test_validate_tree_acusa_comentario_com_chave_de_fechamento():
    tree = arvore_de_sans(["e4"])
    tree["root"]["children"][0]["comment"] = "nota } estranha"
    erros = validate_tree(tree)
    assert erros and "n1" in erros[0] and "}" in erros[0]


def test_validate_tree_acusa_fen_que_nao_e_texto():
    # o JSON vem do editor: uma FEN que não é texto tem de virar mensagem, não exceção
    erros = validate_tree({"fen": 5, "root": {"shapes": [], "children": []}})
    assert erros and "FEN inválida" in erros[0]


def test_validate_tree_acusa_enunciado_que_nao_e_texto():
    tree = empty_tree(chess.STARTING_FEN, "white")
    tree["intro"] = 5
    erros = validate_tree(tree)
    assert erros and "enunciado" in erros[0]


def test_tree_to_game_nao_estoura_com_fen_que_nao_e_texto():
    game = tree_to_game({"fen": 5, "root": {"shapes": [], "children": []}}, {})
    assert game.board().fen() == chess.STARTING_FEN


def test_validate_tree_acusa_enunciado_com_chave_de_fechamento():
    tree = empty_tree(chess.STARTING_FEN, "white")
    tree["intro"] = "olhe } isso"
    erros = validate_tree(tree)
    assert erros and "enunciado" in erros[0] and "}" in erros[0]


def test_validate_tree_acusa_comentario_com_comando_do_pgn():
    # `[%cal …]` no texto viraria marcação na volta do PGN: o comentário deixaria
    # de ser o que o usuário escreveu
    tree = arvore_de_sans(["e4"])
    tree["root"]["children"][0]["comment"] = "olhe [%cal Ge2e4] isso"
    erros = validate_tree(tree)
    assert erros and "n1" in erros[0] and "[%" in erros[0]


def test_validate_tree_acusa_enunciado_com_comando_do_pgn():
    tree = empty_tree(chess.STARTING_FEN, "white")
    tree["intro"] = "olhe [%csl Rd5] isso"
    erros = validate_tree(tree)
    assert erros and "enunciado" in erros[0] and "[%" in erros[0]


def test_validate_tree_para_de_conferir_a_arvore_grande_demais():
    # passou do limite, nem adianta percorrer: a resposta é uma mensagem só
    tree = empty_tree(chess.STARTING_FEN, "white")
    tree["root"]["children"] = [
        {"id": f"n{i}", "uci": "e2e9", "san": "", "comment": "", "shapes": [], "nags": [], "children": []}
        for i in range(MAX_NOS + 1)
    ]
    erros = validate_tree(tree)
    assert len(erros) == 1 and str(MAX_NOS) in erros[0]


# --- PGN do capítulo e do estudo -----------------------------------------


def capitulo(**over) -> StudyChapter:
    base = dict(id="c1", study_id="e1", order=1, name="Exercício 1", fen=chess.STARTING_FEN,
                orientation="white", mode="gamebook", pgn="", intro_comment="", tree_json="")
    base.update(over)
    return StudyChapter(**base)


def test_chapter_pgn_traz_os_headers_do_lichess(jogos):
    tree = game_to_tree(jogos[0])
    estudo = Study(id="e1", title="Aulas do Basso", author="basso01")
    cap = capitulo(name="Exercício 1", orientation="black", fen=tree["fen"],
                   tree_json=json.dumps(tree, ensure_ascii=False))
    pgn = chapter_pgn(cap, estudo)
    assert '[Event "Aulas do Basso: Exercício 1"]' in pgn
    assert '[Site "chess-trainer"]' in pgn
    assert '[Result "*"]' in pgn
    assert '[StudyName "Aulas do Basso"]' in pgn
    assert '[ChapterName "Exercício 1"]' in pgn
    assert '[ChapterMode "gamebook"]' in pgn
    assert '[Orientation "black"]' in pgn
    assert f'[FEN "{tree["fen"]}"]' in pgn and '[SetUp "1"]' in pgn
    assert "Qb6+" in pgn and "acabaram de rocar" in pgn


def test_chapter_pgn_de_capitulo_de_leitura_sai_como_normal():
    cap = capitulo(mode="read", tree_json="")
    cap.pgn = '[Event "x"]\n\n1. e4 e5 *\n'
    pgn = chapter_pgn(cap, Study(id="e1", title="Estudo", author=""))
    # capítulo de leitura sai marcado como "normal": a reimportação não aplica a heurística de exercício
    assert '[ChapterMode "normal"]' in pgn and '"gamebook"' not in pgn
    # sem `tree_json`, a árvore sai do PGN guardado
    assert "1. e4 e5" in pgn


def test_chapter_pgn_reimportado_devolve_a_mesma_arvore(jogos):
    tree = game_to_tree(jogos[0])
    estudo = Study(id="e1", title="Aulas do Basso", author="basso01")
    cap = capitulo(orientation="black", fen=tree["fen"], tree_json=json.dumps(tree, ensure_ascii=False))
    lido = parse_study_pgn(chapter_pgn(cap, estudo))
    assert lido.title == "Aulas do Basso"
    assert lido.author == "basso01"
    assert lido.chapters[0].tree == tree


def test_study_pgn_junta_os_capitulos_em_ordem(texto_do_estudo):
    estudo = Study(id="e1", title="Aulas do Basso", author="basso01")
    parsed = parse_study_pgn(texto_do_estudo)
    estudo.chapters = [
        capitulo(id=f"c{p.order}", order=p.order, name=p.name, fen=p.fen, orientation=p.orientation,
                 mode=p.mode, pgn=p.pgn, tree_json=json.dumps(p.tree, ensure_ascii=False))
        for p in parsed.chapters
    ]
    texto = study_pgn(estudo)
    relido = parse_study_pgn(texto)
    assert [c.name for c in relido.chapters] == [c.name for c in parsed.chapters]
    assert [c.tree for c in relido.chapters] == [c.tree for c in parsed.chapters]


def test_empty_tree():
    tree = empty_tree(chess.STARTING_FEN, "black")
    assert tree == {"fen": chess.STARTING_FEN, "orientation": "black", "intro": "",
                    "root": {"shapes": [], "children": []}}
