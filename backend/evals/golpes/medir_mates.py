"""Mede os detectores de padrão de mate (`core/golpes/mates.py`) contra a etiqueta do Lichess,
em TODOS os mates do banco — não só a amostra de 240 usada nos testes (spec golpes design
§3.6). Abre o banco só para leitura (não é uma tarefa do produto; roda por fora, à mão, nunca
durante um job) e imprime, por padrão aprovado, o recall e a precisão contra a etiqueta do
Lichess, e as contagens brutas — e, para os detectores CANDIDATOS (`PADROES_PARA_CANDIDATOS`,
ainda não aprovados para `padrao_de_mate`, só geram etiqueta própria em `preparar_padroes`), o
recall e o número de extras (sobras sem a etiqueta do Lichess), mais uma amostra de 10 extras
sorteados (id, FEN final, temas) para inspecionar à mão antes de aprovar qualquer um.

Regra para aprovar um detector novo (a mesma que aprovou os três atuais): recall ≥ 95% contra
a etiqueta do Lichess correspondente, com as sobras (falsos positivos) inspecionadas à mão.
Precisão baixa sozinha NÃO reprova um detector quando as sobras são estruturalmente corretas e
o Lichess só deixou de etiquetar (foi o caso do corredor, 26% com a tolerância de uma casa coberta, e do árabe, 77%); recall abaixo
do piso, sim — foi o que descartou os protótipos de dovetail, epaulette e boden (§3.6). O
corredor apertado (`corredor_apertado`, candidato a etiqueta própria) foi inspecionado por essa
mesma régua: recall 93,8% contra `backRankMate` (12 004/12 802) e 4 451 extras — a amostra veio
textbook (`Qe8#` contra f7/g7/h7, `Rf8#` com o rei em h8 atrás de g7/h7); a versão frouxa da
regra (qualquer peça própria à frente do rei, não só peão) tinha o dobro de extras, mas metade
era outra ideia (uma torre presa por cravada) e foi rejeitada.

Uso: `cd backend && uv run python -m evals.golpes.medir_mates` (lê `CHESS_TRAINER_DB`, ou o
caminho padrão do app; sempre em modo somente leitura — `mode=ro` na URI do SQLite, então o
script não conseguiria escrever mesmo tentando)."""
from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Sequence

import chess
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from chess_trainer.core.golpes.mates import PADROES, PADROES_PARA_CANDIDATOS, padrao_de_mate, padrao_para_candidato
from chess_trainer.core.models import LichessPuzzle, LichessPuzzleTheme

# do mais específico ao mais geral (mesma ordem de `PADROES`): usado para o recall aceitar um
# padrão mais específico que a própria etiqueta do Lichess (o detector sempre acha esse primeiro)
ESPECIFICIDADE = {nome: i for i, (nome, _detector) in enumerate(PADROES)}


def contar(pares: Sequence[tuple[str | None, frozenset[str]]]) -> dict[str, dict[str, int]]:
    """A função pura da medição (testada com a amostra em JSON; a parte que toca o banco real,
    `medir` abaixo, não é testada por unidade). `pares` é (padrão detectado ou `None`, temas do
    Lichess) de cada mate. Por padrão aprovado:
    - `lichess`/`recall_ok`: quantos o Lichess etiqueta com o tema e, desses, quantos o
      detector também classificou com esse tema ou um mais específico que ele aprova.
    - `detector`/`precisao_ok`: quantos o detector classificou com o tema e, desses, quantos o
      Lichess também etiqueta com ele (o resto são as sobras a inspecionar à mão)."""
    saida: dict[str, dict[str, int]] = {}
    for tema, _detector in PADROES:
        marcados = [d for d, temas in pares if tema in temas]
        recall_ok = sum(1 for d in marcados if d is not None and ESPECIFICIDADE[d] <= ESPECIFICIDADE[tema])
        detectados = [temas for d, temas in pares if d == tema]
        precisao_ok = sum(1 for temas in detectados if tema in temas)
        saida[tema] = {"lichess": len(marcados), "recall_ok": recall_ok,
                       "detector": len(detectados), "precisao_ok": precisao_ok}
    return saida


def contar_candidatos(pares: Sequence[tuple[str | None, frozenset[str]]]) -> dict[str, dict[str, int]]:
    """A mesma ideia de `contar`, mas para os detectores CANDIDATOS (`PADROES_PARA_CANDIDATOS`):
    ainda não entram em `padrao_de_mate` nem em `PADROES`, então não têm um lugar mais
    específico para "ceder" o recall — só `lichess` (quantos o Lichess etiqueta) e `recall_ok`
    (quantos desses o candidato também acha), `detector` (quantos o candidato achou) e `extras`
    (dos que o candidato achou, quantos SEM a etiqueta do Lichess — a amostra a inspecionar à
    mão antes de aprovar, spec golpes design §3.6)."""
    saida: dict[str, dict[str, int]] = {}
    for tema, _detector in PADROES_PARA_CANDIDATOS:
        marcados = [d for d, temas in pares if tema in temas]
        recall_ok = sum(1 for d in marcados if d == tema)
        detectados = [temas for d, temas in pares if d == tema]
        extras = sum(1 for temas in detectados if tema not in temas)
        saida[tema] = {"lichess": len(marcados), "recall_ok": recall_ok, "detector": len(detectados), "extras": extras}
    return saida


def _posicao_final(fen: str, moves: str) -> chess.Board | None:
    """A posição final de um puzzle do Lichess (`fen` antes do lance de preparo do adversário,
    `moves` começando por ele): `None` num dado inválido, para a medição não travar num puzzle
    ruim isolado."""
    try:
        board = chess.Board(fen)
    except ValueError:
        return None
    for uci in moves.split():
        try:
            mv = chess.Move.from_uci(uci)
        except ValueError:
            return None
        if not board.is_legal(mv):
            return None
        board.push(mv)
    return board


def medir(db: Session) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, int]], list[tuple[str, str, str]]]:
    """Lê todo `lichess_puzzles` etiquetado `mate` (a tag geral de xeque-mate do Lichess) e
    reduz para `contar` (padrões aprovados) e `contar_candidatos` (candidatos a etiqueta
    própria) acima — a única parte deste módulo que toca o banco. Devolve também uma amostra
    sorteada de até 10 extras do(s) candidato(s) — (id, FEN final, temas do Lichess) — para
    inspecionar à mão antes de aprovar qualquer detector novo (spec golpes design §3.6)."""
    ids_mate = select(LichessPuzzleTheme.puzzle_id).where(LichessPuzzleTheme.theme == "mate")
    pares: list[tuple[str | None, frozenset[str]]] = []
    pares_candidatos: list[tuple[str | None, frozenset[str]]] = []
    extras: list[tuple[str, str, str]] = []
    for row in db.scalars(select(LichessPuzzle).where(LichessPuzzle.id.in_(ids_mate))):
        board = _posicao_final(row.fen, row.moves)
        if board is None:
            continue
        temas = frozenset(row.theme_list)
        pares.append((padrao_de_mate(board), temas))
        candidato = padrao_para_candidato(board)
        pares_candidatos.append((candidato, temas))
        if candidato is not None and candidato not in temas:
            extras.append((row.id, board.fen(), row.themes))
    amostra = random.sample(extras, min(10, len(extras)))
    return contar(pares), contar_candidatos(pares_candidatos), amostra


def _relatar(contagens: dict[str, dict[str, int]]) -> None:
    for tema, c in contagens.items():
        recall = 100.0 * c["recall_ok"] / c["lichess"] if c["lichess"] else 0.0
        precisao = 100.0 * c["precisao_ok"] / c["detector"] if c["detector"] else 0.0
        print(f"{tema}: recall {recall:.1f}% ({c['recall_ok']}/{c['lichess']}) | "
             f"precisão {precisao:.1f}% ({c['precisao_ok']}/{c['detector']})")


def _relatar_candidatos(contagens: dict[str, dict[str, int]], amostra: list[tuple[str, str, str]]) -> None:
    print("\n-- candidatos a etiqueta própria (ainda fora de padrao_de_mate) --")
    for tema, c in contagens.items():
        recall = 100.0 * c["recall_ok"] / c["lichess"] if c["lichess"] else 0.0
        print(f"{tema}: recall {recall:.1f}% ({c['recall_ok']}/{c['lichess']}) | "
             f"{c['detector']} achados, {c['extras']} extras sem a etiqueta do Lichess")
    if amostra:
        print(f"\namostra de {len(amostra)} extras (id, FEN final, temas do Lichess):")
        for id_, fen, temas in amostra:
            print(f"  {id_}: {fen} | {temas}")


def main() -> None:
    # mesma derivação de caminho de `core/golpes/exportar_ouro.py`, ajustada para a
    # profundidade deste módulo (`evals/golpes/` em vez de `chess_trainer/core/golpes/`)
    backend_dir = Path(__file__).resolve().parents[2]
    data_dir = Path(os.environ.get("CHESS_TRAINER_DATA", str(backend_dir / "data")))
    db_path = os.environ.get("CHESS_TRAINER_DB", str(data_dir / "chess_trainer.db"))
    # somente leitura de propósito (URI `mode=ro`): este script mede, nunca grava — sem o
    # `make_engine` do app (que cria o arquivo se faltar e liga o WAL, ambos escritas)
    engine = create_engine(f"sqlite:///file:{db_path}?mode=ro&uri=true")
    with sessionmaker(bind=engine)() as db:
        aprovados, candidatos, amostra = medir(db)
        _relatar(aprovados)
        _relatar_candidatos(candidatos, amostra)


if __name__ == "__main__":
    main()
