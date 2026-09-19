"""Voto do usuário sobre um irmão do bloco: "tem a ver com o meu erro?" (spec golpes trechos §8,
revisão "o voto mora no bloco"). O voto é parte do produto, não uma tela de dev à parte — julgar
"é o mesmo golpe?" exige jogar o irmão, e é isso que o bloco já faz. Fonte do conjunto de ouro
que valida (e mais tarde treina) o classificador de golpes."""
from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chess_trainer.core.golpes.assinatura import VERSAO_ASSINATURA
from chess_trainer.core.golpes.service import assinatura_de
from chess_trainer.core.models import GolpeLabel, utcnow

LABELS = ("mesmo", "parecido", "nada")


def votar(db: Session, *, anchor_origem: str, anchor_id: str, candidate_id: str, tier: str, label: str,
         n_lances: int | None = None, posicao: str | None = None, nivel: str | None = None,
         espelhado: bool | None = None) -> GolpeLabel:
    """Grava o voto do usuário sobre um par (âncora, candidato): uma linha por par
    (`uq_golpe_labels_par`) — votar de novo no mesmo par atualiza o rótulo e a procedência em
    vez de duplicar (upsert em Python: a tabela de votos é pequena, não vale a pena um
    `INSERT ... ON CONFLICT` específico do SQLite aqui)."""
    if label not in LABELS:
        raise ValueError(f"rótulo inválido: {label!r} (esperado {LABELS})")
    existente = db.scalar(select(GolpeLabel).where(
        GolpeLabel.anchor_origem == anchor_origem, GolpeLabel.anchor_id == anchor_id,
        GolpeLabel.candidate_id == candidate_id))
    if existente is not None:
        existente.tier_na_hora = tier
        existente.versao_assinatura = VERSAO_ASSINATURA
        existente.label = label
        existente.n_lances = n_lances
        existente.posicao = posicao
        existente.nivel = nivel
        existente.espelhado = espelhado
        existente.created_at = utcnow()
        db.commit()
        return existente
    linha = GolpeLabel(anchor_origem=anchor_origem, anchor_id=anchor_id, candidate_id=candidate_id,
                       tier_na_hora=tier, versao_assinatura=VERSAO_ASSINATURA, label=label,
                       n_lances=n_lances, posicao=posicao, nivel=nivel, espelhado=espelhado)
    db.add(linha)
    db.commit()
    return linha


def voto_de(db: Session, *, anchor_origem: str, anchor_id: str, candidate_id: str) -> str | None:
    """O rótulo já gravado para este par, ou `None` sem voto ainda — para o painel do bloco
    marcar o botão escolhido ao reabrir a tática."""
    return db.scalar(select(GolpeLabel.label).where(
        GolpeLabel.anchor_origem == anchor_origem, GolpeLabel.anchor_id == anchor_id,
        GolpeLabel.candidate_id == candidate_id))


def resumo(db: Session) -> list[dict]:
    """Placar dos votos por procedência (spec golpes trechos §8; padrão de mate: spec golpes
    design §3.6, C): quantos votos de cada resposta ("mesmo"/"parecido"/"nada") cada combinação
    (degrau, posição, tamanho do trecho, nível) já recebeu, para mostrar o quanto cada tipo de
    casamento é ruído. `nivel` entra no agrupamento porque o degrau `padrao-mate` usa a MESMA
    `tier_na_hora` ("padrao-mate") para qualquer tema de mate e qualquer procedência da etiqueta
    (`"backRankMate:lichess"`, `"backRankMate:regra"`...); sem `nivel` na chave, votos de temas
    e procedências diferentes ficariam somados na mesma linha."""
    linhas = db.execute(select(GolpeLabel.tier_na_hora, GolpeLabel.posicao, GolpeLabel.n_lances,
                              GolpeLabel.nivel, GolpeLabel.label, func.count())
                        .group_by(GolpeLabel.tier_na_hora, GolpeLabel.posicao, GolpeLabel.n_lances,
                                 GolpeLabel.nivel, GolpeLabel.label)).all()
    agregados: dict[tuple, dict[str, int]] = {}
    for tier, posicao, n_lances, nivel, label, n in linhas:
        agregados.setdefault((tier, posicao, n_lances, nivel), {"mesmo": 0, "parecido": 0, "nada": 0})[label] = n
    saida = []
    for (tier, posicao, n_lances, nivel), contagem in sorted(agregados.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        saida.append({"tier": tier, "posicao": posicao, "n_lances": n_lances, "nivel": nivel,
                      **contagem, "total": sum(contagem.values())})
    return saida


def exportar_ouro(db: Session) -> str:
    """JSONL do conjunto de ouro: uma linha por voto gravado, com as assinaturas
    (o texto de `destinos`, que identifica o golpe) recalculadas na hora."""
    linhas = []
    for label in db.scalars(select(GolpeLabel).order_by(GolpeLabel.created_at)):
        ancora = assinatura_de(db, label.anchor_origem, label.anchor_id)
        candidato = assinatura_de(db, "lichess", label.candidate_id)
        linhas.append(json.dumps({
            "anchor_origem": label.anchor_origem,
            "anchor_id": label.anchor_id,
            "anchor_assinatura": ancora[0].destinos() if ancora else None,
            "candidate_id": label.candidate_id,
            "candidate_assinatura": candidato[0].destinos() if candidato else None,
            "tier": label.tier_na_hora,
            "versao": label.versao_assinatura,
            "label": label.label,
            "n_lances": label.n_lances,
            "posicao": label.posicao,
            "nivel": label.nivel,
            "espelhado": label.espelhado,
            "created_at": label.created_at.isoformat(),
        }, ensure_ascii=False) + "\n")
    return "".join(linhas)
