"""Assinaturas no banco: calcular para o Lichess e para os exercícios do usuário (spec golpes §4);
busca de irmãos em cascata para um exercício (spec golpes §5)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

import chess
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from chess_trainer.config import set_setting
from chess_trainer.core.golpes.assinatura import VERSAO_ASSINATURA, Assinatura, assinar
from chess_trainer.core.models import LichessPuzzle, LichessPuzzleSignature, Puzzle, PuzzleSignature

ProgressFn = Callable[[str, int, int, str], None]
NOME_TAREFA = "golpes_preparar"


def _lances_lichess(row: LichessPuzzle) -> tuple[str, list[str]] | None:
    """(fen da posição do puzzle, lances da solução). `moves[0]` é o lance de preparação do adversário."""
    ucis = row.moves.split()
    if len(ucis) < 2:
        return None
    try:
        board = chess.Board(row.fen)
        board.push(chess.Move.from_uci(ucis[0]))
    except ValueError:
        return None
    return board.fen(), ucis[1:]


def assinar_lichess(row: LichessPuzzle) -> Assinatura | None:
    par = _lances_lichess(row)
    if par is None:
        return None
    try:
        return assinar(par[0], par[1])
    except ValueError:
        return None


def _lances_proprio(puzzle: Puzzle) -> list[str]:
    return [m["uci"] for m in json.loads(puzzle.solution).get("moves", [])]


def assinar_proprio(puzzle: Puzzle) -> Assinatura | None:
    try:
        return assinar(puzzle.fen_start, _lances_proprio(puzzle))
    except ValueError:
        return None


def linha_de_assinatura(a: Assinatura, cls, puzzle_id: str):
    h = a.hashes()
    return cls(puzzle_id=puzzle_id, versao=VERSAO_ASSINATURA, esqueleto=h["esqueleto"], destinos=h["destinos"],
               destinos_esp=h["destinos_esp"], completo=h["completo"], texto_completo=a.completo(),
               zona_rei=a.zona_rei, n_lances=len(a.lances))


def garantir_assinatura(db: Session, puzzle: Puzzle) -> PuzzleSignature | None:
    """Grava a assinatura do exercício se faltar ou estiver com versão antiga."""
    atual = db.get(PuzzleSignature, puzzle.id)
    if atual is not None and atual.versao == VERSAO_ASSINATURA:
        return atual
    a = assinar_proprio(puzzle)
    if a is None:
        return None
    if atual is not None:
        db.delete(atual)
        db.flush()
    linha = linha_de_assinatura(a, PuzzleSignature, puzzle.id)
    db.add(linha)
    db.flush()
    return linha


def assinatura_de(db: Session, origem: str, id: str) -> tuple[Assinatura, str, list[str]] | None:
    """Assinatura, posição e lances de um exercício próprio (`own`) ou de um puzzle do Lichess."""
    if origem == "own":
        puzzle = db.get(Puzzle, id)
        if puzzle is None:
            return None
        a = assinar_proprio(puzzle)
        return None if a is None else (a, puzzle.fen_start, _lances_proprio(puzzle))
    if origem == "lichess":
        row = db.get(LichessPuzzle, id)
        if row is None:
            return None
        par = _lances_lichess(row)
        if par is None:
            return None
        try:
            return assinar(par[0], par[1]), par[0], par[1]
        except ValueError:
            return None
    return None


def _pendentes(db: Session):
    """Ids do Lichess sem assinatura ou com versão antiga."""
    return (select(LichessPuzzle.id).outerjoin(LichessPuzzleSignature, LichessPuzzleSignature.puzzle_id == LichessPuzzle.id)
            .where((LichessPuzzleSignature.puzzle_id.is_(None)) | (LichessPuzzleSignature.versao < VERSAO_ASSINATURA))
            .order_by(LichessPuzzle.id))


def preparar(db: Session, progress: ProgressFn, should_stop: Callable[[], bool] | None = None, lote: int = 5000) -> int:
    """Assina o que falta, em lotes, com progresso e cancelamento. Percorre os pendentes por um
    cursor de id: puzzle inválido do Lichess (dado ruim: menos de dois lances, lance ilegal) não
    ganha linha, e sem o cursor ele voltaria no mesmo lote para sempre nesta chamada. Entre uma
    chamada e outra, porém, ele continua pendente e é retentado — raro e barato, sem exclusão
    persistida. Devolve quantos puzzles foram processados (válidos ou não)."""
    total = db.scalar(select(func.count()).select_from(_pendentes(db).subquery())) or 0
    progress(NOME_TAREFA, 0, total, "contando")
    feitos = 0
    ultimo = ""
    while True:
        if should_stop is not None and should_stop():
            progress(NOME_TAREFA, feitos, total, "cancelado")
            return feitos
        ids = list(db.scalars(_pendentes(db).where(LichessPuzzle.id > ultimo).limit(lote)))
        if not ids:
            break
        ultimo = ids[-1]
        rows = db.scalars(select(LichessPuzzle).where(LichessPuzzle.id.in_(ids))).all()
        # versão antiga: apaga em massa antes de entrar a nova
        db.execute(delete(LichessPuzzleSignature).where(LichessPuzzleSignature.puzzle_id.in_(ids)))
        db.flush()
        for row in rows:
            a = assinar_lichess(row)
            if a is not None:
                db.add(linha_de_assinatura(a, LichessPuzzleSignature, row.id))
        db.commit()
        feitos += len(ids)
        progress(NOME_TAREFA, feitos, total, f"{feitos}/{total} puzzles")
    set_setting(db, "golpes_cobertura", cobertura(db))
    set_setting(db, "golpes_assinados", db.scalar(select(func.count()).select_from(LichessPuzzleSignature)) or 0)
    progress(NOME_TAREFA, total, total, "concluído")
    return feitos


def cobertura(db: Session) -> dict[str, dict[str, int]]:
    """Por nível: quantos puzzles têm grupo ≥ 5, ≥ 2 e ficam sozinhos (spec §4.2)."""
    out = {}
    for nivel in ("esqueleto", "destinos", "completo"):
        col = getattr(LichessPuzzleSignature, nivel)
        grupos = select(func.count().label("c")).select_from(LichessPuzzleSignature).group_by(col).subquery()
        ge5, ge2, solos = db.execute(select(
            func.coalesce(func.sum(func.iif(grupos.c.c >= 5, grupos.c.c, 0)), 0),
            func.coalesce(func.sum(func.iif(grupos.c.c >= 2, grupos.c.c, 0)), 0),
            func.coalesce(func.sum(func.iif(grupos.c.c == 1, 1, 0)), 0),
        )).one()
        out[nivel] = {"ge5": int(ge5), "ge2": int(ge2), "sozinhos": int(solos)}
    return out


@dataclass
class Irmao:
    row: LichessPuzzle
    tier: str  # mesmo | espelho | esqueleto


def espalhar(itens: list, k: int) -> list:
    """k itens espalhados ao longo de uma lista ordenada: do fácil ao difícil, sem se amontoar."""
    n = len(itens)
    if n <= k:
        return list(itens)
    if k == 1:
        return [itens[0]]
    posicoes = sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})
    return [itens[p] for p in posicoes]


def _candidatos(db: Session, cond, rating_lo: int, rating_hi: int, excluir: set[str], min_popularity: int, min_plays: int):
    q = (select(LichessPuzzle).join(LichessPuzzleSignature, LichessPuzzleSignature.puzzle_id == LichessPuzzle.id)
         .where(cond, LichessPuzzle.rating.between(rating_lo, rating_hi),
                LichessPuzzle.popularity >= min_popularity, LichessPuzzle.nb_plays >= min_plays)
         .order_by(LichessPuzzle.rating, LichessPuzzle.id))
    return [r for r in db.scalars(q) if r.id not in excluir]


def irmaos(db: Session, a: Assinatura, *, rating_lo: int, rating_hi: int, excluir: set[str], k: int = 5,
           min_popularity: int = 50, min_plays: int = 50) -> list[Irmao]:
    """Cascata (spec §5): mesmo golpe → espelho → esqueleto na mesma zona. Cada camada enche o que
    falta, espalhada do fácil ao difícil; o que já saiu numa camada não volta na seguinte."""
    h = a.hashes()
    camadas = [
        ("mesmo", LichessPuzzleSignature.destinos == h["destinos"]),
        ("espelho", LichessPuzzleSignature.destinos == h["destinos_esp"]),
        ("esqueleto", (LichessPuzzleSignature.esqueleto == h["esqueleto"]) & (LichessPuzzleSignature.zona_rei == a.zona_rei)),
    ]
    out: list[Irmao] = []
    usados = set(excluir)
    for tier, cond in camadas:
        if len(out) >= k:
            break
        cands = _candidatos(db, cond, rating_lo, rating_hi, usados, min_popularity, min_plays)
        for row in espalhar(cands, k - len(out)):
            out.append(Irmao(row, tier))
            usados.add(row.id)
    return out
