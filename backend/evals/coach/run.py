"""Roda uma variante do treinador sobre o conjunto de avaliação e grava a rodada.

    cd backend && ANTHROPIC_API_KEY=... uv run python -m evals.coach.run --variante agente_rag --modelo opus --n 30

Precisa do Stockfish (verificação) e, para `agente_rag`, do banco do app com o
índice criado (`CHESS_TRAINER_DB`). A chave vem do ambiente, não do banco."""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

from chess_trainer.coach.explain import OpcoesExplicacao, explicar
from chess_trainer.coach.llm import AnthropicClient, ErroDoTreinador, LlmClient
from chess_trainer.coach.prompts import PROMPT_VERSION
from chess_trainer.coach.verify import Analisar
from evals.coach import metrics
from evals.coach.dataset import ItemAvaliacao, carregar, contexto_de_item
from evals.coach.judge import julgar

MODELOS = {"opus": "claude-opus-5", "sonnet": "claude-sonnet-5"}


def rodar(items: list[ItemAvaliacao], llm: LlmClient, analisar: Analisar, buscar, opcoes: OpcoesExplicacao,
          juiz: LlmClient | None = None) -> list[dict]:
    linhas = []
    for item in items:
        ctx = contexto_de_item(item)
        inicio = time.monotonic()
        try:
            r = explicar(contexto=ctx, llm=llm, analisar=analisar, estatisticas=None, buscar=buscar, opcoes=opcoes)
        except ErroDoTreinador as exc:
            linhas.append({"id": item.id, "origem": item.origem, "status": "errors", "ok": False, "erros": 1, "avisos": 0,
                           "issues": [{"tipo": exc.codigo, "gravidade": "erro", "detalhe": exc.mensagem, "linha_idx": None}],
                           "repaired": False, "custo_usd": 0.0, "duration_ms": int((time.monotonic() - inicio) * 1000),
                           "tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}, "n_chamadas_api": 0,
                           "texto": "", "estruturado": None, "nota": None, "justificativa": None})
            continue
        nota = julgar(juiz, ctx.texto(), r.texto) if juiz is not None else {"nota": None, "justificativa": None}
        linhas.append({
            "id": item.id, "origem": item.origem, "status": r.status, "ok": r.verificacao.ok,
            "erros": r.verificacao.erros, "avisos": r.verificacao.avisos, "issues": r.verificacao.to_dict()["issues"],
            "repaired": r.repaired, "custo_usd": r.custo_usd, "duration_ms": r.duration_ms, "tokens": r.uso.to_dict(),
            "n_chamadas_api": r.n_chamadas_api, "texto": r.texto, "estruturado": r.estruturado, **nota,
        })
    return linhas


# --- ligações com o ambiente real (substituídas nos testes) ------------------

def _db():
    from chess_trainer.core.db import init_db, make_engine, make_session_factory
    engine = make_engine(os.environ.get("CHESS_TRAINER_DB", str(Path(__file__).resolve().parents[2] / "data" / "chess_trainer.db")))
    init_db(engine)
    return make_session_factory(engine)()


def _analisar() -> Analisar:
    from chess_trainer.config import load_settings
    from chess_trainer.core.analysis.engine import StockfishEngine, find_stockfish
    from chess_trainer.core.analysis.interactive import InteractiveAnalyzer
    db = _db()
    try:
        path = find_stockfish(load_settings(db).stockfish_path)
    finally:
        db.close()
    if not path:
        raise SystemExit("Stockfish não encontrado: a verificação precisa da engine")
    return InteractiveAnalyzer(lambda: StockfishEngine(path, threads=2, hash_mb=64)).analyse


def _buscar():
    from chess_trainer.coach.retrieval.embeddings import FastembedEmbeddings
    from chess_trainer.coach.retrieval.index import Indexador
    db = _db()
    idx = Indexador(db.get_bind(), FastembedEmbeddings(cache_dir=Path(__file__).resolve().parents[2] / "data" / "fastembed"))
    return lambda consulta, k: idx.buscar(db, consulta, k)


def _llm(modelo: str) -> LlmClient:
    chave = os.environ.get("ANTHROPIC_API_KEY", "")
    if not chave:
        raise SystemExit("defina ANTHROPIC_API_KEY no ambiente para rodar a avaliação")
    return AnthropicClient(chave, modelo)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Roda a avaliação offline do treinador.")
    ap.add_argument("--dataset", default="evals/coach/dataset/v1.json")
    ap.add_argument("--variante", choices=("prompt", "agente", "agente_rag"), default="agente_rag")
    ap.add_argument("--modelo", choices=tuple(MODELOS), default="opus")
    ap.add_argument("--effort", choices=("low", "medium", "high"), default="high")
    ap.add_argument("--n", type=int, default=0, help="limita aos N primeiros itens (0 = todos)")
    ap.add_argument("--saida", default="evals/coach/runs")
    ap.add_argument("--sem-juiz", action="store_true")
    ap.add_argument("--juiz", choices=tuple(MODELOS), default="opus")
    args = ap.parse_args(argv)

    items = carregar(Path(args.dataset))
    if args.n:
        items = items[: args.n]
    modelo = MODELOS[args.modelo]
    llm = _llm(modelo)
    juiz = None if args.sem_juiz else _llm(MODELOS[args.juiz])
    buscar = _buscar() if args.variante == "agente_rag" else None
    opcoes = OpcoesExplicacao(variante=args.variante, effort=args.effort)
    linhas = rodar(items, llm, _analisar(), buscar, opcoes, juiz)

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    nome = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{args.variante}-{args.modelo}"
    (saida / f"{nome}.jsonl").write_text("\n".join(json.dumps(l, ensure_ascii=False) for l in linhas) + "\n", encoding="utf-8")
    resumo = {"variante": args.variante, "modelo": modelo, "effort": args.effort, "prompt_version": PROMPT_VERSION,
              "dataset": str(args.dataset), "data": datetime.now().date().isoformat(), **metrics.resumir(linhas)}
    (saida / f"{nome}.resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resumo, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
