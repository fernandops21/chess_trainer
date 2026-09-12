"""Conjunto de avaliação do treinador (spec §8.1): os puzzles próprios do
banco mais uma amostra estratificada do Lichess, cada um com o gabarito da
engine nas posições inicial e do erro. Sem texto de terceiros.

Gerar (só o usuário, contra o banco real):
    cd backend && uv run python -m evals.coach.dataset --saida evals/coach/dataset/v1.json
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import chess
from sqlalchemy import select
from sqlalchemy.orm import Session

from chess_trainer.coach.tools import ContextoExercicio, contexto_do_exercicio
from chess_trainer.coach.verify import Analisar
from chess_trainer.core.models import LichessPuzzle, LichessPuzzleTheme, Puzzle
from chess_trainer.core.tactics.convert import to_tactic
from chess_trainer.core.tactics.themes import THEME_LABELS

TEMAS_GENERICOS = {"short", "long", "veryLong", "oneMove", "middlegame", "endgame", "opening", "crushing", "advantage",
                   "equality", "mate", "master", "masterVsMaster", "superGM"}
FAIXAS = ((0, 1399), (1400, 1799), (1800, 9999))
N_TEMAS = 10


@dataclass
class ItemAvaliacao:
    id: str
    origem: str
    contexto: dict
    rating: int | None
    gabarito: dict


def contexto_de_item(item: ItemAvaliacao) -> ContextoExercicio:
    d = dict(item.contexto)
    d["lances_permitidos"] = set(d.get("lances_permitidos", []))
    return ContextoExercicio(**d)


def _gabarito(ctx: ContextoExercicio, analisar: Analisar) -> dict:
    g = {"inicial": analisar(ctx.fen_inicial, 3), "erro": None}
    if ctx.fen_erro:
        g["erro"] = analisar(ctx.fen_erro, 3)
    return g


def _contexto_lichess(row: LichessPuzzle) -> ContextoExercicio:
    t = to_tactic(row)
    board = chess.Board(t.fen_start)
    solucao = []
    for m in t.solution["moves"]:
        mv = chess.Move.from_uci(m["uci"])
        solucao.append(board.san(mv))
        board.push(mv)
    antes = chess.Board(t.fen_before)
    ultimo = chess.Move.from_uci(t.last_move)
    return ContextoExercicio(
        puzzle_id=f"lichess:{row.id}", tipo="lichess", lado="brancas" if t.side_to_move == "white" else "pretas",
        fen_inicial=t.fen_start, fen_erro=t.fen_before, solucao_san=solucao,
        lance_errado={"san": antes.san(ultimo), "uci": t.last_move, "de_quem": "adversário", "nivel": None, "aval_antes": None, "aval_depois": None},
        minha_resposta=None, partida=None, tema=THEME_LABELS.get(t.theme, t.theme), categoria="lichess",
        lances_permitidos={t.solution["moves"][0]["uci"], t.last_move},
    )


def _amostra_lichess(db: Session, n: int, seed: int) -> list[LichessPuzzle]:
    if n <= 0:
        return []
    rnd = random.Random(seed)
    contagem = Counter(t for (t,) in db.execute(select(LichessPuzzleTheme.theme)).all() if t not in TEMAS_GENERICOS)
    temas = [t for t, _ in contagem.most_common(N_TEMAS)]
    por_celula = max(1, n // max(1, len(temas) * len(FAIXAS)))
    escolhidos: dict[str, LichessPuzzle] = {}
    for tema in temas:
        for lo, hi in FAIXAS:
            ids = list(db.scalars(select(LichessPuzzleTheme.puzzle_id).join(LichessPuzzle, LichessPuzzle.id == LichessPuzzleTheme.puzzle_id)
                                  .where(LichessPuzzleTheme.theme == tema, LichessPuzzle.rating >= lo, LichessPuzzle.rating <= hi)))
            rnd.shuffle(ids)
            for pid in ids[:por_celula]:
                if pid not in escolhidos:
                    escolhidos[pid] = db.get(LichessPuzzle, pid)
            if len(escolhidos) >= n:
                break
    return list(escolhidos.values())[:n]


def montar(db: Session, analisar: Analisar, n_lichess: int = 120, seed: int = 7) -> list[ItemAvaliacao]:
    items: list[ItemAvaliacao] = []
    for p in db.scalars(select(Puzzle).where(Puzzle.source == "own").order_by(Puzzle.created_at)):
        ctx = contexto_do_exercicio(db, p)
        items.append(ItemAvaliacao(id=f"own:{p.id}", origem="own", contexto=ctx.to_dict(), rating=None, gabarito=_gabarito(ctx, analisar)))
    for row in _amostra_lichess(db, n_lichess, seed):
        try:
            ctx = _contexto_lichess(row)
        except ValueError:
            continue
        items.append(ItemAvaliacao(id=f"lichess:{row.id}", origem="lichess", contexto=ctx.to_dict(), rating=row.rating, gabarito=_gabarito(ctx, analisar)))
    return items


def salvar(items: list[ItemAvaliacao], path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps([asdict(i) for i in items], ensure_ascii=False, indent=1), encoding="utf-8")


def carregar(path: Path) -> list[ItemAvaliacao]:
    return [ItemAvaliacao(**d) for d in json.loads(Path(path).read_text(encoding="utf-8"))]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Gera o conjunto de avaliação do treinador a partir do banco do app.")
    ap.add_argument("--saida", default="evals/coach/dataset/v1.json")
    ap.add_argument("--n-lichess", type=int, default=120)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)
    from evals.coach.run import _analisar, _db
    db = _db()
    try:
        items = montar(db, _analisar(), args.n_lichess, args.seed)
    finally:
        db.close()
    salvar(items, Path(args.saida))
    print(f"{len(items)} itens em {args.saida}")


if __name__ == "__main__":
    main()
