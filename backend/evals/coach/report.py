"""Relatório em markdown a partir dos resumos das rodadas (spec §8.2).

    cd backend && uv run python -m evals.coach.report evals/coach/runs/*.resumo.json --saida ../docs/coach-eval.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

COLUNAS = (("variante", "variante"), ("modelo", "modelo"), ("n", "n"), ("taxa_ok", "ok"), ("taxa_avisos", "com ressalvas"),
           ("taxa_erros", "com erros"), ("taxa_corrigidas", "corrigidas"), ("nota_media", "nota do juiz"),
           ("custo_medio_usd", "custo médio (US$)"), ("latencia_p50_ms", "p50 (ms)"), ("latencia_p95_ms", "p95 (ms)"))


def _fmt(chave: str, v) -> str:
    if v is None:
        return "–"
    if chave.startswith("taxa_"):
        return f"{100 * v:.0f}%"
    if isinstance(v, float):
        return f"{v:.3f}" if "usd" in chave else f"{v:.2f}"
    return str(v)


def escrever_relatorio(resumos: list[dict], path: Path, meta: dict) -> str:
    linhas = ["# Avaliação do treinador", "",
              f"Conjunto: `{meta.get('dataset', '?')}` · prompt `{meta.get('prompt_version', '?')}` · {meta.get('data', '')}", "",
              "| " + " | ".join(r for _, r in COLUNAS) + " |", "|" + "---|" * len(COLUNAS)]
    for r in resumos:
        linhas.append("| " + " | ".join(_fmt(c, r.get(c)) for c, _ in COLUNAS) + " |")
    tipos = sorted({t for r in resumos for t in r.get("por_tipo", {})})
    if tipos:
        linhas += ["", "## Problemas por 100 explicações", "", "| variante | modelo | " + " | ".join(tipos) + " |", "|---|---|" + "---|" * len(tipos)]
        for r in resumos:
            linhas.append(f"| {r['variante']} | {r['modelo']} | " + " | ".join(str(r.get("por_tipo", {}).get(t, 0)) for t in tipos) + " |")
    total = sum(r.get("custo_total_usd", 0) or 0 for r in resumos)
    linhas += ["", f"Custo total das rodadas: US$ {total:.2f}.", "",
               "Métricas: `ok` = nenhuma ressalva do verificador; `com erros` = lance ilegal, avaliação errada ou citação inexistente; "
               "a nota do juiz é de 1 a 5 pela rubrica em `evals/coach/judge.py`."]
    texto = "\n".join(linhas) + "\n"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(texto, encoding="utf-8")
    return texto


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("resumos", nargs="+")
    ap.add_argument("--saida", default="../docs/coach-eval.md")
    args = ap.parse_args(argv)
    resumos = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.resumos]
    meta = {"dataset": resumos[0].get("dataset"), "prompt_version": resumos[0].get("prompt_version"), "data": resumos[0].get("data")}
    print(escrever_relatorio(resumos, Path(args.saida), meta))


if __name__ == "__main__":
    main()
