"""Métricas de uma rodada (spec §8.2): tudo sai do verificador e dos custos; a nota do juiz é opcional."""
from __future__ import annotations

from collections import Counter

import numpy as np


def _p(valores: list[float], q: float) -> float:
    return float(np.percentile(valores, q)) if valores else 0.0


def resumir(linhas: list[dict]) -> dict:
    n = len(linhas)
    if n == 0:
        return {"n": 0}
    tipos = Counter(i["tipo"] for l in linhas for i in l["issues"])
    notas = [l["nota"] for l in linhas if l.get("nota")]
    lat = [l["duration_ms"] for l in linhas]
    return {
        "n": n,
        "taxa_erros": sum(1 for l in linhas if l["status"] == "errors") / n,
        "taxa_avisos": sum(1 for l in linhas if l["status"] == "warnings") / n,
        "taxa_ok": sum(1 for l in linhas if l["status"] == "ok") / n,
        "taxa_corrigidas": sum(1 for l in linhas if l["repaired"]) / n,
        "por_tipo": {t: round(100.0 * c / n, 1) for t, c in sorted(tipos.items())},  # ocorrências por 100 explicações
        "custo_medio_usd": round(sum(l["custo_usd"] for l in linhas) / n, 4),
        "custo_total_usd": round(sum(l["custo_usd"] for l in linhas), 4),
        "latencia_p50_ms": _p(lat, 50), "latencia_p95_ms": _p(lat, 95),
        "tokens_medios": {k: round(sum(l["tokens"][k] for l in linhas) / n) for k in ("input", "output", "cache_read", "cache_write")},
        "chamadas_api_medias": round(sum(l["n_chamadas_api"] for l in linhas) / n, 2),
        "nota_media": round(sum(notas) / len(notas), 2) if notas else None,
    }


def _ranks(v: list[float]) -> np.ndarray:
    a = np.asarray(v, dtype=float)
    ordem = a.argsort()
    r = np.empty(len(a))
    r[ordem] = np.arange(1, len(a) + 1)
    # empates: média das posições
    for valor in np.unique(a):
        m = a == valor
        if m.sum() > 1:
            r[m] = r[m].mean()
    return r


def spearman(a: list[float], b: list[float]) -> float:
    """Correlação de Spearman entre duas listas (para calibrar o juiz contra as notas do usuário)."""
    if len(a) != len(b) or len(a) < 2:
        return 0.0
    ra, rb = _ranks(a), _ranks(b)
    if ra.std() == 0 or rb.std() == 0:
        return 0.0
    return float(np.corrcoef(ra, rb)[0, 1])
