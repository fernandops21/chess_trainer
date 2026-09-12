import json
import logging

import chess

from evals.coach import dataset, judge, metrics, report, run
from chess_trainer.coach.explain import OpcoesExplicacao
from chess_trainer.coach.llm import ErroDoTreinador
from chess_trainer.core.evals import MATE_SCORE
from chess_trainer.core.models import LichessPuzzle, LichessPuzzleTheme
from tests.fakes import FakeLlm
from tests.test_coach_explain import BOA, TEXTO, analisar
from tests.test_coach_tools import puzzle_punir

FEN_PASTOR = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3"


def lichess(db, id_, fen, moves, rating, temas):
    db.add(LichessPuzzle(id=id_, fen=fen, moves=moves, rating=rating, rating_deviation=50, popularity=95, nb_plays=5000, themes=" ".join(temas)))
    for t in temas:
        db.add(LichessPuzzleTheme(theme=t, puzzle_id=id_))


class LlmQueEstoura(FakeLlm):
    """Levanta a exceção nas `n_falhas` primeiras chamadas e depois segue o roteiro."""

    def __init__(self, exc, roteiros=None, n_falhas=1):
        super().__init__(roteiros or [])
        self.exc = exc
        self.n_falhas = n_falhas

    def run_agent(self, **kwargs):
        if self.n_falhas > 0:
            self.n_falhas -= 1
            raise self.exc
        return super().run_agent(**kwargs)


def test_montar_salvar_e_carregar(db_session, tmp_path):
    puzzle_punir(db_session)
    # dois puzzles sintéticos do Lichess: mate do pastor de cada lado (o FEN é antes do lance do adversário)
    lichess(db_session, "L1", FEN_PASTOR, "g8f6 h5f7", 1100, ["mateIn1", "short", "mate"])
    lichess(db_session, "L2", FEN_PASTOR, "g8f6 h5f7", 1700, ["mateIn1", "short", "mate"])
    db_session.commit()
    items = dataset.montar(db_session, analisar, n_lichess=2, seed=1)
    assert [i.origem for i in items] == ["own", "lichess", "lichess"]
    proprio = items[0]
    assert proprio.contexto["tipo"] == "punir" and proprio.gabarito["inicial"]["lines"][0]["san"] == "Qxf7#"
    tatico = items[1]
    ctx = dataset.contexto_de_item(tatico)
    assert ctx.tipo == "lichess" and ctx.solucao_san == ["Qxf7#"] and ctx.tema in ("mate em 1", "mate") and tatico.rating in (1100, 1700)
    assert "g8f6" in ctx.lances_permitidos and "h5f7" in ctx.lances_permitidos
    caminho = tmp_path / "v1.json"
    dataset.salvar(items, caminho)
    de_volta = dataset.carregar(caminho)
    assert [i.id for i in de_volta] == [i.id for i in items] and de_volta[1].gabarito == items[1].gabarito
    assert "short" in dataset.TEMAS_GENERICOS


def test_amostra_incompleta_avisa_e_devolve_o_que_tem(db_session, caplog):
    lichess(db_session, "L1", FEN_PASTOR, "g8f6 h5f7", 1100, ["mateIn1", "short"])
    lichess(db_session, "L2", FEN_PASTOR, "g8f6 h5f7", 1700, ["mateIn1", "short"])
    db_session.commit()
    with caplog.at_level(logging.WARNING, logger="evals.coach.dataset"):
        items = dataset.montar(db_session, analisar, n_lichess=5, seed=1)
    assert [i.origem for i in items] == ["lichess", "lichess"] and {i.id for i in items} == {"lichess:L1", "lichess:L2"}
    assert "faltaram 3" in caplog.text


def test_rodar_resumir_e_relatorio(db_session, tmp_path):
    puzzle_punir(db_session)
    items = dataset.montar(db_session, analisar, n_lichess=0, seed=1)
    ruim = {**BOA, "linhas": [{"inicio": "inicial", "lances": ["Qxf8"], "avaliacao_cp": None, "mate_em": None}], "citacoes": [], "por_que": TEXTO}
    llm = FakeLlm([[("final", ruim)], [("final", ruim)]])
    juiz = FakeLlm([[("final", {"nota": 4, "justificativa": "clara"})]])
    linhas = run.rodar(items, llm, analisar, buscar=None, opcoes=OpcoesExplicacao(variante="agente"), juiz=juiz)
    assert len(linhas) == 1 and linhas[0]["status"] == "errors" and linhas[0]["nota"] == 4 and linhas[0]["erros"] == 1
    r = metrics.resumir(linhas)
    assert r["n"] == 1 and r["taxa_erros"] == 1.0 and r["por_tipo"]["lance_ilegal"] == 100.0 and r["nota_media"] == 4.0
    assert r["custo_total_usd"] == 0.0 and r["latencia_p50_ms"] >= 0
    md = report.escrever_relatorio([{"variante": "agente", "modelo": "fake", **r}], tmp_path / "rel.md",
                                   {"dataset": "v1", "prompt_version": "v1", "data": "2026-09-11"})
    assert "| agente | fake |" in md and (tmp_path / "rel.md").read_text(encoding="utf-8").startswith("# Avaliação do treinador")


def test_uma_excecao_nao_derruba_a_rodada(db_session):
    puzzle_punir(db_session)
    items = dataset.montar(db_session, analisar, n_lichess=0, seed=1) * 2
    boa = {**BOA, "citacoes": [], "por_que": TEXTO + " Qxf7#"}
    llm = LlmQueEstoura(RuntimeError("engine morreu"), [[("final", boa)]])
    linhas = run.rodar(items, llm, analisar, buscar=None, opcoes=OpcoesExplicacao(variante="agente"))
    assert len(linhas) == 2
    assert linhas[0]["status"] == "errors" and linhas[0]["issues"] == [
        {"tipo": "excecao", "gravidade": "erro", "detalhe": "RuntimeError: engine morreu", "linha_idx": None}]
    assert linhas[0]["texto"] == "" and linhas[0]["nota"] is None
    assert linhas[1]["status"] == "ok" and linhas[1]["texto"].endswith("Qxf7#")


def test_erro_do_treinador_vira_linha_com_o_codigo(db_session):
    puzzle_punir(db_session)
    items = dataset.montar(db_session, analisar, n_lichess=0, seed=1)
    llm = LlmQueEstoura(ErroDoTreinador("limite_de_uso", "x"))
    linhas = run.rodar(items, llm, analisar, buscar=None, opcoes=OpcoesExplicacao(variante="agente"))
    assert len(linhas) == 1 and linhas[0]["status"] == "errors" and linhas[0]["erros"] == 1
    assert linhas[0]["issues"][0]["tipo"] == "limite_de_uso" and linhas[0]["issues"][0]["detalhe"] == "x"


def test_spearman_e_julgar():
    assert metrics.spearman([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0
    assert metrics.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    juiz = FakeLlm([[("final", {"nota": 2, "justificativa": "vaga"})]])
    nota = judge.julgar(juiz, "contexto", "explicação")
    assert nota == {"nota": 2, "justificativa": "vaga"} and "1 a 5" in judge.RUBRICA and juiz.prompts[0]["ferramentas"] == []
    # folga de tokens: a nota é curta, mas o raciocínio sai do mesmo orçamento
    assert juiz.prompts[0]["max_tokens"] == 4096


def test_juiz_que_falha_nao_derruba_o_item():
    """Erro do juiz (truncado, limite de uso) vira nota 0 com a justificativa: a amostra
    inteira não pode ir embora por causa de uma nota."""
    class JuizQuebrado:
        model = "fake"

        def run_agent(self, **kw):
            raise ErroDoTreinador("resposta_truncada", "a resposta passou do limite de tokens e foi cortada")

    nota = judge.julgar(JuizQuebrado(), "contexto", "explicação")
    assert nota["nota"] == 0 and nota["justificativa"] == "juiz falhou: a resposta passou do limite de tokens e foi cortada"


def test_main_le_o_dataset_e_escreve_a_rodada(db_session, tmp_path, monkeypatch):
    puzzle_punir(db_session)
    items = dataset.montar(db_session, analisar, n_lichess=0, seed=1)
    dataset.salvar(items, tmp_path / "v1.json")
    monkeypatch.setattr(run, "_llm", lambda modelo: FakeLlm([[("final", {**BOA, "citacoes": [], "por_que": TEXTO + " Qxf7#"})]]))
    monkeypatch.setattr(run, "_analisar", lambda: analisar)
    monkeypatch.setattr(run, "_buscar", lambda: None)
    run.main(["--dataset", str(tmp_path / "v1.json"), "--variante", "agente", "--modelo", "opus", "--saida", str(tmp_path / "runs"), "--sem-juiz"])
    arquivos = list((tmp_path / "runs").glob("*.jsonl"))
    assert len(arquivos) == 1 and json.loads(arquivos[0].read_text(encoding="utf-8").splitlines()[0])["status"] == "ok"
    # gravado linha a linha: uma linha por item, terminada em \n e sem linha em branco
    bruto = arquivos[0].read_text(encoding="utf-8")
    assert bruto.endswith("\n") and bruto.splitlines() == [bruto[:-1]] and "\n\n" not in bruto
    resumo = json.loads(arquivos[0].with_suffix(".resumo.json").read_text(encoding="utf-8"))
    assert resumo["variante"] == "agente" and resumo["modelo"] == "claude-opus-5" and resumo["n"] == 1
