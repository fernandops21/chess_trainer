import json

import chess

from chess_trainer.coach.tools import (ContextoExercicio, contexto_do_exercicio, fatos_taticos,
                                      ferramentas_do_treinador)
from chess_trainer.core.evals import CLAMP_CP, MATE_SCORE
from chess_trainer.core.models import Game, Position
from tests.factories import make_puzzle

FEN_ERRO = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3"   # pretas jogam Nf6??
FEN = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"        # exercício: Qxf7#
# posição de uma partida do aluno depois de 32...Qh3: a ameaça é Qxf1#, não Qxh2#
FEN_FATOS = "5R2/2p3pk/2pp3p/4p3/1P6/2PPbPrq/7P/5Q1K w - - 4 33"
# a mesma depois de 33.Rh8+: as pretas estão em xeque
FEN_FATOS_XEQUE = "7R/2p3pk/2pp3p/4p3/1P6/2PPbPrq/7P/5Q1K b - - 5 33"
# três damas e uma torre contra o rei sozinho: mais xeques do que o limite das listas
FEN_MUITOS_XEQUES = "7k/8/8/8/QQQ5/8/2R5/7K w - - 0 1"
PGN = '[Event "x"]\n[White "eu"]\n[Black "ele"]\n[Result "1-0"]\n\n1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0'


def puzzle_punir(db):
    game = Game(source_id="g-1", pgn=PGN, white="eu", black="ele", result="1-0", time_control="600", category="rapid",
                played_at=__import__("datetime").datetime(2026, 8, 1), my_color="white")
    db.add(game)
    db.flush()
    # `eval_before/eval_after` são do ponto de vista de quem jogou: no ply 6 quem joga são as pretas
    pos = Position(game_id=game.id, ply=6, fen=FEN_ERRO, move_played="Nf6", move_uci="g8f6", eval_before=-150,
                   eval_after=-(MATE_SCORE - 1),
                   best_move="g7g6", best_eval=-150, is_mistake=True, mistake_level="blunder", mistake_by="opponent")
    db.add(pos)
    db.flush()
    db.add(Position(game_id=game.id, ply=7, fen=FEN, move_played="Qxf7#", move_uci="h5f7", eval_before=MATE_SCORE - 1,
                    eval_after=MATE_SCORE, best_move="h5f7", best_eval=MATE_SCORE, is_mistake=False))
    from chess_trainer.core.models import Puzzle
    p = Puzzle(position_id=pos.id, game_id=game.id, kind="punish", fen_start=FEN, side_to_move="white",
               solution=json.dumps({"moves": [{"uci": "h5f7", "by": "solver", "alternatives": []}], "explanation_pv": []}),
               end_reason="mate", theme="mate_in_1", category="rapid", solver_moves=1)
    db.add(p)
    db.commit()
    return p


def test_contexto_de_um_punir_com_partida(db_session):
    p = puzzle_punir(db_session)
    ctx = contexto_do_exercicio(db_session, p)
    assert ctx.tipo == "punir" and ctx.lado == "brancas" and ctx.fen_inicial == FEN and ctx.fen_erro == FEN_ERRO
    assert ctx.solucao_san == ["Qxf7#"] and ctx.tema == "mate em 1"
    # avaliações do banco (ponto de vista de quem jogou) viradas para o ponto de vista das brancas
    assert ctx.lance_errado == {"san": "Nf6", "uci": "g8f6", "de_quem": "adversário", "nivel": "blunder",
                                "aval_antes": 150, "aval_depois": MATE_SCORE - 1}
    assert ctx.minha_resposta == {"san": "Qxf7#", "uci": "h5f7", "achou": True, "aval_antes": MATE_SCORE - 1, "aval_depois": MATE_SCORE}
    assert ctx.partida["brancas"] == "eu" and ctx.partida["meu_lado"] == "brancas"
    assert ctx.partida["lances_em_volta"] == "1.e4 e5 2.Qh5 Nc6 3.Bc4 Nf6 4.Qxf7#"
    # a abertura são só os 6 primeiros plies, no formato dos caminhos dos trechos dos estudos
    assert ctx.abertura == "1.e4 e5 2.Qh5 Nc6 3.Bc4 Nf6"
    assert ctx.lances_permitidos == {"h5f7", "g8f6"}
    texto = ctx.texto()
    assert "Qxf7#" in texto and "Nf6" in texto and "FEN" in texto
    assert "+1.50 → #1" in texto and "ponto de vista das brancas" in texto
    assert json.loads(json.dumps(ctx.to_dict()))["tipo"] == "punir"


def test_contexto_de_um_evitar_sem_resposta(db_session):
    p = make_puzzle(db_session, fen=FEN, kind="avoid", move_played="Qh5", move_uci="d1h5", mistake_by="me")
    ctx = contexto_do_exercicio(db_session, p)
    assert ctx.tipo == "evitar" and ctx.lance_errado["de_quem"] == "você" and ctx.minha_resposta is None
    assert "a2a4" in ctx.lances_permitidos and "d1h5" in ctx.lances_permitidos
    # ply 1: quem jogou foram as brancas, então as avaliações da factory não mudam de sinal
    assert ctx.lance_errado["aval_antes"] == 0 and ctx.lance_errado["aval_depois"] == -300


def test_ferramentas_do_treinador(db_session):
    p = puzzle_punir(db_session)
    ctx = contexto_do_exercicio(db_session, p)

    def analisar(fen, multipv):
        return {"fen": fen, "turn": "white", "terminal": None,
                "lines": [{"move": "h5f7", "san": "Qxf7#", "score": MATE_SCORE - 1, "pv": ["h5f7"], "pv_san": ["Qxf7#"]}][:multipv]}

    buscas = []
    ferr = ferramentas_do_treinador(ctx, analisar, estatisticas=lambda dias: [{"theme": "fork", "label": "garfo", "attempts": 3, "accuracy": 0.5}],
                                    buscar=lambda consulta, k: buscas.append((consulta, k)) or [{"chunk_id": "ab12", "texto": "t"}])
    por_nome = {f.nome: f for f in ferr}
    assert set(por_nome) == {"analisar_posicao", "fatos_taticos", "contexto_do_exercicio", "estatisticas_por_tema", "buscar_estudos"}
    fatos = json.loads(por_nome["fatos_taticos"].fn({"fen": FEN}))
    assert fatos["mates_em_1"] == ["Qxf7#"] and "sem engine" in por_nome["fatos_taticos"].descricao
    linhas = json.loads(por_nome["analisar_posicao"].fn({"fen": FEN, "multipv": 1}))
    # o mate não vai como código interno (±(MATE_SCORE - n)): vira `mate_em` assinado
    linha = linhas["linhas"][0]
    assert linha["lance"] == "Qxf7#" and linha["mate_em"] == 1 and linha["avaliacao_cp"] is None
    assert linha["avaliacao"] == "#1" and linha["continuacao"] == ["Qxf7#"]
    # com as pretas a mover, o score do lado a mover vira negativo para as brancas: são elas que dão o mate
    linhas2 = json.loads(por_nome["analisar_posicao"].fn({"fen": FEN_ERRO, "multipv": 1}))
    assert linhas2["linhas"][0]["mate_em"] == -1 and linhas2["linhas"][0]["avaliacao_cp"] is None
    assert linhas2["linhas"][0]["avaliacao"] == "#-1"
    # sem mate, `avaliacao_cp` vem em centipeões limitados e `mate_em` nulo
    def analisar_cp(fen, multipv):
        return {"fen": fen, "turn": "white", "terminal": None,
                "lines": [{"move": "h5f7", "san": "Qxf7", "score": 9_000, "pv": ["h5f7"], "pv_san": ["Qxf7"]}][:multipv]}

    cp = json.loads({f.nome: f for f in ferramentas_do_treinador(ctx, analisar_cp, None, None)}["analisar_posicao"]
                    .fn({"fen": FEN, "multipv": 1}))["linhas"][0]
    assert cp["avaliacao_cp"] == CLAMP_CP and cp["mate_em"] is None and cp["avaliacao"] == "+90.00"
    assert json.loads(por_nome["contexto_do_exercicio"].fn({}))["tipo"] == "punir"
    assert json.loads(por_nome["estatisticas_por_tema"].fn({"dias": 30}))[0]["label"] == "garfo"
    assert json.loads(por_nome["buscar_estudos"].fn({"consulta": "garfo", "k": 2}))[0]["chunk_id"] == "ab12" and buscas == [("garfo", 2)]
    # sem busca disponível, a ferramenta não existe
    assert "buscar_estudos" not in {f.nome for f in ferramentas_do_treinador(ctx, analisar, None, None)}
    # FEN inválida vira erro de ferramenta (o cliente empacota), não exceção sem tratamento
    import pytest
    with pytest.raises(ValueError):
        por_nome["analisar_posicao"].fn({"fen": "lixo", "multipv": 1})


def test_fatos_taticos_da_posicao_da_ameaca_real():
    """O caso que motivou a ferramenta: o modelo escreveu que a ameaça era Qxh2#
    (só xeque); a ameaça exata é Qxf1#, e as brancas não têm casa para o rei."""
    f = fatos_taticos(FEN_FATOS)
    assert f["fen"] == chess.Board(FEN_FATOS).fen() and f["lado_a_mover"] == "brancas"
    assert f["em_xeque"] is False and f["lances_do_rei"] == [] and f["mates_em_1"] == []
    assert f["xeques"] == ["Rh8+"]
    assert f["ameacas_do_adversario"]["mates_em_1"] == ["Qxf1#"]
    assert "Qxf1#" in f["ameacas_do_adversario"]["capturas_de_pecas_indefesas"]
    # a dama das brancas em f1 está atacada pela dama preta de h3 e ninguém a defende
    assert {"casa": "f1", "peca": "dama branca", "atacada_por": ["h3"]} in f["pecas_atacadas_sem_defesa"]
    assert json.loads(json.dumps(f))["em_xeque"] is False


def test_fatos_taticos_em_xeque_nao_tem_ameacas_do_adversario():
    f = fatos_taticos(FEN_FATOS_XEQUE)
    assert f["em_xeque"] is True and f["lado_a_mover"] == "pretas"
    assert f["lances_do_rei"] == ["Kxh8", "Kg6"]
    # em xeque não existe "se fosse a vez dele": o lance nulo é ilegal
    assert f["ameacas_do_adversario"] == {"mates_em_1": [], "capturas_de_pecas_indefesas": []}


def test_fatos_taticos_do_mate_do_pastor():
    f = fatos_taticos(FEN)
    assert f["mates_em_1"] == ["Qxf7#"] and "Qxf7#" in f["xeques"]
    # f7 é defendido pelo rei, então o mate não conta como captura de peça indefesa
    assert f["capturas_de_pecas_indefesas"] == []
    # a dama das brancas em h5 está atacada pelo cavalo de f6 e sem defensor
    assert f["pecas_atacadas_sem_defesa"] == [{"casa": "h5", "peca": "dama branca", "atacada_por": ["f6"]}]
    assert f["ameacas_do_adversario"]["capturas_de_pecas_indefesas"] == ["Nxh5", "Nxe4"]


def test_fatos_taticos_limita_as_listas_e_recusa_fen_invalida():
    import pytest
    assert len(fatos_taticos(FEN_MUITOS_XEQUES)["xeques"]) == 12
    with pytest.raises(ValueError):
        fatos_taticos("lixo")
