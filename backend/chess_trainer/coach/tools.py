"""Contexto do exercício e ferramentas do agente (spec §4.2). O contexto é um
dado puro (serve ao pipeline, ao verificador e à avaliação offline); as
ferramentas são funções finas sobre o que o app já tem."""
from __future__ import annotations

import io
import json
from dataclasses import asdict, dataclass, field
from typing import Callable

import chess
import chess.pgn
from sqlalchemy import select
from sqlalchemy.orm import Session

from chess_trainer.coach.llm import Ferramenta
from chess_trainer.coach.verify import Analisar
from chess_trainer.core.models import Position, Puzzle
from chess_trainer.core.tactics.themes import THEME_LABELS, normalize_own_theme

JANELA_PLIES = 6


@dataclass
class ContextoExercicio:
    puzzle_id: str
    tipo: str  # punir | evitar | estudo | lichess
    lado: str  # brancas | pretas
    fen_inicial: str
    fen_erro: str | None
    solucao_san: list[str]
    lance_errado: dict | None
    minha_resposta: dict | None
    partida: dict | None
    tema: str
    categoria: str
    lances_permitidos: set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["lances_permitidos"] = sorted(self.lances_permitidos)
        return d

    def texto(self) -> str:
        linhas = ["## Exercício", f"Tipo: {self.tipo}. O aluno joga de {self.lado}. Tema: {self.tema}. Categoria: {self.categoria}.",
                  f"FEN da posição do exercício (inicial): {self.fen_inicial}",
                  f"Solução do exercício: {' '.join(self.solucao_san) or '(sem lances)'}"]
        if self.fen_erro:
            linhas.append(f"FEN da posição antes do lance errado (erro): {self.fen_erro}")
        if self.lance_errado:
            e = self.lance_errado
            linhas.append(f"Lance errado ({e['de_quem']}, {e.get('nivel') or 'erro'}): {e['san']}; avaliação como o app mostra: "
                          f"{e['aval_antes']} → {e['aval_depois']} (use `analisar_posicao` para números confiáveis).")
        if self.minha_resposta:
            r = self.minha_resposta
            linhas.append(("Na partida o aluno achou a solução: " if r["achou"] else "Na partida o aluno respondeu ") + r["san"]
                          + ("" if r["achou"] else f" ({r['aval_antes']} → {r['aval_depois']}) e deixou passar a solução."))
        if self.partida:
            p = self.partida
            linhas.append(f"Partida: {p['brancas']} x {p['pretas']} ({p['resultado']}, {p['data']}); o aluno era {p['meu_lado']}.")
            linhas.append(f"Lances em volta do erro: {p['lances_em_volta']}")
        return "\n".join(linhas)


def _san_da_solucao(fen: str, moves: list[dict]) -> list[str]:
    board = chess.Board(fen)
    out = []
    for m in moves:
        try:
            mv = chess.Move.from_uci(m["uci"])
            out.append(board.san(mv))
            board.push(mv)
        except (ValueError, KeyError):
            break
    return out


def _lances_em_volta(pgn: str, ply: int) -> str:
    """Janela de ±6 plies em volta do lance de número `ply` (1 = primeiro lance), em SAN numerado."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return ""
    board = game.board()
    tokens: list[tuple[int, bool, str]] = []
    for mv in game.mainline_moves():
        tokens.append((board.fullmove_number, board.turn == chess.WHITE, board.san(mv)))
        board.push(mv)
    ini, fim = max(0, ply - 1 - JANELA_PLIES), min(len(tokens), ply + JANELA_PLIES)
    out = []
    for i, (numero, brancas, san) in enumerate(tokens[ini:fim]):
        if brancas:
            out.append(f"{numero}.{san}")
        elif i == 0:
            out.append(f"{numero}...{san}")  # a janela começa num lance das pretas
        else:
            out.append(san)
    return " ".join(out)


def _tema(theme: str) -> str:
    return THEME_LABELS.get(normalize_own_theme(theme), theme)


def contexto_do_exercicio(db: Session, puzzle: Puzzle) -> ContextoExercicio:
    sol = puzzle.solution_data.get("moves", [])
    lado = "brancas" if puzzle.side_to_move == "white" else "pretas"
    if puzzle.source == "study":
        tipo = "estudo"
    elif puzzle.source == "lichess":
        tipo = "lichess"
    else:
        tipo = "evitar" if puzzle.kind == "avoid" else "punir"
    permitidos: set[str] = set()
    if sol:
        permitidos.add(sol[0]["uci"])
        permitidos.update(sol[0].get("alternatives", []))
    pos = puzzle.position
    lance_errado = minha_resposta = partida = None
    fen_erro = puzzle.fen_before
    if pos is not None:
        fen_erro = pos.fen
        de_quem = "você" if (pos.mistake_by == "me" or (pos.mistake_by is None and tipo == "evitar")) else "adversário"
        lance_errado = {"san": pos.move_played, "uci": pos.move_uci, "de_quem": de_quem, "nivel": pos.mistake_level,
                        "aval_antes": pos.eval_before, "aval_depois": pos.eval_after}
        permitidos.add(pos.move_uci)
        if tipo == "punir":
            seguinte = db.scalar(select(Position).where(Position.game_id == pos.game_id, Position.ply == pos.ply + 1))
            if seguinte is not None:
                achou = bool(sol) and (seguinte.move_uci == sol[0]["uci"] or seguinte.move_uci in sol[0].get("alternatives", []))
                minha_resposta = {"san": seguinte.move_played, "uci": seguinte.move_uci, "achou": achou,
                                  "aval_antes": seguinte.eval_before, "aval_depois": seguinte.eval_after}
                permitidos.add(seguinte.move_uci)
    game = puzzle.game
    if game is not None and pos is not None:
        partida = {"brancas": game.white, "pretas": game.black, "resultado": game.result,
                   "data": game.played_at.date().isoformat(), "meu_lado": "brancas" if game.my_color == "white" else "pretas",
                   "lances_em_volta": _lances_em_volta(game.pgn, pos.ply)}
    elif puzzle.last_move and puzzle.fen_before:
        # táticas e estudos: o "erro" é o último lance do adversário
        b = chess.Board(puzzle.fen_before)
        try:
            mv = chess.Move.from_uci(puzzle.last_move)
            lance_errado = {"san": b.san(mv), "uci": puzzle.last_move, "de_quem": "adversário", "nivel": None, "aval_antes": None, "aval_depois": None}
            permitidos.add(puzzle.last_move)
        except ValueError:
            pass
    return ContextoExercicio(
        puzzle_id=puzzle.id, tipo=tipo, lado=lado, fen_inicial=puzzle.fen_start, fen_erro=fen_erro,
        solucao_san=_san_da_solucao(puzzle.fen_start, sol), lance_errado=lance_errado, minha_resposta=minha_resposta,
        partida=partida, tema=_tema(puzzle.theme), categoria=puzzle.category, lances_permitidos=permitidos,
    )


def _analisar_posicao(analisar: Analisar) -> Callable[[dict], str]:
    def fn(entrada: dict) -> str:
        fen = str(entrada.get("fen", ""))
        board = chess.Board(fen)  # ValueError em FEN inválida: vira erro de ferramenta
        multipv = max(1, min(3, int(entrada.get("multipv", 3))))
        a = analisar(board.fen(), multipv)
        sinal = 1 if board.turn == chess.WHITE else -1
        linhas = [{"lance": l["san"], "avaliacao_brancas_cp": sinal * int(l["score"]), "continuacao": list(l.get("pv_san", []))[:8]}
                  for l in a.get("lines", [])]
        return json.dumps({"fen": board.fen(), "lado_a_mover": "brancas" if board.turn else "pretas",
                           "terminal": a.get("terminal"), "linhas": linhas}, ensure_ascii=False)
    return fn


def ferramentas_do_treinador(contexto: ContextoExercicio, analisar: Analisar,
                             estatisticas: Callable[[int], list[dict]] | None,
                             buscar: Callable[[str, int], list[dict]] | None) -> list[Ferramenta]:
    ferr = [
        Ferramenta("analisar_posicao", "Analisa uma posição com o Stockfish: melhores lances, avaliação (ponto de vista das brancas, centipeões) e continuação.",
                   {"type": "object", "properties": {"fen": {"type": "string"}, "multipv": {"type": "integer", "minimum": 1, "maximum": 3}},
                    "required": ["fen"], "additionalProperties": False}, _analisar_posicao(analisar)),
        Ferramenta("contexto_do_exercicio", "Devolve de novo o contexto completo do exercício (posições, solução, lance errado, partida).",
                   {"type": "object", "properties": {}, "additionalProperties": False},
                   lambda _e: json.dumps(contexto.to_dict(), ensure_ascii=False)),
    ]
    if estatisticas is not None:
        ferr.append(Ferramenta("estatisticas_por_tema", "Acerto do aluno por tema tático nos últimos N dias (padrão 90).",
                               {"type": "object", "properties": {"dias": {"type": "integer", "minimum": 1, "maximum": 3650}}, "additionalProperties": False},
                               lambda e: json.dumps(estatisticas(int(e.get("dias", 90)))[:10], ensure_ascii=False)))
    if buscar is not None:
        ferr.append(Ferramenta("buscar_estudos", "Busca trechos nos estudos e livros que o aluno está lendo. Devolve chunk_id para citar com [c:ID].",
                               {"type": "object", "properties": {"consulta": {"type": "string"}, "k": {"type": "integer", "minimum": 1, "maximum": 10}},
                                "required": ["consulta"], "additionalProperties": False},
                               lambda e: json.dumps(buscar(str(e["consulta"]), int(e.get("k", 5))), ensure_ascii=False)))
    return ferr
