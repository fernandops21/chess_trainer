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


def refazer_assinatura(db: Session, puzzle: Puzzle) -> PuzzleSignature | None:
    """Descarta a assinatura gravada e recalcula, mesmo com a versão em dia: para quando a
    solução do exercício mudou (extensão da linha, edição do capítulo, gêmeo adotado) e
    `garantir_assinatura` sozinho voltaria cedo demais, por já ver a versão certa na linha
    antiga."""
    atual = db.get(PuzzleSignature, puzzle.id)
    if atual is not None:
        db.delete(atual)
        db.flush()
    return garantir_assinatura(db, puzzle)


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


# cortados pelos mais próximos do centro da faixa preferida (ou do fácil ao difícil, em
# `candidatos_por_camada`); 5000 é mais do que qualquer bloco espalha e cabe na memória
LIMITE_CANDIDATOS = 5000


def espalhar(itens: list, k: int) -> list:
    """k itens espalhados ao longo de uma lista ordenada: do fácil ao difícil, sem se amontoar."""
    n = len(itens)
    if n <= k:
        return list(itens)
    if k == 1:
        return [itens[0]]
    posicoes = sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})
    return [itens[p] for p in posicoes]


def _candidatos(db: Session, cond, excluir: set[str], centro: int, min_popularity: int,
                min_plays: int) -> list[tuple[str, int]]:
    """Ids e rating candidatos, sem materializar a linha inteira nem a tabela toda: só (id,
    rating), até `LIMITE_CANDIDATOS` — os mais próximos de `centro`, não os mais fáceis: quem
    decide a camada é o golpe (sem filtro de rating aqui), e o corte de segurança deve cobrir a
    faixa preferida em volta de `centro`, não só as táticas mais fáceis do banco. A exclusão é
    aplicada depois, em Python."""
    q = (select(LichessPuzzle.id, LichessPuzzle.rating)
         .join(LichessPuzzleSignature, LichessPuzzleSignature.puzzle_id == LichessPuzzle.id)
         .where(cond, LichessPuzzle.popularity >= min_popularity, LichessPuzzle.nb_plays >= min_plays)
         .order_by(func.abs(LichessPuzzle.rating - centro), LichessPuzzle.id).limit(LIMITE_CANDIDATOS))
    return [(pid, rating) for pid, rating in db.execute(q) if pid not in excluir]


def escolher_por_rating(cands: list[tuple[str, int]], k: int, lo: int, hi: int) -> list[str]:
    """Dos candidatos (id, rating) de uma camada, escolhe até k para o bloco: a busca de irmãos
    ignora rating (quem decide a camada é o golpe), mas o bloco mostra do fácil ao difícil dentro
    da faixa preferida `[lo, hi]` do usuário. Primeiro espalha (fácil → difícil) os que caem na
    faixa; faltando, completa com os mais próximos de fora dela — primeiro os de cima (subindo),
    depois os de baixo (descendo, o mais perto primeiro)."""
    dentro = sorted(((r, pid) for pid, r in cands if lo <= r <= hi))
    escolhidos = espalhar([pid for _r, pid in dentro], k)
    faltam = k - len(escolhidos)
    if faltam <= 0:
        return escolhidos
    acima = sorted((r, pid) for pid, r in cands if r > hi)
    escolhidos += [pid for _r, pid in acima[:faltam]]
    faltam = k - len(escolhidos)
    if faltam <= 0:
        return escolhidos
    abaixo = sorted(((-r, pid) for pid, r in cands if r < lo))
    escolhidos += [pid for _r, pid in abaixo[:faltam]]
    return escolhidos


def _camadas(a: Assinatura):
    """As três condições da cascata (spec §5), na ordem: mesmo golpe → espelho → esqueleto
    na mesma zona. Compartilhada por `irmaos` (cascata, um total) e `candidatos_por_camada`
    (cada camada à parte, para a rotulagem)."""
    h = a.hashes()
    return [
        ("mesmo", LichessPuzzleSignature.destinos == h["destinos"]),
        ("espelho", LichessPuzzleSignature.destinos == h["destinos_esp"]),
        ("esqueleto", (LichessPuzzleSignature.esqueleto == h["esqueleto"]) & (LichessPuzzleSignature.zona_rei == a.zona_rei)),
    ]


def irmaos(db: Session, a: Assinatura, *, rating: int, abaixo: int = 100, acima: int = 500, excluir: set[str],
           k: int = 5, min_popularity: int = 50, min_plays: int = 50) -> list[Irmao]:
    """Cascata (spec §5): mesmo golpe → espelho → esqueleto na mesma zona. A busca de irmãos
    ignora rating (quem decide a camada é o golpe); o rating só escolhe quem aparece no bloco,
    preferindo a faixa `[rating - abaixo, rating + acima]` e completando de fora dela quando falta
    (`escolher_por_rating`). O que já saiu numa camada não volta na seguinte. Ids primeiro, linhas
    completas só dos escolhidos no final: a tabela do Lichess tem milhões de linhas. O bloco final
    fica em ordem ascendente de rating, mesmo cruzando camadas."""
    lo, hi = rating - abaixo, rating + acima
    centro = (lo + hi) // 2
    escolhidos: list[tuple[str, str]] = []  # (id, tier)
    usados = set(excluir)
    for tier, cond in _camadas(a):
        if len(escolhidos) >= k:
            break
        cands = _candidatos(db, cond, usados, centro, min_popularity, min_plays)
        for pid in escolher_por_rating(cands, k - len(escolhidos), lo, hi):
            escolhidos.append((pid, tier))
            usados.add(pid)
    linhas = {r.id: r for r in db.scalars(
        select(LichessPuzzle).where(LichessPuzzle.id.in_([pid for pid, _tier in escolhidos])))}
    escolhidos.sort(key=lambda par: (linhas[par[0]].rating, par[0]))
    return [Irmao(linhas[pid], tier) for pid, tier in escolhidos]


def candidatos_por_camada(db: Session, a: Assinatura, *, excluir: set[str], k: int,
                          min_popularity: int = 50, min_plays: int = 50) -> dict[str, list[LichessPuzzle]]:
    """As três camadas da cascata (spec §5) à parte, até `k` de cada uma, espalhadas do fácil
    ao difícil (sem faixa de rating: a rotulagem julga o golpe, não a dificuldade) — diferente de
    `irmaos`, que cascateia até completar `k` no total e por isso nunca chega às camadas seguintes
    quando a primeira já basta sozinha. Quem combina com uma camada mais específica não some pelas
    mais frouxas mesmo sem ter sido um dos `k` escolhidos ali (senão o mesmo puzzle apareceria de
    novo, rotulado uma vez como "mesmo" e outra como "esqueleto"): por isso o que exclui a camada
    seguinte é todo mundo que combinou, não só os escolhidos. A rotulagem usa esta função porque
    precisa ver as três camadas para formar o conjunto de ouro."""
    usados = set(excluir)
    ids_por_tier: dict[str, list[str]] = {}
    for tier, cond in _camadas(a):
        # `centro=0`: rating nunca é negativo, então `abs(rating - 0) == rating` e a ordem
        # sai crescente — os candidatos vêm do fácil ao difícil sem precisar de outra consulta.
        combinam = _candidatos(db, cond, usados, 0, min_popularity, min_plays)
        ids = [pid for pid, _rating in combinam]
        ids_por_tier[tier] = espalhar(ids, k)
        usados |= set(ids)
    linhas = {r.id: r for r in db.scalars(
        select(LichessPuzzle).where(LichessPuzzle.id.in_([pid for ids in ids_por_tier.values() for pid in ids])))}
    return {tier: [linhas[pid] for pid in ids] for tier, ids in ids_por_tier.items()}
