"""Assinaturas no banco: calcular para o Lichess e para os exercícios do usuário (spec golpes §4)."""
from __future__ import annotations

import json

import chess
from sqlalchemy.orm import Session

from chess_trainer.core.golpes.assinatura import VERSAO_ASSINATURA, Assinatura, assinar
from chess_trainer.core.models import LichessPuzzle, LichessPuzzleSignature, Puzzle, PuzzleSignature


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
