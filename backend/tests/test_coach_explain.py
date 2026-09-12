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
BOA = {"texto": TEXTO + " A linha Qxf7# fecha. [c:ab12]", "linhas": [{"inicio": "inicial", "lances": ["Qxf7#"], "avaliacao_cp": None, "mate_em": 0}],
       "citacoes": ["ab12"], "padrao": "mateIn1", "treinar": ["mates com dama e bispo"]}


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
    assert [s[0] for s in tracer.spans][:2] == ["coach.explain", "contexto"] and tracer.geracoes[0]["model"] == "fake"
    assert "Qxf7#" in consulta_de_busca(r.contexto) and "mate em 1" in consulta_de_busca(r.contexto)


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
    pior = {**ruim, "citacoes": ["zzzz"], "texto": ruim["texto"] + " [c:zzzz]"}
    r = rodar(db_session, FakeLlm([[("final", ruim)], [("final", pior)]]))
    assert not r.repaired and r.status == "errors" and r.verificacao.erros == 1


def test_variantes_sem_busca_e_sem_ferramentas(db_session):
    llm = FakeLlm([[("final", {**BOA, "citacoes": [], "texto": TEXTO + " Qxf7#"})]])
    r = rodar(db_session, llm, opcoes=OpcoesExplicacao(variante="agente"))
    assert llm.prompts[0]["ferramentas"] == ["analisar_posicao", "contexto_do_exercicio", "estatisticas_por_tema"] and r.citacoes == []
    llm2 = FakeLlm([[("final", {**BOA, "citacoes": [], "texto": TEXTO + " Qxf7#"})]])
    rodar(db_session, llm2, opcoes=OpcoesExplicacao(variante="prompt"))
    assert llm2.prompts[0]["ferramentas"] == [] and "nenhum trecho" in llm2.prompts[0]["user"].lower()


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


def test_teto_de_tokens_vale_para_a_explicacao_inteira(db_session):
    """Cada chamada cabe no teto, a soma não: a explicação para em vez de seguir gastando."""
    import pytest
    ruim = {**BOA, "linhas": [{"inicio": "inicial", "lances": ["Qxf8"], "avaliacao_cp": None, "mate_em": None}]}
    llm = FakeLlm([[("final", ruim)], [("final", BOA)]], uso=Uso(0, 7_000, 0, 0))
    with pytest.raises(ErroDoTreinador) as exc:
        rodar(db_session, llm)
    assert exc.value.codigo == "custo_excedido"
    assert len(llm.prompts) == 2  # a primeira passou; a correção é que estourou


def test_gravar_guarda_so_a_ultima(db_session):
    r = rodar(db_session, FakeLlm([[("final", BOA)]]))
    a = gravar(db_session, r, review_id=None)
    b = gravar(db_session, r, review_id=None)
    rows = db_session.query(CoachExplanation).filter_by(puzzle_id=r.contexto.puzzle_id).all()
    assert [x.id for x in rows] == [b.id] and a.id != b.id
    assert json.loads(b.verification_json)["ok"] and json.loads(b.citations_json)[0]["chunk_id"] == "ab12"
    assert b.status == "ok" and b.model == "fake" and b.input_tokens == 1000 and b.text.startswith("explicação")
