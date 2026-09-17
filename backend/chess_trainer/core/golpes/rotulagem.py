"""Rotulagem humana dos pares (âncora, candidato) que a cascata de irmãos propõe: a
fonte do conjunto de ouro que valida (e mais tarde treina) o classificador de golpes
(spec golpes §8). Fica atrás de `CHESS_TRAINER_ROTULAGEM=1`, como o restante da tela."""
from __future__ import annotations

import json
import random
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from chess_trainer.config import AppSettings
from chess_trainer.core.golpes.assinatura import VERSAO_ASSINATURA
from chess_trainer.core.golpes.service import assinatura_de, irmaos
from chess_trainer.core.models import GolpeLabel, LichessPuzzle, LichessPuzzleSignature, Puzzle, PuzzleSignature
from chess_trainer.core.tactics.convert import to_tactic

LABELS = ("mesmo", "parecido", "nada")


def _ancoras_proprias(db: Session) -> list[str]:
    """Ids de exercícios do usuário com assinatura de golpe, em ordem estável."""
    return list(db.scalars(
        select(Puzzle.id).join(PuzzleSignature, PuzzleSignature.puzzle_id == Puzzle.id).order_by(Puzzle.id)))


def _ancoras_lichess(db: Session) -> list[str]:
    """Ids de puzzles do Lichess com assinatura de golpe, em ordem estável."""
    return list(db.scalars(
        select(LichessPuzzle.id).join(LichessPuzzleSignature, LichessPuzzleSignature.puzzle_id == LichessPuzzle.id)
        .order_by(LichessPuzzle.id)))


def _sortear_ancora(db: Session, rng: random.Random) -> tuple[str, str] | None:
    """Exercício próprio com assinatura, se houver; senão um puzzle do Lichess assinado ao acaso."""
    proprias = _ancoras_proprias(db)
    if proprias:
        return "own", rng.choice(proprias)
    lichess = _ancoras_lichess(db)
    return ("lichess", rng.choice(lichess)) if lichess else None


def _anchor_payload(origem: str, id: str, texto: str, puzzle_row) -> dict:
    """{"origem", "id", "assinatura", "tactic"|"puzzle"}: `tactic` para um puzzle do
    Lichess (mesmo formato dos candidatos), `puzzle` para um exercício próprio."""
    payload = {"origem": origem, "id": id, "assinatura": texto}
    if origem == "own":
        payload["puzzle"] = {"id": puzzle_row.id, "fen_start": puzzle_row.fen_start,
                             "solution": puzzle_row.solution_data}
    else:
        payload["tactic"] = asdict(to_tactic(puzzle_row))
    return payload


def proximo_item(db: Session, settings: AppSettings, rng: random.Random | None = None, por_camada: int = 3,
                 ancora: tuple[str, str] | None = None) -> dict | None:
    """Uma âncora (dada ou sorteada) e seus candidatos ainda não rotulados, embaralhados
    para a tela de rotulagem. Sem rating a filtrar (o julgamento é sobre o golpe, não
    sobre a dificuldade); pares já rotulados para esta âncora não voltam."""
    rng = rng or random.Random()
    if ancora is not None:
        origem, aid = ancora
    else:
        sorteio = _sortear_ancora(db, rng)
        if sorteio is None:
            return None
        origem, aid = sorteio
    achado = assinatura_de(db, origem, aid)
    if achado is None:
        return None
    a, _fen, _lances = achado
    puzzle_row = db.get(Puzzle, aid) if origem == "own" else db.get(LichessPuzzle, aid)
    if puzzle_row is None:
        return None
    try:
        anchor = _anchor_payload(origem, aid, a.destinos(), puzzle_row)
    except ValueError:
        return None
    ja_rotulados = set(db.scalars(
        select(GolpeLabel.candidate_id).where(GolpeLabel.anchor_origem == origem, GolpeLabel.anchor_id == aid)))
    candidatos = []
    for irmao in irmaos(db, a, rating_lo=0, rating_hi=4000, excluir=ja_rotulados | {aid}, k=por_camada):
        try:
            candidatos.append({"id": irmao.row.id, "tier": irmao.tier, "tactic": asdict(to_tactic(irmao.row))})
        except ValueError:
            continue
    rng.shuffle(candidatos)
    return {"anchor": anchor, "candidatos": candidatos}


def rotular(db: Session, *, anchor_origem: str, anchor_id: str, candidate_id: str, tier: str, label: str) -> GolpeLabel:
    """Grava o julgamento humano de um par (âncora, candidato) da cascata (spec §8)."""
    if label not in LABELS:
        raise ValueError(f"rótulo inválido: {label!r} (esperado {LABELS})")
    linha = GolpeLabel(anchor_origem=anchor_origem, anchor_id=anchor_id, candidate_id=candidate_id,
                       tier_na_hora=tier, versao_assinatura=VERSAO_ASSINATURA, label=label)
    db.add(linha)
    db.commit()
    return linha


def exportar_ouro(db: Session) -> str:
    """JSONL do conjunto de ouro: uma linha por rótulo gravado, com as assinaturas
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
            "created_at": label.created_at.isoformat(),
        }, ensure_ascii=False) + "\n")
    return "".join(linhas)
