import json

from chess_trainer.coach.costs import Uso
from chess_trainer.coach.explain import OpcoesExplicacao, consulta_de_busca, explicar, gravar
from chess_trainer.coach.llm import ErroDoTreinador
from chess_trainer.coach.prompts import PROMPT_VERSION
from chess_trainer.coach.tools import contexto_do_exercicio
from chess_trainer.core.evals import MATE_SCORE
from chess_trainer.core.models import CoachExplanation, Puzzle
from tests.fakes import FakeLlm, FakeTracer
from tests.test_coach_tools import FEN, FEN_ERRO, puzzle_punir

TEXTO = " ".join(["explicação"] * 70)
# o bloco "na partida" não cita lance nenhum: lance na prosa fora das linhas viraria aviso
NA_PARTIDA = "Na partida a dama branca já apontava para o ponto mais fraco do lado do rei."


def analisar(fen, multipv):
    import chess
    b = chess.Board(fen)
    if b.is_game_over():
        return {"fen": fen, "turn": "white", "terminal": "checkmate", "lines": []}
    if b.fen() == FEN:
        return {"fen": fen, "turn": "white", "terminal": None, "lines": [{"move": "h5f7", "san": "Qxf7#", "score": MATE_SCORE - 1, "pv": ["h5f7"], "pv_san": ["Qxf7#"]}][:multipv]}
    mv = next(iter(b.legal_moves))
    return {"fen": fen, "turn": "white" if b.turn else "black", "terminal": None, "lines": [{"move": mv.uci(), "san": b.san(mv), "score": 0, "pv": [mv.uci()], "pv_san": [b.san(mv)]}]}


TRECHOS = [{"chunk_id": "ab12", "study_id": "s1", "estudo": "E", "chapter_id": "c1", "capitulo": "C", "node_id": "n1",
            "caminho_san": "1.e4", "texto": "Trecho sintético sobre mate com dama e bispo.", "url": "/estudos/s1/capitulos/c1?lance=n1"}]
BOA = {"na_partida": NA_PARTIDA, "por_que": TEXTO + " A linha Qxf7# fecha. [c:ab12]",
       "linhas": [{"inicio": "inicial", "lances": ["Qxf7#"], "avaliacao_cp": None, "mate_em": 0}],
       "citacoes": ["ab12"], "padrao": "mate do pastor", "treinar": ["mates com dama e bispo"]}


def _exercicio(db):
    """O mesmo exercício a cada chamada: `puzzle_punir` cria uma partida com `source_id`
    único, então reaproveitamos o que já existe quando o teste roda o pipeline duas vezes."""
    return db.query(Puzzle).first() or puzzle_punir(db)


def rodar(db, llm, tracer=None, buscar=lambda consulta, k: TRECHOS, opcoes=None):
    ctx = contexto_do_exercicio(db, _exercicio(db))
    return explicar(contexto=ctx, llm=llm, analisar=analisar, estatisticas=lambda dias: [], buscar=buscar,
                    opcoes=opcoes or OpcoesExplicacao(), tracer=tracer)


def test_caminho_feliz_com_rag_e_citacao(db_session):
    llm = FakeLlm([[("ferramenta", "analisar_posicao", {"fen": FEN, "multipv": 1}), ("final", BOA)]])
    tracer = FakeTracer()
    r = rodar(db_session, llm, tracer)
    assert r.status == "ok" and r.verificacao.ok and not r.repaired and r.n_chamadas_api == 1
    assert r.citacoes == TRECHOS and r.linhas == BOA["linhas"] and r.prompt_version == PROMPT_VERSION
    assert r.uso == Uso(1000, 200, 500, 0) and r.custo_usd == 0.0 and r.trace_id == "trace-falso"
    assert "[c:ab12]" in llm.prompts[0]["user"] and "buscar_estudos" in llm.prompts[0]["ferramentas"]
    # o dossiê vai na primeira mensagem, calculado antes da primeira chamada (span próprio)
    assert "## Fatos já calculados" in llm.prompts[0]["user"] and "ameacas_inicial" in llm.prompts[0]["user"]
    assert "### apos_solucao — posição depois de Qxf7#" in llm.prompts[0]["user"]
    assert [s[0] for s in tracer.spans][:4] == ["coach.explain", "contexto", "recuperacao", "dossie"] and tracer.geracoes[0]["model"] == "fake"
    assert "Qxf7#" in consulta_de_busca(r.contexto) and "mate em 1" in consulta_de_busca(r.contexto)
    # o `texto` é derivado dos dois blocos: é o que o verificador, a avaliação e o juiz leem
    assert r.texto == f"{NA_PARTIDA}\n\n{BOA['por_que']}"
    assert r.estruturado is not None and r.estruturado["padrao"] == "mate do pastor"
    assert r.estruturado["treinar"] == ["mates com dama e bispo"]


def test_texto_derivado_junta_os_blocos_e_ignora_o_que_falta():
    from chess_trainer.coach.explain import texto_da_resposta

    assert texto_da_resposta({"na_partida": " a ", "por_que": " b "}) == "a\n\nb"
    assert texto_da_resposta({"na_partida": "", "por_que": "b"}) == "b"
    assert texto_da_resposta({"na_partida": "a", "por_que": "   "}) == "a"
    assert texto_da_resposta({}) == ""


def test_trecho_achado_pela_ferramenta_pode_ser_citado(db_session):
    # a recuperação inicial não acha nada; quem acha é o agente, chamando `buscar_estudos`
    llm = FakeLlm([[("ferramenta", "buscar_estudos", {"consulta": "mate", "k": 1}), ("final", BOA)]])
    r = rodar(db_session, llm, buscar=lambda consulta, k: TRECHOS if consulta == "mate" else [])
    assert r.status == "ok" and r.verificacao.ok and r.citacoes == TRECHOS
    assert [t["chunk_id"] for t in r.trechos] == ["ab12"]
    assert "nenhum trecho" in llm.prompts[0]["user"].lower()


def test_erro_de_verificacao_dispara_uma_correcao(db_session):
    ruim = {**BOA, "linhas": [{"inicio": "inicial", "lances": ["Qxf8"], "avaliacao_cp": None, "mate_em": None}]}
    llm = FakeLlm([[("final", ruim)], [("final", BOA)]])
    r = rodar(db_session, llm)
    assert r.repaired and r.status == "ok" and r.n_chamadas_api == 2 and r.uso == Uso(2000, 400, 1000, 0)
    assert "lance_ilegal" in llm.prompts[1]["user"] and "Qxf8" in llm.prompts[1]["user"]


def test_correcao_que_nao_melhora_mantem_a_primeira(db_session):
    ruim = {**BOA, "linhas": [{"inicio": "inicial", "lances": ["Qxf8"], "avaliacao_cp": None, "mate_em": None}]}
    pior = {**ruim, "citacoes": ["zzzz"], "por_que": ruim["por_que"] + " [c:zzzz]"}
    r = rodar(db_session, FakeLlm([[("final", ruim)], [("final", pior)]]))
    assert not r.repaired and r.status == "errors" and r.verificacao.erros == 1


def test_variantes_sem_busca_e_sem_ferramentas(db_session):
    llm = FakeLlm([[("final", {**BOA, "citacoes": [], "por_que": TEXTO + " Qxf7#"})]])
    r = rodar(db_session, llm, opcoes=OpcoesExplicacao(variante="agente"))
    assert llm.prompts[0]["ferramentas"] == ["analisar_posicao", "fatos_taticos", "contexto_do_exercicio", "estatisticas_por_tema"] and r.citacoes == []
    llm2 = FakeLlm([[("final", {**BOA, "citacoes": [], "por_que": TEXTO + " Qxf7#"})]])
    rodar(db_session, llm2, opcoes=OpcoesExplicacao(variante="prompt"))
    assert llm2.prompts[0]["ferramentas"] == [] and "nenhum trecho" in llm2.prompts[0]["user"].lower()
    # a variante só prompt também recebe o dossiê: sem ferramentas, é dele que a explicação sai
    assert "## Fatos já calculados" in llm2.prompts[0]["user"] and "ameacas_inicial" in llm2.prompts[0]["user"]


def test_resposta_fora_do_esquema_tenta_de_novo_e_depois_falha(db_session):
    llm = FakeLlm([[("texto", "sem entrega")], [("final", BOA)]])
    assert rodar(db_session, llm).status == "ok"
    # a retentativa avisa que a resposta anterior não veio pela ferramenta
    assert "entregar_explicacao" in llm.prompts[1]["user"] and llm.prompts[1]["user"] != llm.prompts[0]["user"]
    import pytest
    tracer = FakeTracer()
    with pytest.raises(ErroDoTreinador) as exc:
        rodar(db_session, FakeLlm([[("texto", "x")], [("texto", "y")]]), tracer)
    assert exc.value.codigo == "resposta_fora_do_esquema" and tracer.flushed is True


def test_agente_que_morre_no_meio_conta_as_chamadas_ja_feitas_no_log(db_session, caplog):
    """A API recusou a quarta chamada: o log tem de dizer que houve três, e o que as ferramentas custaram."""
    import logging

    import pytest
    from chess_trainer.coach.llm import ChamadaFerramenta

    class LlmQueMorre:
        model = "fake"

        def run_agent(self, **kw):
            exc = ErroDoTreinador("requisicao_invalida", "a API recusou o pedido")
            exc.n_chamadas_api = 3
            exc.chamadas = [ChamadaFerramenta("analisar_posicao", {}, "{}", ms=1200), ChamadaFerramenta("analisar_posicao", {}, "{}", ms=800)]
            raise exc

    with caplog.at_level(logging.INFO, logger="chess_trainer.coach.explain"), pytest.raises(ErroDoTreinador):
        rodar(db_session, LlmQueMorre())
    linha = [x for x in caplog.messages if x.startswith("explicacao ")][0]
    assert "llm 3 chamadas" in linha and "analisar_posicao 2x 2000 ms" in linha
    # o dossiê já tinha sido calculado quando o agente morreu: o tempo dele entra na conta
    assert "| dossie " in linha


def test_teto_de_tokens_vale_para_a_explicacao_inteira(db_session, caplog):
    """Cada chamada cabe no teto, a soma não: a explicação para em vez de seguir gastando."""
    import logging

    import pytest
    ruim = {**BOA, "linhas": [{"inicio": "inicial", "lances": ["Qxf8"], "avaliacao_cp": None, "mate_em": None}]}
    llm = FakeLlm([[("final", ruim)], [("final", BOA)]], uso=Uso(0, 11_000, 0, 0))  # 11k + 11k > 20k
    with caplog.at_level(logging.INFO, logger="chess_trainer.coach.explain"), pytest.raises(ErroDoTreinador) as exc:
        rodar(db_session, llm)
    assert exc.value.codigo == "custo_excedido"
    assert len(llm.prompts) == 2  # a primeira passou; a correção é que estourou
    # a explicação que morreu no meio também diz onde gastou o tempo
    assert [x for x in caplog.messages if x.startswith("explicacao ")]


AFIRMACAO_FALSA = {"tipo": "ataca", "trecho": "a dama de h5 ataca e8", "peca": "h5", "alvo": "e8",
                   "lance": None, "lado": None, "tipo_peca": None, "casas": []}


def checador(*listas):
    """O segundo modelo, com o preço do Sonnet para o custo da checagem ser conferível."""
    llm = FakeLlm([[("final", {"afirmacoes": list(lista)})] for lista in listas])
    llm.model = "claude-sonnet-5"
    return llm


def test_afirmacao_falsa_dispara_a_correcao_e_entra_na_conta(db_session, caplog):
    """O caso real: a prosa diz que a dama ataca uma casa que ela não alcança (o peão de f7
    tapa e8). O segundo modelo extrai a afirmação, o python-chess a derruba, e a correção roda."""
    import logging

    llm = FakeLlm([[("final", BOA)], [("final", BOA)]])
    check = checador([AFIRMACAO_FALSA], [])
    tracer = FakeTracer()
    with caplog.at_level(logging.INFO, logger="chess_trainer.coach.explain"):
        ctx = contexto_do_exercicio(db_session, _exercicio(db_session))
        r = explicar(contexto=ctx, llm=llm, analisar=analisar, estatisticas=lambda dias: [], buscar=lambda c, k: TRECHOS,
                     opcoes=OpcoesExplicacao(), tracer=tracer, llm_checagem=check)
    assert r.repaired and r.status == "ok" and len(llm.prompts) == 2 and len(check.prompts) == 2
    # a correção viu a afirmação falsa com o trecho e o motivo, e a instrução do que fazer com ela
    assert "afirmacao_falsa" in llm.prompts[1]["user"] and "«a dama de h5 ataca e8»" in llm.prompts[1]["user"]
    assert "h5 não ataca e8" in llm.prompts[1]["user"] and "reescreva a frase" in llm.prompts[1]["user"]
    # o texto da explicação foi ao checador, com o prompt dele
    assert BOA["por_que"] in check.prompts[0]["user"] and check.prompts[0]["effort"] == "low"
    # tokens: `uso` é só do modelo principal; a checagem vai à parte e o custo soma os dois
    assert r.uso == Uso(2000, 400, 1000, 0) and r.uso_checagem == Uso(2000, 400, 1000, 0)
    assert r.custo_usd == 0.0082  # 2000*2,0 + 1000*0,20 + 400*10 por milhão, do Sonnet; o principal ("fake") custa zero
    assert r.n_chamadas_api == 4 and r.tempos["llm_chamadas"] == 2 and r.tempos["afirmacoes"] == 1 and r.tempos["checagem_ms"] >= 0
    linha = [x for x in caplog.messages if x.startswith("explicacao ")][0]
    assert "checagem 1 afirmacoes" in linha and "correcao sim" in linha
    assert [s[0] for s in tracer.spans].count("checagem") == 2
    assert [g for g in tracer.geracoes if g["nome"] == "checagem"][0]["model"] == "claude-sonnet-5"


def test_checagem_sem_afirmacao_falsa_nao_muda_nada(db_session):
    llm = FakeLlm([[("final", BOA)]])
    verdadeira = {**AFIRMACAO_FALSA, "trecho": "a dama de h5 ataca f7", "alvo": "f7"}
    check = checador([verdadeira, {**AFIRMACAO_FALSA, "tipo": "outro"}])
    ctx = contexto_do_exercicio(db_session, _exercicio(db_session))
    r = explicar(contexto=ctx, llm=llm, analisar=analisar, estatisticas=lambda dias: [], buscar=lambda c, k: TRECHOS,
                 opcoes=OpcoesExplicacao(), llm_checagem=check)
    assert r.status == "ok" and not r.repaired and r.tempos["afirmacoes"] == 2 and r.n_chamadas_api == 2
    assert r.custo_usd == 0.0041 and r.uso == Uso(1000, 200, 500, 0)
    # a explicação gravada leva o custo somado
    row = gravar(db_session, r, review_id=None)
    assert row.cost_usd == 0.0041 and row.input_tokens == 1000


def test_gravar_guarda_so_a_ultima(db_session):
    r = rodar(db_session, FakeLlm([[("final", BOA)]]))
    a = gravar(db_session, r, review_id=None)
    b = gravar(db_session, r, review_id=None)
    rows = db_session.query(CoachExplanation).filter_by(puzzle_id=r.contexto.puzzle_id).all()
    assert [x.id for x in rows] == [b.id] and a.id != b.id
    assert json.loads(b.verification_json)["ok"] and json.loads(b.citations_json)[0]["chunk_id"] == "ab12"
    assert b.status == "ok" and b.model == "fake" and b.input_tokens == 1000 and b.text.startswith("Na partida")
    # a resposta em blocos vai guardada como veio: é dela que o cartão monta a leitura
    est = json.loads(b.structured_json)
    assert est["na_partida"] == NA_PARTIDA and est["por_que"].endswith("[c:ab12]")
    assert est["padrao"] == "mate do pastor" and est["treinar"] == ["mates com dama e bispo"]


def test_tempos_medidos_e_registrados_no_log(db_session, caplog):
    """Uma explicação real leva perto de um minuto: o log diz onde o tempo foi."""
    import logging

    llm = FakeLlm([[("ferramenta", "analisar_posicao", {"fen": FEN, "multipv": 1}),
                    ("ferramenta", "fatos_taticos", {"fen": FEN}),
                    ("ferramenta", "analisar_posicao", {"fen": FEN_ERRO, "multipv": 1}), ("final", BOA)]])
    with caplog.at_level(logging.INFO, logger="chess_trainer.coach.explain"):
        r = rodar(db_session, llm)
    t = r.tempos
    assert set(t) == {"total_ms", "dossie_ms", "llm_ms", "llm_chamadas", "ferramentas", "verificacao_ms", "checagem_ms",
                      "afirmacoes", "correcao"}
    assert t["llm_chamadas"] == 1 and t["correcao"] is False and t["total_ms"] >= 0 and t["verificacao_ms"] >= 0
    # sem modelo de checagem não há afirmação nem tempo de checagem, mas a linha do log ainda os traz
    assert t["checagem_ms"] == 0 and t["afirmacoes"] == 0 and r.uso_checagem == Uso()
    assert t["dossie_ms"] >= 0
    assert t["ferramentas"]["analisar_posicao"]["n"] == 2 and t["ferramentas"]["fatos_taticos"]["n"] == 1
    assert all(f["ms"] >= 0 for f in t["ferramentas"].values())
    assert t["llm_ms"] >= 0
    linha = [x for x in caplog.messages if x.startswith("explicacao ")]
    assert len(linha) == 1 and r.contexto.puzzle_id in linha[0]
    # o relógio do LLM engloba as ferramentas (elas rodam dentro da chamada): o log avisa
    assert "total " in linha[0] and "llm 1 chamadas," in linha[0] and "(inclui as ferramentas)" in linha[0]
    assert "verificacao " in linha[0] and "| checagem 0 afirmacoes, 0 ms" in linha[0]
    # o dossiê sai logo depois do total: é a engine antes da primeira chamada
    assert linha[0].index("total ") < linha[0].index("| dossie ") < linha[0].index("| llm ")
    assert "analisar_posicao 2x" in linha[0] and "fatos_taticos 1x" in linha[0] and "correcao não" in linha[0]


def test_tempos_somam_a_correcao_e_as_duas_verificacoes(db_session, caplog):
    import logging

    ruim = {**BOA, "linhas": [{"inicio": "inicial", "lances": ["Qxf8"], "avaliacao_cp": None, "mate_em": None}]}
    with caplog.at_level(logging.INFO, logger="chess_trainer.coach.explain"):
        r = rodar(db_session, FakeLlm([[("final", ruim)], [("final", BOA)]]))
    assert r.repaired and r.tempos["correcao"] is True and r.tempos["llm_chamadas"] == 2
    # sem ferramenta nenhuma o log ainda sai, dizendo que não houve
    assert r.tempos["ferramentas"] == {} and "ferramentas: nenhuma" in caplog.text and "correcao sim" in caplog.text
