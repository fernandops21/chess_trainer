"""Testes do parser de PGN de estudos do Lichess."""

import io
import re
from pathlib import Path

import chess
import chess.pgn
import pytest

from chess_trainer.core.studies.parser import (
    ParsedChapter,
    clean_comment,
    parse_study_pgn,
    solution_from_game,
)

FIXTURE = Path(__file__).parent / "fixtures" / "study_4JKVAfaE.pgn"


@pytest.fixture(scope="module")
def texto_do_estudo() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def estudo(texto_do_estudo: str):
    return parse_study_pgn(texto_do_estudo)


def ucis_de_sans(fen: str, sans: list[str]) -> list[str]:
    """Converte uma sequência de lances em SAN para UCI a partir de uma FEN."""
    board = chess.Board(fen)
    ucis = []
    for san in sans:
        move = board.parse_san(san)
        ucis.append(move.uci())
        board.push(move)
    return ucis


def capitulo_por_url(estudo, sufixo: str) -> ParsedChapter:
    for cap in estudo.chapters:
        if cap.lichess_url and cap.lichess_url.endswith(sufixo):
            return cap
    raise AssertionError(f"capítulo {sufixo} não encontrado")


# --- metadados do estudo -------------------------------------------------


def test_metadados_do_estudo(estudo):
    assert estudo.title == "#PL05A - O jeito certo para achar tática em toda partida"
    assert estudo.author == "basso01"
    assert estudo.lichess_id == "4JKVAfaE"
    # PGN vindo do Lichess: nenhum id local
    assert estudo.local_id is None


def test_um_capitulo_por_jogo_do_pgn(estudo, texto_do_estudo):
    esperado = len(re.findall(r"^\[Event ", texto_do_estudo, flags=re.MULTILINE))
    assert esperado == 27
    assert len(estudo.chapters) == esperado
    assert [c.order for c in estudo.chapters] == list(range(1, esperado + 1))


def test_contagem_de_modos_bate_com_os_headers(estudo, texto_do_estudo):
    gamebook = len(re.findall(r'^\[ChapterMode "gamebook"\]', texto_do_estudo, flags=re.MULTILINE))
    total = len(re.findall(r"^\[Event ", texto_do_estudo, flags=re.MULTILINE))
    modos = [c.mode for c in estudo.chapters]
    # todos os capítulos `gamebook` da fixture têm lances, então nenhum vira `read`;
    # um capítulo comum (posição própria + linha curta) vira exercício pela heurística
    assert gamebook == 15 and total == 27
    assert modos.count("gamebook") == 16
    assert modos.count("read") == 11


def test_nenhum_capitulo_da_fixture_foi_pulado(estudo):
    assert [c.name for c in estudo.chapters if c.skipped_reason] == []


def test_nomes_e_urls_dos_capitulos(estudo):
    primeiro = estudo.chapters[0]
    assert primeiro.name == "Exercício (peça sem defesa - aluno)"
    assert primeiro.lichess_url == "https://lichess.org/study/4JKVAfaE/Pt2y3ild"


# --- primeiro capítulo (gamebook completo) -------------------------------


def test_primeiro_capitulo_fen_e_orientacao(estudo):
    cap = estudo.chapters[0]
    assert cap.mode == "gamebook"
    assert cap.fen.endswith("b kq - 2 10")
    # sem header [Orientation], vale o lado a mover
    assert cap.orientation == "black"


def test_primeiro_capitulo_lances_alternam_solver_e_engine(estudo):
    cap = estudo.chapters[0]
    esperados = ucis_de_sans(cap.fen, ["Qb6+", "Kh1", "Qxb5"])
    moves = cap.solution["moves"]
    assert [m["uci"] for m in moves] == esperados
    assert moves[0]["uci"] == "d8b6"
    assert [m["by"] for m in moves] == ["solver", "engine", "solver"]
    assert all(m["alternatives"] == [] for m in moves)
    assert cap.solution["explanation_pv"] == []


def test_primeiro_capitulo_intro_e_comentarios(estudo):
    cap = estudo.chapters[0]
    assert "acabaram de rocar" in cap.intro_comment
    assert "acabaram de rocar" in cap.solution["intro"]
    assert "alinhamento" in cap.solution["comments"]["0"]
    # nós sem comentário não entram no dicionário
    assert "1" not in cap.solution["comments"]


def test_primeiro_capitulo_wrong_moves_so_com_comentario(estudo):
    cap = estudo.chapters[0]
    errados = cap.solution["wrong_moves"]
    assert errados["e8g8"] == "Assim seguiu a partida..."
    # a variação 10... Bg6 não tem comentário, então é ignorada
    assert "f5g6" not in errados


def test_capitulo_sem_setas_nao_traz_shapes(estudo):
    assert "shapes" not in estudo.chapters[0].solution


# --- capítulos de leitura ------------------------------------------------


def test_capitulos_read_nao_tem_solucao(estudo):
    leitura = [c for c in estudo.chapters if c.mode == "read"]
    assert leitura
    assert all(c.solution is None for c in leitura)
    assert all(c.pgn.strip() for c in leitura)


def test_capitulo_sem_lances_e_read(estudo):
    cap = capitulo_por_url(estudo, "/kM4x3MjK")
    assert cap.name == "Pratique mais nos links da descrição"
    assert cap.mode == "read"
    assert cap.solution is None


def test_capitulo_de_um_lance_so_tem_solver(estudo):
    cap = capitulo_por_url(estudo, "/NwWrHT4Y")
    esperados = ucis_de_sans(cap.fen, ["Qh5#"])
    assert [m["uci"] for m in cap.solution["moves"]] == esperados
    assert [m["by"] for m in cap.solution["moves"]] == ["solver"]


# --- clean_comment -------------------------------------------------------


def test_clean_comment_remove_comandos_e_normaliza_espacos():
    bruto = "Boa jogada { } [%eval 1.85] [%clk 0:09:20]  [%cal Gf6d5,Bf6g8][%csl Rb5]\n mesmo"
    assert clean_comment(bruto) == "Boa jogada { } mesmo"


def test_clean_comment_de_texto_vazio():
    assert clean_comment("") == ""
    assert clean_comment("  [%eval 0.1]  ") == ""


# --- casos sintéticos ----------------------------------------------------

CABECALHO_SINTETICO = """[Event "Estudo de teste: {nome}"]
[StudyName "Estudo de teste"]
[ChapterName "{nome}"]
[ChapterURL "https://lichess.org/study/ABCD1234/EFGH5678"]
[Annotator "https://lichess.org/@/fulano"]
"""


def pgn_sintetico(nome: str, movimentos: str, extras: str = "") -> str:
    cabecalho = CABECALHO_SINTETICO.format(nome=nome)
    if extras:
        cabecalho += extras.rstrip("\n") + "\n"
    return cabecalho + "\n" + movimentos + "\n\n"


def test_lance_ilegal_marca_skipped_reason():
    texto = pgn_sintetico(
        "Linha quebrada",
        "1. e4 e5 2. Qh8 *",
        extras='[ChapterMode "gamebook"]',
    )
    estudo = parse_study_pgn(texto)
    cap = estudo.chapters[0]
    assert cap.skipped_reason
    assert "Qh8" in cap.skipped_reason
    assert cap.solution is None
    # sem solução não há exercício: o capítulo vale como leitura, e não como gamebook
    assert cap.mode == "read"


def test_fen_invalida_marca_skipped_reason():
    texto = pgn_sintetico(
        "FEN quebrada",
        "*",
        extras='[FEN "isso nao e uma fen"]\n[SetUp "1"]\n[ChapterMode "gamebook"]',
    )
    cap = parse_study_pgn(texto).chapters[0]
    assert cap.skipped_reason
    assert cap.solution is None
    assert cap.mode == "read"


def test_sem_chapter_mode_vira_read():
    texto = pgn_sintetico("Partida comentada", "1. e4 e5 *")
    cap = parse_study_pgn(texto).chapters[0]
    assert cap.mode == "read"
    assert cap.solution is None
    assert cap.fen == chess.STARTING_FEN
    assert cap.orientation == "white"


def test_gamebook_sem_lances_vira_read():
    texto = pgn_sintetico("Só texto", "{ Leia isto } *", extras='[ChapterMode "gamebook"]')
    cap = parse_study_pgn(texto).chapters[0]
    assert cap.mode == "read"
    assert cap.solution is None
    assert cap.intro_comment == "Leia isto"


def test_orientation_do_header_prevalece_sobre_o_lado_a_mover():
    texto = pgn_sintetico("De ponta cabeça", "1. e4 *", extras='[Orientation "Black"]')
    cap = parse_study_pgn(texto).chapters[0]
    assert cap.orientation == "black"


def test_titulo_e_nome_vem_do_event_quando_faltam_headers():
    texto = (
        '[Event "Meu estudo: Capítulo 1"]\n'
        '[Annotator "https://lichess.org/@/ciclano"]\n'
        "\n1. e4 *\n\n"
    )
    estudo = parse_study_pgn(texto)
    assert estudo.title == "Meu estudo"
    assert estudo.author == "ciclano"
    assert estudo.lichess_id is None
    assert estudo.chapters[0].name == "Capítulo 1"
    assert estudo.chapters[0].lichess_url is None


def test_shapes_de_cal_e_csl_com_os_pinceis_certos():
    movimentos = (
        "{ Olhe a casa [%csl Ge4] } "
        "1. e4 { Avanço [%cal Ge2e4,Rd1h5][%csl Yd5] } "
        "1... e5 { [%cal Bb8c6] } 2. Nf3 *"
    )
    texto = pgn_sintetico("Setas", movimentos, extras='[ChapterMode "gamebook"]')
    cap = parse_study_pgn(texto).chapters[0]
    shapes = cap.solution["shapes"]
    # setas do nó raiz (posição inicial) ficam sob a chave "start"
    assert shapes["start"] == [{"orig": "e4", "brush": "green"}]
    assert shapes["0"] == [
        {"orig": "e2", "dest": "e4", "brush": "green"},
        {"orig": "d1", "dest": "h5", "brush": "red"},
        {"orig": "d5", "brush": "yellow"},
    ]
    assert shapes["1"] == [{"orig": "b8", "dest": "c6", "brush": "blue"}]
    assert cap.solution["intro"] == "Olhe a casa"
    assert cap.solution["comments"]["0"] == "Avanço"
    assert "1" not in cap.solution["comments"]


def test_wrong_moves_ignora_variacoes_do_lado_do_engine():
    movimentos = "1. e4 (1. d4 { Também dá }) 1... e5 (1... c5 { Siciliana }) 2. Nf3 *"
    texto = pgn_sintetico("Variações", movimentos, extras='[ChapterMode "gamebook"]')
    cap = parse_study_pgn(texto).chapters[0]
    # solver são as brancas (lance 0 e 2); a variação 1... c5 é do engine
    assert cap.solution["wrong_moves"] == {"d2d4": "Também dá"}


def test_varios_capitulos_no_mesmo_pgn():
    texto = pgn_sintetico("Um", "1. e4 *", extras='[ChapterMode "gamebook"]') + pgn_sintetico(
        "Dois", "1. d4 *"
    )
    estudo = parse_study_pgn(texto)
    assert [c.name for c in estudo.chapters] == ["Um", "Dois"]
    assert [c.order for c in estudo.chapters] == [1, 2]
    assert [c.mode for c in estudo.chapters] == ["gamebook", "read"]


def test_id_local_vem_do_header_do_exportador_daqui():
    """`[ChessTrainerStudy]` é o que faz o PGN exportado aqui, colado de volta,
    reencontrar o estudo que o gerou."""
    texto = pgn_sintetico("Um", "1. e4 *", extras='[ChessTrainerStudy "abc123"]')
    assert parse_study_pgn(texto).local_id == "abc123"


def test_header_vazio_ou_de_interrogacao_nao_vira_id_local():
    assert parse_study_pgn(pgn_sintetico("Um", "1. e4 *", extras='[ChessTrainerStudy ""]')).local_id is None
    assert parse_study_pgn(pgn_sintetico("Um", "1. e4 *", extras='[ChessTrainerStudy "?"]')).local_id is None
    assert parse_study_pgn(pgn_sintetico("Um", "1. e4 *")).local_id is None


def test_pgn_vazio_nao_tem_capitulos():
    estudo = parse_study_pgn("   \n\n")
    assert estudo.chapters == []
    assert estudo.title == ""
    assert estudo.lichess_id is None


def test_pgn_do_capitulo_preserva_headers_e_lances():
    texto = pgn_sintetico("Um", "1. e4 { Nota } *", extras='[ChapterMode "gamebook"]')
    cap = parse_study_pgn(texto).chapters[0]
    assert '[ChapterMode "gamebook"]' in cap.pgn
    assert "e4" in cap.pgn
    assert "Nota" in cap.pgn


# --- lado do aluno (solver) ----------------------------------------------

# peão passado contra o rei: dá linhas curtas e legais dos dois lados
FEN_BRANCAS = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"
FEN_PRETAS = "4k3/8/8/8/8/4P3/8/4K3 b - - 0 1"


def exercicio_sintetico(movimentos: str, fen: str = FEN_BRANCAS, extras: str = "") -> ParsedChapter:
    """Capítulo gamebook de uma posição própria, para os casos de cada regra."""
    cabecalho = "\n".join([f'[FEN "{fen}"]', '[SetUp "1"]', '[ChapterMode "gamebook"]'])
    if extras:
        cabecalho += "\n" + extras
    return parse_study_pgn(pgn_sintetico("Exercício", movimentos, extras=cabecalho)).chapters[0]


def lances(cap: ParsedChapter) -> list[tuple[str, str]]:
    return [(m["uci"], m["by"]) for m in cap.solution["moves"]]


def test_enunciado_decide_o_lado_do_aluno():
    # regra 1: a FEN é das brancas, mas o enunciado entrega o exercício às pretas
    cap = exercicio_sintetico("{ Jogam as pretas } 1. e4 Kd7 2. e5")
    assert cap.intro_move == "e2e4"
    assert lances(cap) == [("e8d7", "solver"), ("e4e5", "engine")]


def test_comentario_do_primeiro_lance_tambem_decide():
    # regra 1, sem depender de maiúsculas nem de acentos no resto do texto
    cap = exercicio_sintetico("{ Atenção! } 1. e4 { NEGRAS JOGAM } Kd7 2. e5")
    assert cap.intro_move == "e2e4"
    assert lances(cap) == [("e8d7", "solver"), ("e4e5", "engine")]


def test_texto_em_ingles_decide():
    cap = exercicio_sintetico("{ White to play } 1... Kd7 2. e4 Kc6", FEN_PRETAS)
    assert cap.intro_move == "e8d7"
    assert lances(cap) == [("e3e4", "solver"), ("d7c6", "engine")]


def test_resultado_decide_quando_o_texto_nao_diz():
    # regra 3: FEN e primeiro lance das pretas, mas o 1-0 diz que o exercício é das brancas
    cap = exercicio_sintetico("1... Kd7 2. e4 Kc6", FEN_PRETAS, extras='[Result "1-0"]')
    assert cap.intro_move == "e8d7"
    assert lances(cap) == [("e3e4", "solver"), ("d7c6", "engine")]


def test_ultimo_lance_decide_sem_texto_nem_resultado():
    # regra 4: o autor para depois do lance do aluno, então uma linha de número
    # par de meios-lances termina no lado oposto ao da FEN
    cap = exercicio_sintetico("1. e4 Kd7", extras='[Result "1/2-1/2"]')
    assert cap.intro_move == "e2e4"
    assert lances(cap) == [("e8d7", "solver")]


# torre contra rei encurralado: duas linhas curtas e legais sem resultado declarado
FEN_TORRE = "6k1/8/8/8/8/8/8/R3K3 w - - 0 1"


def test_linha_de_dois_meios_lances_sem_texto_nem_resultado_vira_introducao():
    """Regra 4 com `Result "*"`: a linha para depois do lance das pretas, então o
    exercício é delas e `Ra8+` vira introdução. Decisão registrada de propósito —
    é ela que o salvamento no editor não pode desfazer sozinho (regra 2)."""
    cap = exercicio_sintetico("1. Ra8+ Kh7", FEN_TORRE, extras='[Result "*"]')
    assert cap.intro_move == "a1a8"
    assert lances(cap) == [("g8h7", "solver")]
    # e o tabuleiro abre do lado do aluno
    assert cap.orientation == "black"


def test_lado_recebido_de_fora_vence_o_resultado_e_o_ultimo_lance():
    """Regra 2: com o lado do aluno vindo de fora (o exercício já gravado), nem o
    `[Result]` nem o último lance da linha invertem o exercício."""
    texto = pgn_sintetico("Exercício", '1... Kd7 2. e4 Kc6',
                          extras="\n".join([f'[FEN "{FEN_PRETAS}"]', '[SetUp "1"]',
                                             '[ChapterMode "gamebook"]', '[Result "1-0"]']))
    game = chess.pgn.read_game(io.StringIO(texto))
    # sem o lado de fora, o 1-0 entrega o exercício às brancas (regra 3)
    assert solution_from_game(game).intro_move == "e8d7"
    # com ele, as pretas continuam donas do exercício
    exercicio = solution_from_game(game, chess.BLACK)
    assert exercicio.intro_move is None
    assert [(m["uci"], m["by"]) for m in exercicio.solution["moves"]] == [
        ("e8d7", "solver"), ("e3e4", "engine"), ("d7c6", "solver"),
    ]


def test_texto_do_autor_vence_o_lado_recebido_de_fora():
    """Regra 1 continua acima da 2: o autor corrigiu o enunciado no editor."""
    texto = pgn_sintetico("Exercício", '{ Jogam as pretas } 1. e4 Kd7 2. e5',
                          extras="\n".join([f'[FEN "{FEN_BRANCAS}"]', '[SetUp "1"]',
                                             '[ChapterMode "gamebook"]']))
    game = chess.pgn.read_game(io.StringIO(texto))
    exercicio = solution_from_game(game, chess.WHITE)
    assert exercicio.intro_move == "e2e4"


def test_sem_nenhum_sinal_vale_o_lado_a_jogar_na_fen():
    # regra 5: linha ímpar, sem texto e sem resultado — nada muda
    cap = exercicio_sintetico("1. e4 Kd7 2. e5")
    assert cap.intro_move is None
    assert lances(cap) == [("e2e4", "solver"), ("e8d7", "engine"), ("e4e5", "solver")]


def test_linha_de_um_lance_so_nao_vira_introducao():
    # deslocar deixaria o aluno sem nada para jogar: a linha fica como está
    cap = exercicio_sintetico("{ Jogam as pretas } 1. e4")
    assert cap.intro_move is None
    assert lances(cap) == [("e2e4", "solver")]


def test_enunciado_e_marcacoes_acompanham_o_lance_de_introducao():
    movimentos = ("{ Ache o plano [%csl Ge4] } 1. e4 { Jogam as pretas [%cal Ge2e4] } "
                  "Kd7 { Aproxima o rei [%csl Rd7] } 2. e5")
    cap = exercicio_sintetico(movimentos)
    assert cap.intro_move == "e2e4"
    # o comentário do lance de introdução vira enunciado e as setas dele passam a
    # ser as da posição em que o aluno começa
    assert cap.solution["intro"] == "Ache o plano\n\nJogam as pretas"
    assert cap.solution["shapes"]["start"] == [
        {"orig": "e4", "brush": "green"},
        {"orig": "e2", "dest": "e4", "brush": "green"},
    ]
    # os índices andam junto: o comentário do lance do aluno é o "0"
    assert cap.solution["comments"] == {"0": "Aproxima o rei"}
    assert cap.solution["shapes"]["0"] == [{"orig": "d7", "brush": "red"}]


def test_variacoes_comentadas_seguem_o_lado_do_aluno():
    movimentos = "{ Jogam as pretas } 1. e4 Kd7 (1... Kf7 { Longe demais }) 2. e5"
    cap = exercicio_sintetico(movimentos)
    assert cap.solution["wrong_moves"] == {"e8f7": "Longe demais"}


def test_capitulo_com_lance_de_introducao_do_adversario(estudo):
    """QtPYhPsi: FEN das brancas, `34. Re4 { Jogam as pretas }` e resultado 0-1.
    O exercício é das pretas e começa depois do lance das brancas."""
    cap = capitulo_por_url(estudo, "/QtPYhPsi")
    assert cap.fen.startswith("2r3k1/6bp/3pr1p1/2q5/1R3P2/5PP1/7K/3QBR2 w")
    assert cap.intro_move == "b4e4"
    moves = cap.solution["moves"]
    assert (moves[0]["uci"], moves[0]["by"]) == ("c5h5", "solver")
    assert (moves[-1]["uci"], moves[-1]["by"]) == ("g7d4", "solver")
    assert [m["by"] for m in moves] == ["solver", "engine"] * 4 + ["solver"]
    assert cap.solution["intro"] == "Jogam as pretas"


def test_orientacao_segue_o_aluno_quando_ha_lance_de_introducao(estudo):
    """QtPYhPsi não declara `[Orientation]` e a FEN é das brancas, mas o aluno é
    das pretas: o tabuleiro abre do lado dele."""
    cap = capitulo_por_url(estudo, "/QtPYhPsi")
    assert cap.intro_move == "b4e4"
    assert cap.orientation == "black"
    assert cap.tree["orientation"] == "black"


def test_nenhum_gamebook_da_fixture_termina_no_engine(estudo):
    """O sinal do bug: exercício que acaba com lance do adversário. Sobram só os
    capítulos em que o texto do autor manda a linha continuar depois do aluno."""
    invertidos = [cap.name for cap in estudo.chapters
                  if cap.solution and cap.solution["moves"][-1]["by"] == "engine"]
    assert invertidos == []


def test_capitulos_da_fixture_que_ganharam_lance_de_introducao(estudo):
    """Os 11 capítulos deste estudo em que o aluno não é o lado a jogar na FEN:
    dez pelo texto ou pelo resultado, e o "Exemplo - Sobrecarga" (MjDMl1jz) pelo
    último lance da linha."""
    com_introducao = {cap.lichess_url.rsplit("/", 1)[-1]: cap.intro_move
                      for cap in estudo.chapters if cap.intro_move}
    assert com_introducao == {
        "jplGgITX": "e7c5", "jqdDO7BG": "g7h6", "bdvmPuaP": "c6c5", "d5GqFvzD": "f6e8",
        "Xsy3fEHM": "e6c5", "6bG9tWYf": "g6h5", "rLEIPsYy": "g7h6", "cn9ywxGv": "e8f8",
        "0ROSVAVW": "d3c4", "QtPYhPsi": "b4e4", "MjDMl1jz": "a2a1",
    }


# --- árvore de lances ----------------------------------------------------


def test_capitulo_traz_a_arvore_de_lances(estudo):
    cap = estudo.chapters[0]
    assert cap.tree["fen"] == cap.fen
    assert cap.tree["orientation"] == cap.orientation
    assert cap.tree["intro"] == cap.intro_comment
    assert [n["san"] for n in cap.tree["root"]["children"]] == ["Qb6+", "O-O", "Bg6"]
    assert cap.tree["root"]["children"][0]["uci"] == "d8b6"


def test_todos_os_capitulos_lidos_tem_arvore(estudo):
    assert all(c.tree is not None for c in estudo.chapters)


def test_capitulo_de_leitura_tambem_tem_arvore(estudo):
    cap = capitulo_por_url(estudo, "/kM4x3MjK")
    assert cap.mode == "read" and cap.tree == {
        "fen": cap.fen, "orientation": cap.orientation, "intro": cap.intro_comment,
        "root": {"shapes": [], "children": []},
    }


def test_capitulo_com_fen_invalida_fica_sem_arvore():
    texto = pgn_sintetico(
        "FEN quebrada",
        "*",
        extras='[FEN "isso nao e uma fen"]\n[SetUp "1"]\n[ChapterMode "gamebook"]',
    )
    cap = parse_study_pgn(texto).chapters[0]
    assert cap.tree is None


def test_solution_from_game_e_a_funcao_publica_da_solucao(estudo, texto_do_estudo):
    game = chess.pgn.read_game(io.StringIO(texto_do_estudo))
    exercicio = solution_from_game(game)
    assert exercicio.solution == estudo.chapters[0].solution
    assert exercicio.intro_move is None


def test_capitulo_comum_com_posicao_propria_e_linha_curta_vira_exercicio():
    texto = pgn_sintetico(
        "Exemplo",
        "1... Qxf6 2. Qxf6 Re1+ 3. Bf1 Rxf1+ 4. Rxf1 f2+ 5. Qf3 Bxf3# *",
        extras='[FEN "2k1r3/1pp2p2/p2p1B1p/3b2q1/1P4p1/2QB1pP1/P4R1P/7K b - - 0 1"]\n[SetUp "1"]',
    )
    cap = parse_study_pgn(texto).chapters[0]
    assert cap.mode == "gamebook" and cap.solution is not None
    assert cap.solution["moves"][0]["uci"] == "g5f6" and cap.solution["moves"][0]["by"] == "solver"


def test_partida_inteira_da_posicao_inicial_continua_leitura():
    texto = pgn_sintetico("Partida", "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *")
    cap = parse_study_pgn(texto).chapters[0]
    assert cap.mode == "read" and cap.solution is None


def test_posicao_propria_com_linha_longa_continua_leitura():
    # cavalos dos dois lados vão e voltam: 28 meios-lances legais, acima do teto
    passos = ["Nf3 Nf6", "Ng1 Ng8"] * 7
    linha = " ".join(f"{i + 1}. {par}" for i, par in enumerate(passos)) + " *"
    texto = pgn_sintetico("Longa", linha, extras='[FEN "4k1n1/8/8/8/8/8/8/4K1N1 w - - 0 1"]\n[SetUp "1"]')
    cap = parse_study_pgn(texto).chapters[0]
    # é o teto de lances que decide, não um lance ilegal
    assert cap.skipped_reason is None
    assert cap.mode == "read" and cap.solution is None


def test_posicao_propria_dentro_do_teto_vira_exercicio():
    passos = ["Nf3 Nf6", "Ng1 Ng8"] * 6  # 24 meios-lances: no limite
    linha = " ".join(f"{i + 1}. {par}" for i, par in enumerate(passos)) + " *"
    texto = pgn_sintetico("Curta", linha, extras='[FEN "4k1n1/8/8/8/8/8/8/4K1N1 w - - 0 1"]\n[SetUp "1"]')
    cap = parse_study_pgn(texto).chapters[0]
    assert cap.skipped_reason is None and cap.mode == "gamebook"


def test_aspas_escapadas_nos_headers_sao_desfeitas():
    texto = pgn_sintetico("Exercicio", "1. e4 *", extras='[ChapterName "Brancas jogam (\\"pegadinha\\")"]\n[StudyName "Tática \\"dupla\\""]')
    estudo = parse_study_pgn(texto)
    assert estudo.chapters[0].name == 'Brancas jogam ("pegadinha")'
    assert estudo.title == 'Tática "dupla"'


# --- PGN comum (coleção de partidas) -------------------------------------

PGN_DE_PARTIDAS = """[Event "Linares"]
[Date "1993.??.??"]
[White "Kasparov, Garry"]
[Black "Karpov, Anatoly"]
[Result "*"]

1. e4 e5 *

[Event "?"]
[Date "????.??.??"]
[White "Kasparov, Garry"]
[Black "Karpov, Anatoly"]
[Result "*"]

1. d4 d5 *
"""


def test_pgn_comum_titulo_vem_do_torneio_do_primeiro_jogo():
    estudo = parse_study_pgn(PGN_DE_PARTIDAS)
    assert estudo.title == "Linares"
    assert estudo.author == "" and estudo.lichess_id is None


def test_pgn_comum_um_capitulo_por_partida_com_jogadores_no_nome():
    estudo = parse_study_pgn(PGN_DE_PARTIDAS)
    assert [c.name for c in estudo.chapters] == [
        "Kasparov, Garry × Karpov, Anatoly (Linares, 1993)",
        "Kasparov, Garry × Karpov, Anatoly",
    ]
    # partida inteira da posição inicial: capítulo de leitura
    assert [c.mode for c in estudo.chapters] == ["read", "read"]


def test_pgn_comum_sem_torneio_ganha_titulo_generico():
    texto = '[Event "?"]\n[White "?"]\n[Black "?"]\n[Result "*"]\n\n1. e4 *\n\n'
    estudo = parse_study_pgn(texto)
    assert estudo.title == "PGN importado"
    assert estudo.chapters[0].name == "Capítulo 1"


def test_pgn_comum_sem_jogadores_usa_o_torneio_como_nome_do_capitulo():
    texto = '[Event "Linares"]\n[White "?"]\n[Black "?"]\n[Result "*"]\n\n1. e4 *\n\n'
    assert parse_study_pgn(texto).chapters[0].name == "Linares"


def test_pgn_comum_com_jogadores_e_so_o_ano():
    texto = ('[Event "?"]\n[Date "1993.05.10"]\n[White "Kasparov, Garry"]\n'
             '[Black "Karpov, Anatoly"]\n[Result "*"]\n\n1. e4 *\n\n')
    cap = parse_study_pgn(texto).chapters[0]
    assert cap.name == "Kasparov, Garry × Karpov, Anatoly (1993)"
