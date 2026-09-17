"""Assinatura do golpe: o que a solução de um puzzle faz, em texto canônico (spec §3).

Puro: só python-chess. `anotar` descreve os lances de quem soluciona no tabuleiro dado;
`assinar` antes vira o tabuleiro para quem soluciona ser sempre as brancas, de modo que o
mesmo golpe jogado por qualquer cor tenha a mesma assinatura."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Sequence

import chess

VERSAO_ASSINATURA = 2
MAX_LANCES = 3
LETRA = {chess.PAWN: "P", chess.KNIGHT: "N", chess.BISHOP: "B", chess.ROOK: "R", chess.QUEEN: "Q", chess.KING: "K"}
VALOR = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
# quantas peças descobertas/atacadas entram por lance: as mais valiosas
LIMITE_ALVOS = 2


@dataclass(frozen=True)
class Lance:
    peca: str
    origem: str
    destino: str
    captura: str | None
    xeque: str  # "", "+", "++", "d+" (descoberto), "#"
    promocao: str | None
    descobertas: tuple[tuple[str, str, str], ...]  # (peça atacada, casa dela, casa de quem passa a atacar)
    ataques: tuple[tuple[str, str], ...]  # (peça atacada, casa dela) pela própria peça que moveu


@dataclass(frozen=True)
class Assinatura:
    rei: str
    lances: tuple[Lance, ...]

    @property
    def zona_rei(self) -> str:
        return zona(chess.parse_square(self.rei))

    def esqueleto(self) -> str:
        partes = []
        for l in self.lances:
            p = [l.peca] + ([f"x{l.captura}"] if l.captura else []) + ([l.xeque] if l.xeque else []) \
                + ([f"={l.promocao}"] if l.promocao else []) \
                + ([f"desc({''.join(sorted(d[0] for d in l.descobertas))})"] if l.descobertas else []) \
                + ([f"atk({''.join(sorted(a[0] for a in l.ataques))})"] if l.ataques else [])
            partes.append(" ".join(p))
        return " | ".join([f"K{self.zona_rei}", *partes])

    def destinos(self) -> str:
        partes = []
        for l in self.lances:
            p = [l.peca] + ([f"x{l.captura}"] if l.captura else []) + [l.destino] + ([l.xeque] if l.xeque else []) \
                + ([f"={l.promocao}"] if l.promocao else []) \
                + ([f"desc({','.join(f'{d[0]}{d[1]}' for d in l.descobertas)})"] if l.descobertas else []) \
                + ([f"atk({','.join(f'{a[0]}{a[1]}' for a in l.ataques)})"] if l.ataques else [])
            partes.append(" ".join(p))
        return " | ".join([f"K{self.rei}", *partes])

    def completo(self) -> str:
        partes = []
        for l in self.lances:
            p = [l.peca, f"{l.origem}-{l.destino}"] + ([f"x{l.captura}"] if l.captura else []) + ([l.xeque] if l.xeque else []) \
                + ([f"={l.promocao}"] if l.promocao else []) \
                + ([f"desc({','.join(f'{d[0]}{d[1]}<{d[2]}' for d in l.descobertas)})"] if l.descobertas else []) \
                + ([f"atk({','.join(f'{a[0]}{a[1]}' for a in l.ataques)})"] if l.ataques else [])
            partes.append(" ".join(p))
        return " | ".join([f"K{self.rei}", *partes])

    def espelhada(self) -> "Assinatura":
        """O mesmo golpe na outra ala: colunas trocadas (a<->h). Ataques e descobertas são
        simétricos, então basta trocar as casas no texto."""
        return Assinatura(_esp(self.rei), tuple(
            replace(l, origem=_esp(l.origem), destino=_esp(l.destino),
                    descobertas=tuple((p, _esp(c), _esp(q)) for p, c, q in l.descobertas),
                    ataques=tuple((p, _esp(c)) for p, c in l.ataques))
            for l in self.lances))

    def hashes(self) -> dict[str, int]:
        return {"esqueleto": hash64(self.esqueleto()), "destinos": hash64(self.destinos()),
                "destinos_esp": hash64(self.espelhada().destinos()), "completo": hash64(self.completo())}


def hash64(texto: str) -> int:
    """Os 8 primeiros bytes do BLAKE2b (spec §3.4) como inteiro com sinal: cabe num INTEGER do SQLite e indexa bem."""
    return int.from_bytes(hashlib.blake2b(texto.encode("utf-8")).digest()[:8], "big", signed=True)


def zona(casa: int) -> str:
    coluna = chess.square_file(casa)
    ala = "dama" if coluna < 3 else "centro" if coluna < 5 else "rei"
    return f"{ala}-{'fundo' if chess.square_rank(casa) >= 6 else 'exposto'}"


def _esp(casa: str) -> str:
    sq = chess.parse_square(casa)
    return chess.square_name(chess.square(7 - chess.square_file(sq), chess.square_rank(sq)))


def _alvos(board: chess.Board, cor_alvo: chess.Color) -> list[int]:
    """Casas das peças de `cor_alvo` que contam como alvo: nem rei nem peões (spec §3.3)."""
    return [sq for sq, p in board.piece_map().items()
            if p.color == cor_alvo and p.piece_type not in (chess.KING, chess.PAWN)]


def _atacadas_por_outras(board: chess.Board, quem: chess.Color, exceto: int) -> set[int]:
    """Peças adversárias atacadas por alguma peça de `quem` que não seja a da casa `exceto`."""
    return {sq for sq in _alvos(board, not quem) if any(a != exceto for a in board.attackers(quem, sq))}


def _mais_valiosas(board: chess.Board, casas: set[int]) -> list[int]:
    return sorted(casas, key=lambda sq: (-VALOR[board.piece_type_at(sq)], chess.square_name(sq)))[:LIMITE_ALVOS]


def _anotar_lance(board: chess.Board, mv: chess.Move) -> Lance:
    quem = board.turn
    peca = board.piece_type_at(mv.from_square)
    if peca is None or not board.is_legal(mv):
        raise ValueError(f"lance ilegal: {mv.uci()} em {board.fen()}")
    captura = "P" if board.is_en_passant(mv) else (LETRA[t] if (t := board.piece_type_at(mv.to_square)) else None)
    antes_outras = _atacadas_por_outras(board, quem, mv.from_square)
    antes_propria = set(board.attacks(mv.from_square))
    board.push(mv)
    xeque = ""
    if board.is_check():
        checkers = board.checkers()
        xeque = "++" if len(checkers) >= 2 else "+" if mv.to_square in checkers else "d+"
    if board.is_checkmate():
        # a partida acabou: o que a peça ataca ou destapa não descreve o golpe
        return Lance(LETRA[peca], chess.square_name(mv.from_square), chess.square_name(mv.to_square), captura, "#",
                     LETRA[mv.promotion] if mv.promotion else None, (), ())
    depois_outras = _atacadas_por_outras(board, quem, mv.to_square)
    descobertas = []
    for sq in _mais_valiosas(board, depois_outras - antes_outras):
        por = min(a for a in board.attackers(quem, sq) if a != mv.to_square)
        descobertas.append((LETRA[board.piece_type_at(sq)], chess.square_name(sq), chess.square_name(por)))
    novas = {sq for sq in _alvos(board, not quem) if sq in board.attacks(mv.to_square) and sq not in antes_propria}
    ataques = [(LETRA[board.piece_type_at(sq)], chess.square_name(sq)) for sq in _mais_valiosas(board, novas)]
    return Lance(LETRA[peca], chess.square_name(mv.from_square), chess.square_name(mv.to_square), captura, xeque,
                 LETRA[mv.promotion] if mv.promotion else None, tuple(descobertas), tuple(ataques))


def anotar(board: chess.Board, lances_uci: Sequence[str], max_lances: int = MAX_LANCES) -> Assinatura:
    """Descreve os lances de quem soluciona (índices pares) no tabuleiro dado, sem normalizar."""
    board = board.copy()
    if not board.is_valid():
        raise ValueError(f"posição impossível: {board.fen()}")
    quem = board.turn
    rei = chess.square_name(board.king(not quem))
    lances: list[Lance] = []
    for i, uci in enumerate(lances_uci):
        try:
            mv = chess.Move.from_uci(uci)
        except ValueError as exc:
            raise ValueError(f"lance inválido: {uci}") from exc
        if i % 2 == 0:
            if len(lances) >= max_lances:
                break
            lances.append(_anotar_lance(board, mv))
        else:
            if not board.is_legal(mv):
                raise ValueError(f"lance ilegal: {uci} em {board.fen()}")
            board.push(mv)
    return Assinatura(rei, tuple(lances))


def assinar(fen: str, lances_uci: Sequence[str], max_lances: int = MAX_LANCES) -> Assinatura:
    """Assinatura normalizada: quem soluciona vira as brancas (espelho vertical com troca de cores)."""
    try:
        board = chess.Board(fen)
    except ValueError as exc:
        raise ValueError(f"FEN inválida: {fen}") from exc
    if board.turn == chess.BLACK:
        board = board.mirror()
        lances_uci = [_uci_espelho_vertical(u) for u in lances_uci]
    return anotar(board, lances_uci, max_lances)


def _uci_espelho_vertical(uci: str) -> str:
    mv = chess.Move.from_uci(uci)
    return chess.Move(chess.square_mirror(mv.from_square), chess.square_mirror(mv.to_square), mv.promotion).uci()


@dataclass(frozen=True)
class Trecho:
    """Um pedaço da solução, começando no `inicio`-ésimo lance do solucionador (0-based) e
    cobrindo `n` deles (spec golpes trechos §3.5). `posicao` é relativa a TODOS os lances do
    solucionador na solução: "inteira" quando o trecho cobre todos, "inicio" quando começa no
    primeiro, "fim" quando termina no último, senão "meio". A casa do rei em `assinatura` é a de
    quando o trecho começa, não a da posição do puzzle: um trecho que começa depois de o rei se
    mexer mostra a casa nova (é o que faz um irmão "mesmo trecho" ter a mesma geometria local)."""
    inicio: int
    n: int
    posicao: str
    assinatura: Assinatura


def trechos(fen: str, lances_uci: Sequence[str], max_solver: int = 6, tamanhos: tuple[int, ...] = (1, 2, 3)) -> list["Trecho"]:
    """Todo trecho contíguo de `tamanhos` lances do solucionador, começando em cada lance até
    `max_solver` (spec golpes trechos §3.5): a busca de irmãos por trecho compara a âncora
    (sempre `inicio == 0`, prefixos) contra qualquer posição da solução de um candidato — um
    golpe pode estar espalhado a partir do início, do fim ou do meio de uma solução mais longa.
    Normaliza como `assinar` (o solucionador sempre joga de brancas). Levanta ValueError como
    `assinar` (FEN inválida ou lance ilegal)."""
    try:
        board = chess.Board(fen)
    except ValueError as exc:
        raise ValueError(f"FEN inválida: {fen}") from exc
    if board.turn == chess.BLACK:
        board = board.mirror()
        lances_uci = [_uci_espelho_vertical(u) for u in lances_uci]
    n_solver = (len(lances_uci) + 1) // 2
    limite = min(n_solver, max_solver)
    # tabuleiro no início de cada lance do solucionador (`boards[i]`): antes do i-ésimo lance
    # dele, ou seja, depois de i lances dele e i respostas do adversário
    boards = [board.copy()]
    atual = board.copy()
    for j in range(min(len(lances_uci), 2 * limite)):
        mv = chess.Move.from_uci(lances_uci[j])
        if not atual.is_legal(mv):
            raise ValueError(f"lance ilegal: {lances_uci[j]} em {atual.fen()}")
        atual.push(mv)
        if j % 2 == 1:
            boards.append(atual.copy())
    out = []
    for i in range(limite):
        for n in tamanhos:
            if i + n > limite:
                continue
            a = anotar(boards[i], lances_uci[2 * i:], max_lances=n)
            if i == 0 and i + n == n_solver:
                posicao = "inteira"
            elif i == 0:
                posicao = "inicio"
            elif i + n == n_solver:
                posicao = "fim"
            else:
                posicao = "meio"
            out.append(Trecho(inicio=i, n=n, posicao=posicao, assinatura=a))
    return out
