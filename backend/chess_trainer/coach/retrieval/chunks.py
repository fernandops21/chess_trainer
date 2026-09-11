"""Árvore de um capítulo -> trechos indexáveis (spec §6.1).

Um trecho por enunciado e por comentário de nó, com a posição (FEN), o
caminho de lances desde a raiz e o texto indexado com um cabeçalho
"estudo — capítulo — caminho" (ajuda a busca por nome de abertura).
Comentários curtos são juntados ao trecho anterior do mesmo ramo; longos são
partidos em frases. Puro: só recebe a árvore."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import chess

from chess_trainer.core.studies.tree import move_of

MIN_CHARS = 40
MAX_CHARS = 1200
_FRASE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Trecho:
    key: str
    chapter_id: str
    node_id: str | None
    kind: str  # "intro" | "comment"
    text: str
    comment: str
    fen: str
    path_san: str
    ply: int
    content_hash: str


def _partir(texto: str) -> list[str]:
    if len(texto) <= MAX_CHARS:
        return [texto]
    partes: list[str] = []
    atual = ""
    for frase in _FRASE.split(texto):
        if atual and len(atual) + 1 + len(frase) > MAX_CHARS:
            partes.append(atual)
            atual = frase
        else:
            atual = f"{atual} {frase}".strip()
    if atual:
        partes.append(atual)
    return partes


def _chave(chapter_id: str, node_id: str | None, kind: str, parte: int) -> str:
    return hashlib.sha1(f"{chapter_id}|{node_id or ''}|{kind}|{parte}".encode()).hexdigest()[:10]


def trechos_do_capitulo(chapter_id: str, estudo: str, capitulo: str, tree: dict) -> list[Trecho]:
    cabecalho = f"{estudo} — {capitulo}"
    # rascunhos mutáveis: a junção de comentários curtos altera o anterior
    rascunhos: list[dict] = []
    intro = str(tree.get("intro") or "").strip()
    fen0 = str(tree.get("fen") or chess.STARTING_FEN)
    if intro:
        rascunhos.append({"node_id": None, "kind": "intro", "comment": intro, "fen": fen0, "path_san": "", "ply": 0})

    def percorrer(node: dict, board: chess.Board, caminho: list[str], anterior: int | None) -> None:
        for filho in node.get("children") or []:
            if not isinstance(filho, dict):
                continue
            b = board.copy()
            try:
                mv = move_of(b, filho)
            except ValueError:
                continue  # ramo com lance ilegal: fica de fora
            san = b.san(mv)
            numero = b.fullmove_number
            token = f"{numero}.{san}" if b.turn == chess.WHITE else (f"{numero}...{san}" if not caminho else san)
            b.push(mv)
            novo_caminho = caminho + [token]
            comentario = str(filho.get("comment") or "").strip()
            atual = anterior
            if comentario:
                if len(comentario) < MIN_CHARS and anterior is not None:
                    rascunhos[anterior]["comment"] = f"{rascunhos[anterior]['comment']} {comentario}"
                else:
                    rascunhos.append({"node_id": str(filho.get("id") or ""), "kind": "comment", "comment": comentario,
                                      "fen": b.fen(), "path_san": " ".join(novo_caminho), "ply": len(novo_caminho)})
                    atual = len(rascunhos) - 1
            percorrer(filho, b, novo_caminho, atual)

    percorrer(tree.get("root") or {}, chess.Board(fen0), [], None)

    out: list[Trecho] = []
    for r in rascunhos:
        prefixo = f"{cabecalho} — {r['path_san']}" if r["path_san"] else cabecalho
        for i, parte in enumerate(_partir(r["comment"])):
            text = f"{prefixo}: {parte}"
            out.append(Trecho(
                key=_chave(chapter_id, r["node_id"], r["kind"], i), chapter_id=chapter_id, node_id=r["node_id"],
                kind=r["kind"], text=text, comment=parte, fen=r["fen"], path_san=r["path_san"], ply=r["ply"],
                content_hash=hashlib.sha1(text.encode()).hexdigest()[:16],
            ))
    return out
