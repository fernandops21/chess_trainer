import json

import chess

from evals.coach import dataset, judge, metrics, report, run
from chess_trainer.coach.explain import OpcoesExplicacao
from chess_trainer.core.evals import MATE_SCORE
from chess_trainer.core.models import LichessPuzzle, LichessPuzzleTheme
from tests.fakes import FakeLlm
from tests.test_coach_explain import BOA, TEXTO, analisar
from tests.test_coach_tools import puzzle_punir


def lichess(db, id_, fen, moves, rating, temas):
    db.add(LichessPuzzle(id=id_, fen=fen, moves=moves, rating=rating, rating_deviation=50, popularity=95, nb_plays=5000, themes=" ".join(temas)))
    for t in temas:
        db.add(LichessPuzzleTheme(theme=t, puzzle_id=id_))


def test_montar_salvar_e_carregar(db_session, tmp_path):
    puzzle_punir(db_session)
    # dois puzzles sintéticos do Lichess: mate do pastor de cada lado (o FEN é antes do lance do adversário)
    lichess(db_session, "L1", "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3", "g8f6 h5f7", 1100, ["mateIn1", "short", "mate"])
    lichess(db_session, "L2", "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3", "g8f6 h5f7", 1700, ["mateIn1", "short", "mate"])
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


def test_rodar_resumir_e_relatorio(db_session, tmp_path):
    puzzle_punir(db_session)
    items = dataset.montar(db_session, analisar, n_lichess=0, seed=1)
    ruim = {**BOA, "linhas": [{"inicio": "inicial", "lances": ["Qxf8"], "avaliacao_cp": None, "mate_em": None}], "citacoes": [], "texto": TEXTO}
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


def test_spearman_e_julgar():
    assert metrics.spearman([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0
    assert metrics.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    juiz = FakeLlm([[("final", {"nota": 2, "justificativa": "vaga"})]])
    nota = judge.julgar(juiz, "contexto", "explicação")
    assert nota == {"nota": 2, "justificativa": "vaga"} and "1 a 5" in judge.RUBRICA and juiz.prompts[0]["ferramentas"] == []


def test_main_le_o_dataset_e_escreve_a_rodada(db_session, tmp_path, monkeypatch):
    puzzle_punir(db_session)
    items = dataset.montar(db_session, analisar, n_lichess=0, seed=1)
    dataset.salvar(items, tmp_path / "v1.json")
    monkeypatch.setattr(run, "_llm", lambda modelo: FakeLlm([[("final", {**BOA, "citacoes": [], "texto": TEXTO + " Qxf7#"})]]))
    monkeypatch.setattr(run, "_analisar", lambda: analisar)
    monkeypatch.setattr(run, "_buscar", lambda: None)
    run.main(["--dataset", str(tmp_path / "v1.json"), "--variante", "agente", "--modelo", "opus", "--saida", str(tmp_path / "runs"), "--sem-juiz"])
    arquivos = list((tmp_path / "runs").glob("*.jsonl"))
    assert len(arquivos) == 1 and json.loads(arquivos[0].read_text(encoding="utf-8").splitlines()[0])["status"] == "ok"
    resumo = json.loads(arquivos[0].with_suffix(".resumo.json").read_text(encoding="utf-8"))
    assert resumo["variante"] == "agente" and resumo["modelo"] == "claude-opus-5" and resumo["n"] == 1
