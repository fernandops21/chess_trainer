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
from chess_trainer.core.golpes.assinatura import VERSAO_ASSINATURA, Assinatura, Trecho, assinar, assinar_com_trechos, trechos
from chess_trainer.core.models import (
    LichessPuzzle, LichessPuzzleSignature, LichessPuzzleTrecho, Puzzle, PuzzleSignature,
)

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


def trechos_lichess(row: LichessPuzzle) -> list[Trecho] | None:
    """Os trechos (spec golpes trechos §3.5) da solução de um puzzle do Lichess; `None` na
    mesma condição de `assinar_lichess` (linha inválida)."""
    par = _lances_lichess(row)
    if par is None:
        return None
    try:
        return trechos(par[0], par[1])
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


def linha_de_trecho(t: Trecho, puzzle_id: str) -> LichessPuzzleTrecho:
    h = t.assinatura.hashes()
    return LichessPuzzleTrecho(puzzle_id=puzzle_id, inicio=t.inicio, n=t.n, posicao=t.posicao,
                               destinos=h["destinos"], destinos_esp=h["destinos_esp"],
                               # o esqueleto de um lance só combina com quase tudo (ruído): não
                               # é gravado nem buscado (spec golpes trechos §4.1)
                               esqueleto=None if t.n == 1 else h["esqueleto"])


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
        db.execute(delete(LichessPuzzleTrecho).where(LichessPuzzleTrecho.puzzle_id.in_(ids)))
        db.flush()
        for row in rows:
            # assinatura e trechos numa passada só pela solução (o milhão agradece)
            par = _lances_lichess(row)
            if par is None:
                continue
            try:
                a, ts = assinar_com_trechos(par[0], par[1])
            except ValueError:
                continue
            db.add(linha_de_assinatura(a, LichessPuzzleSignature, row.id))
            db.add_all([linha_de_trecho(t, row.id) for t in ts])
        db.commit()
        feitos += len(ids)
        progress(NOME_TAREFA, feitos, total, f"{feitos}/{total} puzzles")
    set_setting(db, "golpes_cobertura", cobertura(db))
    set_setting(db, "golpes_assinados", db.scalar(select(func.count()).select_from(LichessPuzzleSignature)) or 0)
    set_setting(db, "golpes_trechos", db.scalar(select(func.count()).select_from(LichessPuzzleTrecho)) or 0)
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


@dataclass(frozen=True)
class Procedencia:
    """De onde veio um irmão na cascata (spec golpes trechos §5): o degrau, o nível de
    assinatura comparado (`destinos` | `destinos_esp` | `esqueleto`), quantos lances do
    solucionador entraram na comparação, a posição do trecho combinado na solução do
    CANDIDATO ("inteira" para os degraus de assinatura inteira) e se foi por espelho."""
    degrau: str
    nivel: str
    n: int
    posicao: str
    espelhado: bool


@dataclass
class Irmao:
    row: LichessPuzzle
    tier: str  # o degrau da procedência, repetido aqui por compatibilidade da API
    procedencia: Procedencia


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


def _candidatos_trecho(db: Session, coluna: str, n: int, valor: int, excluir: set[str], centro: int,
                       min_popularity: int, min_plays: int) -> tuple[list[tuple[str, int]], dict[str, tuple[int, str]]]:
    """Como `_candidatos`, mas contra `lichess_puzzle_trechos`: `coluna` é `destinos` ou
    `esqueleto`, `valor` o hash do trecho da ÂNCORA a procurar em qualquer posição da solução
    de um candidato. Um candidato pode ter mais de um trecho de tamanho `n` que combine (a
    mesma peça se repete geometricamente na solução dele); fica o de menor `inicio` (spec golpes
    trechos §5). Devolve os candidatos e, à parte, `inicio`/`posicao` do trecho que casou —
    a procedência do candidato, não da âncora."""
    col = getattr(LichessPuzzleTrecho, coluna)
    sub = (select(LichessPuzzleTrecho.puzzle_id, func.min(LichessPuzzleTrecho.inicio).label("inicio"))
           .where(col == valor, LichessPuzzleTrecho.n == n).group_by(LichessPuzzleTrecho.puzzle_id).subquery())
    q = (select(LichessPuzzle.id, LichessPuzzle.rating, sub.c.inicio)
         .join(sub, sub.c.puzzle_id == LichessPuzzle.id)
         .where(LichessPuzzle.popularity >= min_popularity, LichessPuzzle.nb_plays >= min_plays)
         .order_by(func.abs(LichessPuzzle.rating - centro), LichessPuzzle.id).limit(LIMITE_CANDIDATOS))
    linhas = [(pid, rating, inicio) for pid, rating, inicio in db.execute(q) if pid not in excluir]
    if not linhas:
        return [], {}
    posicoes = {(t.puzzle_id, t.inicio): t.posicao for t in db.scalars(
        select(LichessPuzzleTrecho).where(LichessPuzzleTrecho.n == n,
                                          LichessPuzzleTrecho.puzzle_id.in_([pid for pid, _r, _i in linhas])))}
    prov = {pid: (inicio, posicoes.get((pid, inicio), "meio")) for pid, _r, inicio in linhas}
    return [(pid, rating) for pid, rating, _i in linhas], prov


def _passos(a: Assinatura, meus_trechos: dict[int, "Trecho"], k: int, incluir_extra_rotulagem: bool):
    """A cascata em degraus (spec golpes trechos §5), na ordem: assinatura inteira → trechos
    (do maior prefixo ao menor) → espelho inteiro → trechos espelhados → esqueleto inteiro →
    trechos por esqueleto. `meus_trechos` são os PRÓPRIOS trechos da âncora com `inicio == 0`
    (os prefixos dela, de `trechos(fen, lances)`); um trecho de tamanho `n` só entra quando a
    âncora tiver um. `incluir_extra_rotulagem` acrescenta `espelho-trecho1`, único degrau que
    usa o esqueleto de um lance só — bom demais para achar pares (ruído) para entrar no bloco,
    mas útil para a rotulagem medir o quanto ele erra (spec §8). Cada item da lista devolvida é
    `(degrau, nivel, n, espelhado, eh_trecho, valor)`."""
    h = a.hashes()
    passos = [("inteira", "destinos", k, False, False, h["destinos"])]
    for n in range(k, 0, -1):
        t = meus_trechos.get(n)
        if t is not None:
            passos.append((f"trecho{n}", "destinos", n, False, True, t.assinatura.hashes()["destinos"]))
    passos.append(("espelho", "destinos_esp", k, True, False, h["destinos_esp"]))
    for n in range(k, 1, -1):
        t = meus_trechos.get(n)
        if t is not None:
            passos.append((f"espelho-trecho{n}", "destinos_esp", n, True, True, t.assinatura.hashes()["destinos_esp"]))
    passos.append(("esqueleto", "esqueleto", k, False, False, h["esqueleto"]))
    for n in range(k, 1, -1):
        t = meus_trechos.get(n)
        if t is not None:
            passos.append((f"esqueleto-trecho{n}", "esqueleto", n, False, True, t.assinatura.hashes()["esqueleto"]))
    if incluir_extra_rotulagem:
        t1 = meus_trechos.get(1)
        if t1 is not None:
            passos.append(("espelho-trecho1", "destinos_esp", 1, True, True, t1.assinatura.hashes()["destinos_esp"]))
    return passos


def _meus_trechos(fen: str, lances: list[str]) -> dict[int, "Trecho"]:
    """Os prefixos da própria âncora (`inicio == 0` de `trechos`), por tamanho: as consultas da
    cascata por trecho comparam esses hashes contra qualquer posição da solução do candidato."""
    return {t.n: t for t in trechos(fen, lances) if t.inicio == 0}


def _executar_passo(db: Session, nivel: str, n: int, eh_trecho: bool, valor: int, zona_rei: str,
                    excluir: set[str], centro: int, min_popularity: int, min_plays: int):
    """Roda um degrau da cascata: devolve os candidatos (id, rating) e, se for um degrau de
    trecho, a procedência bruta (`inicio`, `posicao`) de cada um — `None` num degrau de
    assinatura inteira, onde a posição do casamento é sempre a solução inteira."""
    coluna = "esqueleto" if nivel == "esqueleto" else "destinos"
    if eh_trecho:
        return _candidatos_trecho(db, coluna, n, valor, excluir, centro, min_popularity, min_plays)
    cond = getattr(LichessPuzzleSignature, coluna) == valor
    if nivel == "esqueleto":
        cond = cond & (LichessPuzzleSignature.zona_rei == zona_rei)
    return _candidatos(db, cond, excluir, centro, min_popularity, min_plays), None


def irmaos(db: Session, fen: str, lances: list[str], *, rating: int, abaixo: int = 100, acima: int = 500,
          excluir: set[str], k: int = 5, min_popularity: int = 50, min_plays: int = 50) -> list[Irmao]:
    """Cascata (spec golpes trechos §5): assinatura inteira → trechos (prefixos da âncora, do
    maior ao menor) → espelho inteiro → trechos espelhados → esqueleto inteiro → trechos por
    esqueleto. A busca ignora rating (quem decide o degrau é o golpe); o rating só escolhe quem
    aparece no bloco, preferindo a faixa `[rating - abaixo, rating + acima]` e completando de
    fora dela quando falta (`escolher_por_rating`). O que já saiu num degrau não volta nos
    seguintes. Ids primeiro, linhas completas só dos escolhidos no final: a tabela do Lichess tem
    milhões de linhas. O bloco final fica em ordem ascendente de rating, mesmo cruzando degraus."""
    a = assinar(fen, lances)
    k_ = min(len(a.lances), 3)
    passos = _passos(a, _meus_trechos(fen, lances), k_, incluir_extra_rotulagem=False)
    lo, hi = rating - abaixo, rating + acima
    centro = (lo + hi) // 2
    escolhidos: list[tuple[str, str, Procedencia]] = []
    usados = set(excluir)
    for nome, nivel, n, espelhado, eh_trecho, valor in passos:
        if len(escolhidos) >= k:
            break
        cands, prov = _executar_passo(db, nivel, n, eh_trecho, valor, a.zona_rei, usados, centro,
                                      min_popularity, min_plays)
        for pid in escolher_por_rating(cands, k - len(escolhidos), lo, hi):
            posicao = "inteira" if prov is None else prov[pid][1]
            escolhidos.append((pid, nome, Procedencia(degrau=nome, nivel=nivel, n=n, posicao=posicao, espelhado=espelhado)))
            usados.add(pid)
    linhas = {r.id: r for r in db.scalars(
        select(LichessPuzzle).where(LichessPuzzle.id.in_([pid for pid, _nome, _proc in escolhidos])))}
    escolhidos.sort(key=lambda item: (linhas[item[0]].rating, item[0]))
    return [Irmao(linhas[pid], nome, proc) for pid, nome, proc in escolhidos]


def candidatos_por_camada(db: Session, fen: str, lances: list[str], *, excluir: set[str], k: int,
                          por_degrau: int | None = None, min_popularity: int = 50,
                          min_plays: int = 50) -> dict[str, list[Irmao]]:
    """Todos os degraus da cascata (spec golpes trechos §5) à parte, até `por_degrau` (ou `k`, se
    omitido) de cada um, espalhados do fácil ao difícil (sem faixa de rating: a rotulagem julga o
    golpe, não a dificuldade) — diferente de `irmaos`, que cascateia até completar `k` no total e
    por isso nunca chega aos degraus seguintes quando os primeiros já bastam sozinhos. Inclui
    `espelho-trecho1` (nunca usado no bloco): a rotulagem precisa medir o quanto esse degrau erra.
    Quem combina com um degrau mais específico não some dos mais frouxos por não ter sido um dos
    escolhidos ali (senão o mesmo puzzle apareceria de novo, rotulado uma vez em cada); por isso o
    que exclui o degrau seguinte é todo mundo que combinou, não só os escolhidos."""
    a = assinar(fen, lances)
    k_ = min(len(a.lances), 3)
    passos = _passos(a, _meus_trechos(fen, lances), k_, incluir_extra_rotulagem=True)
    n_por_degrau = por_degrau if por_degrau is not None else k
    usados = set(excluir)
    por_degrau_bruto: dict[str, tuple[list[str], dict, str, int, bool]] = {}
    for nome, nivel, n, espelhado, eh_trecho, valor in passos:
        # `centro=0`: rating nunca é negativo, então `abs(rating - 0) == rating` e a ordem sai
        # crescente — os candidatos vêm do fácil ao difícil sem precisar de outra consulta.
        cands, prov = _executar_passo(db, nivel, n, eh_trecho, valor, a.zona_rei, usados, 0,
                                      min_popularity, min_plays)
        ids = [pid for pid, _rating in cands]
        por_degrau_bruto[nome] = (espalhar(ids, n_por_degrau), prov, nivel, n, espelhado)
        usados |= set(ids)
    todos_ids = {pid for ids, _p, _nv, _n, _e in por_degrau_bruto.values() for pid in ids}
    linhas = {r.id: r for r in db.scalars(select(LichessPuzzle).where(LichessPuzzle.id.in_(todos_ids)))}
    resultado: dict[str, list[Irmao]] = {}
    for nome, (ids, prov, nivel, n, espelhado) in por_degrau_bruto.items():
        itens = []
        for pid in ids:
            posicao = "inteira" if prov is None else prov[pid][1]
            itens.append(Irmao(linhas[pid], nome, Procedencia(degrau=nome, nivel=nivel, n=n, posicao=posicao, espelhado=espelhado)))
        resultado[nome] = itens
    return resultado
