import json

import chess

from chess_trainer.coach.tools import (ContextoExercicio, contexto_do_exercicio, fatos_taticos,
                                      ferramentas_do_treinador, saldo_material)
from chess_trainer.core.evals import CLAMP_CP, MATE_SCORE
from chess_trainer.core.models import Game, Position
from tests.factories import make_puzzle

FEN_ERRO = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3"   # pretas jogam Nf6??
FEN = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"        # exercício: Qxf7#
# posição de uma partida do aluno depois de 32...Qh3: a ameaça é Qxf1#, não Qxh2#
FEN_FATOS = "5R2/2p3pk/2pp3p/4p3/1P6/2PPbPrq/7P/5Q1K w - - 4 33"
# a mesma depois de 33.Rh8+: as pretas estão em xeque
FEN_FATOS_XEQUE = "7R/2p3pk/2pp3p/4p3/1P6/2PPbPrq/7P/5Q1K b - - 5 33"
# brancas a jogar com o rei preto já em xeque: posição impossível, o lance nulo só esconderia
FEN_XEQUE_DO_LADO_ERRADO = "4k3/4R3/8/8/8/8/8/4K3 w - - 0 1"
# cavalo de e2 cravado pela dama de e8: na geometria ele ataca g3, mas não pode capturar
FEN_CRAVADA = "4q2k/8/8/8/8/6n1/4N3/4K3 w - - 0 1"
# três damas contra o rei sozinho: mais mates em 1 do que o limite das listas
FEN_MUITOS_MATES = "k1K5/8/8/1QQ5/8/8/8/6Q1 w - - 0 1"
# três damas e uma torre contra o rei sozinho: mais xeques do que o limite das listas
FEN_MUITOS_XEQUES = "7k/8/8/8/QQQ5/8/2R5/7K w - - 0 1"
# torre branca em d2, dama preta em d5 defendida pelo peão de c6: Rxd5 cxd5 ganha a dama pela torre
FEN_MATERIAL = "4k3/8/2p5/3q4/8/8/3R4/4K3 w - - 0 1"
# a mesma com torre preta em d5: Rxd5 cxd5 é troca igual
FEN_TROCA = "4k3/8/2p5/3r4/8/8/3R4/4K3 w - - 0 1"
# a torre branca em d3, longe do rei: se as brancas passassem a vez, Qxd3 a ganharia de graça
FEN_AMEACA = "4k3/8/2p5/3q4/8/3R4/8/4K3 w - - 0 1"
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
    # FEN do exercício tem fullmove 4, brancas a jogar: é o número que o modelo usa para
    # numerar os lances na prosa (`32...Qh3`, `33.Rh8+`)
    assert "Lance atual: 4 (brancas a jogar)" in texto
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
    # a descrição tem de avisar que as peças atacadas vêm dos dois lados
    assert "dos dois lados" in por_nome["fatos_taticos"].descricao
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


def test_analisar_posicao_apos_passar_analisa_o_lance_nulo(db_session):
    """O caso que motivou a bandeira: as ameaças do adversário são as melhores linhas
    dele na posição em que o lado a mover passa a vez (lance nulo)."""
    import pytest

    ctx = contexto_do_exercicio(db_session, puzzle_punir(db_session))
    chamadas = []

    def analisar(fen, multipv):
        chamadas.append((fen, multipv))
        b = chess.Board(fen)
        mv = next(iter(b.legal_moves))
        return {"fen": fen, "turn": "white" if b.turn else "black", "terminal": None,
                "lines": [{"move": mv.uci(), "san": b.san(mv), "score": 250, "pv": [mv.uci()], "pv_san": [b.san(mv)]}][:multipv]}

    ferramenta = {f.nome: f for f in ferramentas_do_treinador(ctx, analisar, None, None)}["analisar_posicao"]
    # FEN_ERRO: as pretas movem, então quem ameaça (e move depois do lance nulo) são as brancas
    passa = chess.Board(FEN_ERRO)
    passa.push(chess.Move.null())
    saida = json.loads(ferramenta.fn({"fen": FEN_ERRO, "multipv": 1, "apos_passar": True}))
    assert chamadas == [(passa.fen(), 1)]
    assert saida["apos_passar"] is True and saida["quem_ameaca"] == "brancas"
    assert saida["fen"] == passa.fen() and saida["lado_a_mover"] == "brancas"
    # a linha da ameaça vem no formato das outras, ponto de vista das brancas
    linha = saida["linhas"][0]
    assert set(linha) == {"lance", "avaliacao_cp", "mate_em", "avaliacao", "continuacao", "material_fim", "ganho_material"}
    assert linha["avaliacao_cp"] == 250 and linha["mate_em"] is None and linha["avaliacao"] == "+2.50"
    # sem a bandeira nada muda: analisa a posição pedida e não fala de ameaça
    chamadas.clear()
    normal = json.loads(ferramenta.fn({"fen": FEN_ERRO, "multipv": 1}))
    assert chamadas == [(chess.Board(FEN_ERRO).fen(), 1)]
    assert "apos_passar" not in normal and "quem_ameaca" not in normal and normal["lado_a_mover"] == "pretas"
    # em xeque não existe "se você passasse a vez": erro de ferramenta
    with pytest.raises(ValueError, match="passar"):
        ferramenta.fn({"fen": FEN_FATOS_XEQUE, "apos_passar": True})
    # posição impossível (xeque do lado errado) é recusada antes de o lance nulo escondê-la
    with pytest.raises(ValueError, match="impossível"):
        ferramenta.fn({"fen": FEN_XEQUE_DO_LADO_ERRADO, "apos_passar": True})
    # o esquema e a descrição avisam o modelo de quando usar a bandeira
    assert ferramenta.schema["properties"]["apos_passar"] == {"type": "boolean"}
    assert ferramenta.schema["required"] == ["fen"] and ferramenta.schema["additionalProperties"] is False
    assert "apos_passar" in ferramenta.descricao and "AMEAÇAS" in ferramenta.descricao


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
    assert sorted(f["lances_do_rei"]) == ["Kg6", "Kxh8"]
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


def test_fatos_taticos_ignora_atacante_cravado():
    """`attackers` é geometria: o cavalo de e2 está cravado pela dama de e8, então Nxg3
    é ilegal e g3 não está atacada de fato."""
    f = fatos_taticos(FEN_CRAVADA)
    assert f["capturas_de_pecas_indefesas"] == []
    casas = [x["casa"] for x in f["pecas_atacadas_sem_defesa"]]
    assert "g3" not in casas
    # o cavalo de e2 entra: depois de Nxe2 (ou Qxe2) o rei não pode recapturar, porque a
    # dama de e8 cobre a casa -- é peça do aluno pendurada de verdade
    assert casas == ["e2"] and f["pecas_atacadas_sem_defesa"][0]["peca"] == "cavalo branco"


def test_fatos_taticos_limita_as_listas_e_recusa_fen_invalida():
    import pytest
    assert len(fatos_taticos(FEN_MUITOS_XEQUES)["xeques"]) == 12
    assert len(fatos_taticos(FEN_MUITOS_MATES)["mates_em_1"]) == 12
    with pytest.raises(ValueError):
        fatos_taticos("lixo")
    # posição impossível (sem rei) também é erro de ferramenta, não resposta sem sentido
    with pytest.raises(ValueError):
        fatos_taticos("8/8/8/8/8/8/8/8 w - - 0 1")


def analisador_de_pvs(*pvs: list[str]):
    """Analisador roteirizado: uma linha por continuação em SAN, todas com o mesmo score."""
    def analisar(fen, multipv):
        b = chess.Board(fen)
        return {"fen": fen, "turn": "white" if b.turn else "black", "terminal": None,
                "lines": [{"move": "", "san": pv[0], "score": 100, "pv": [], "pv_san": list(pv)} for pv in pvs][:multipv]}
    return analisar


def _analisar_posicao(db, analisar):
    # o mesmo exercício a cada chamada: `puzzle_punir` cria uma partida com `source_id` único
    from chess_trainer.core.models import Puzzle
    ctx = contexto_do_exercicio(db, db.query(Puzzle).first() or puzzle_punir(db))
    return {f.nome: f for f in ferramentas_do_treinador(ctx, analisar, None, None)}["analisar_posicao"]


def test_em_troca_de_contrai_so_a_primeira_peca():
    from chess_trainer.coach.tools import _em_troca_de
    assert _em_troca_de(["a torre"]) == " pela torre"
    assert _em_troca_de(["o cavalo"]) == " pelo cavalo"
    assert _em_troca_de(["a torre", "o bispo", "o cavalo"]) == " pela torre, o bispo e o cavalo"
    assert _em_troca_de(["duas torres"]) == " por duas torres"
    assert _em_troca_de([]) == ""


def test_saldo_material_conta_as_pecas_dos_dois_lados():
    assert saldo_material(chess.Board()) == 0
    # torre branca (5) contra dama e peão pretos (10)
    assert saldo_material(chess.Board(FEN_MATERIAL)) == -5
    # reis não contam
    assert saldo_material(chess.Board("4k3/8/8/8/8/8/8/4K3 w - - 0 1")) == 0
    assert saldo_material(chess.Board("4k3/8/8/8/8/8/8/3QK3 w - - 0 1")) == 9


def test_linhas_da_analise_trazem_o_material(db_session):
    """O caso que motivou os campos: a linha do adversário dizia só `+3,9`, sem contar
    que o que se perde ali é a dama."""
    ferramenta = _analisar_posicao(db_session, analisador_de_pvs(["Rxd5", "cxd5"], ["Rd3", "Kd8"]))
    linhas = json.loads(ferramenta.fn({"fen": FEN_MATERIAL, "multipv": 2}))["linhas"]
    # quem move primeiro na linha são as brancas: elas ganham a dama e devolvem a torre
    assert linhas[0]["ganho_material"] == "brancas ganham a dama pela torre (+4)"
    assert linhas[0]["material_fim"] == -1
    # linha sem captura nenhuma: o material não muda
    assert linhas[1]["ganho_material"] == "nada" and linhas[1]["material_fim"] == -5
    # torre por torre: troca igual
    troca = json.loads(_analisar_posicao(db_session, analisador_de_pvs(["Rxd5", "cxd5"]))
                       .fn({"fen": FEN_TROCA, "multipv": 1}))["linhas"][0]
    assert troca["ganho_material"] == "troca igual" and troca["material_fim"] == -1
    # a descrição da ferramenta anuncia os dois campos
    assert "ganho_material" in ferramenta.descricao and "material_fim" in ferramenta.descricao


def test_material_da_linha_do_adversario_e_da_captura_de_graca(db_session):
    # `apos_passar`: quem move primeiro é o adversário, e o ganho é contado para ele
    ameaca = json.loads(_analisar_posicao(db_session, analisador_de_pvs(["Qxd3"]))
                        .fn({"fen": FEN_AMEACA, "multipv": 1, "apos_passar": True}))["linhas"][0]
    assert ameaca["ganho_material"] == "pretas ganham a torre (+5)" and ameaca["material_fim"] == -10
    # peça de graça, sem devolver nada: não aparece o "por ..."
    livre = json.loads(_analisar_posicao(db_session, analisador_de_pvs(["Rxd5", "Ke7"]))
                       .fn({"fen": FEN_MATERIAL, "multipv": 1}))["linhas"][0]
    assert livre["ganho_material"] == "brancas ganham a dama (+9)" and livre["material_fim"] == 4
    # a continuação (e o replay) param nos 8 primeiros lances
    longa = json.loads(_analisar_posicao(db_session, analisador_de_pvs(
        ["Rd3", "Kd8", "Rd4", "Kc8", "Rd3", "Kd8", "Rd4", "Kc8", "Rxd5"])).fn({"fen": FEN_MATERIAL, "multipv": 1}))["linhas"][0]
    assert len(longa["continuacao"]) == 8 and longa["ganho_material"] == "nada"


def test_material_nao_finge_precisao_em_promocao_e_em_troca_pela_metade(db_session):
    """Dois casos em que contar as peças perdidas enganaria: o peão que vira dama capturando
    (a peça "perdida" é o próprio peão que promoveu) e a linha que para antes da recaptura."""
    # b7xa8=Q: a torre preta some e o peão branco vira dama; nomear as peças diria "a torre pelo peão"
    promocao = json.loads(_analisar_posicao(db_session, analisador_de_pvs(["bxa8=Q"]))
                          .fn({"fen": "r3k3/1P6/8/8/8/8/8/4K3 w - - 0 1", "multipv": 1}))["linhas"][0]
    assert promocao["ganho_material"] == "brancas ganham material (+13)" and promocao["material_fim"] == 9
    # a continuação para logo depois de Rxd5, com cxd5 em cima: o saldo ali não é o da linha
    meio = json.loads(_analisar_posicao(db_session, analisador_de_pvs(["Rxd5"]))
                      .fn({"fen": FEN_MATERIAL, "multipv": 1}))["linhas"][0]
    assert meio["ganho_material"] == "material em disputa (a continuação para no meio de uma troca)"
    assert meio["material_fim"] == 4
    assert "em disputa" in _analisar_posicao(db_session, analisador_de_pvs(["Rxd5"])).descricao


def test_material_quando_quem_move_primeiro_e_quem_perde(db_session):
    # Rd3?? Qxd3: quem move primeiro é quem entrega a torre, então quem ganha é o outro lado
    linha = json.loads(_analisar_posicao(db_session, analisador_de_pvs(["Rd3", "Qxd3"]))
                       .fn({"fen": FEN_MATERIAL, "multipv": 1}))["linhas"][0]
    assert linha["ganho_material"] == "pretas ganham a torre (+5)" and linha["material_fim"] == -10
