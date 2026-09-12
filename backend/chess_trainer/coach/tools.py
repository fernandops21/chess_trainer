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
from chess_trainer.core.analysis.mistakes import mover_color
from chess_trainer.core.evals import clamp, format_score, is_mate, mate_in
from chess_trainer.core.models import Position, Puzzle
from chess_trainer.core.tactics.themes import THEME_LABELS, normalize_own_theme

JANELA_PLIES = 6
# mesma janela que o índice usa para "mesma abertura" (`retrieval/index.py`)
PLIES_ABERTURA = 6
# teto de cada lista de `fatos_taticos`: o modelo precisa dos fatos, não da lista inteira
LIMITE_FATOS = 12
NOME_DA_PECA = {chess.KING: "rei", chess.QUEEN: "dama", chess.ROOK: "torre",
                chess.BISHOP: "bispo", chess.KNIGHT: "cavalo", chess.PAWN: "peão"}
PECAS_FEMININAS = {chess.QUEEN, chess.ROOK}


def _aval(cp: int | None) -> str:
    """Centipeões (ponto de vista das brancas) no formato que o app mostra; `?` quando não há número."""
    return "?" if cp is None else format_score(cp)


def _pdv_brancas(cp: int | None, ply: int) -> int | None:
    """`Position.eval_*` é do ponto de vista de quem jogou; aqui vira sempre o das brancas."""
    if cp is None:
        return None
    return cp if mover_color(ply) == "white" else -cp


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
    # primeiros plies da partida em SAN numerado, no formato dos caminhos dos trechos
    # (`1.e4 e5 2.Nf3 ...`): é por ele que a busca acha trechos da mesma abertura
    abertura: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["lances_permitidos"] = sorted(self.lances_permitidos)
        return d

    def texto(self) -> str:
        board_inicial = chess.Board(self.fen_inicial)
        lado_a_mover = "brancas" if board_inicial.turn == chess.WHITE else "pretas"
        linhas = ["## Exercício", f"Tipo: {self.tipo}. O aluno joga de {self.lado}. Tema: {self.tema}. Categoria: {self.categoria}.",
                  f"Lance atual: {board_inicial.fullmove_number} ({lado_a_mover} a jogar)",
                  f"FEN da posição do exercício (inicial): {self.fen_inicial}",
                  f"Solução do exercício: {' '.join(self.solucao_san) or '(sem lances)'}"]
        if self.fen_erro:
            linhas.append(f"FEN da posição antes do lance errado (erro): {self.fen_erro}")
        if self.lance_errado:
            e = self.lance_errado
            linhas.append(f"Lance errado ({e['de_quem']}, {e.get('nivel') or 'erro'}): {e['san']}; avaliação "
                          f"(ponto de vista das brancas, como o app mostra): {_aval(e['aval_antes'])} → {_aval(e['aval_depois'])} "
                          "(use `analisar_posicao` para números confiáveis).")
        if self.minha_resposta:
            r = self.minha_resposta
            linhas.append(("Na partida o aluno achou a solução: " if r["achou"] else "Na partida o aluno respondeu ") + r["san"]
                          + ("" if r["achou"] else f" ({_aval(r['aval_antes'])} → {_aval(r['aval_depois'])}) e deixou passar a solução."))
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


def _lances_da_partida(pgn: str) -> list[tuple[int, bool, str]]:
    """Linha principal do PGN como (número do lance, é das brancas, SAN)."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return []
    board = game.board()
    tokens: list[tuple[int, bool, str]] = []
    for mv in game.mainline_moves():
        tokens.append((board.fullmove_number, board.turn == chess.WHITE, board.san(mv)))
        board.push(mv)
    return tokens


def _numerar(tokens: list[tuple[int, bool, str]]) -> str:
    """SAN numerado no mesmo formato dos caminhos dos trechos (`1.e4 e5 2.Nf3 ...`)."""
    out = []
    for i, (numero, brancas, san) in enumerate(tokens):
        if brancas:
            out.append(f"{numero}.{san}")
        elif i == 0:
            out.append(f"{numero}...{san}")  # a sequência começa num lance das pretas
        else:
            out.append(san)
    return " ".join(out)


def _lances_em_volta(pgn: str, ply: int) -> str:
    """Janela de ±6 plies em volta do lance de número `ply` (1 = primeiro lance), em SAN numerado."""
    tokens = _lances_da_partida(pgn)
    ini, fim = max(0, ply - 1 - JANELA_PLIES), min(len(tokens), ply + JANELA_PLIES)
    return _numerar(tokens[ini:fim])


def _tokens_san(pgn: str, n_plies: int) -> str:
    """Os `n_plies` primeiros lances da partida, em SAN numerado desde o início."""
    return _numerar(_lances_da_partida(pgn)[:n_plies])


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
                        "aval_antes": _pdv_brancas(pos.eval_before, pos.ply),
                        "aval_depois": _pdv_brancas(pos.eval_after, pos.ply)}
        permitidos.add(pos.move_uci)
        if tipo == "punir":
            seguinte = db.scalar(select(Position).where(Position.game_id == pos.game_id, Position.ply == pos.ply + 1))
            if seguinte is not None:
                achou = bool(sol) and (seguinte.move_uci == sol[0]["uci"] or seguinte.move_uci in sol[0].get("alternatives", []))
                minha_resposta = {"san": seguinte.move_played, "uci": seguinte.move_uci, "achou": achou,
                                  "aval_antes": _pdv_brancas(seguinte.eval_before, seguinte.ply),
                                  "aval_depois": _pdv_brancas(seguinte.eval_after, seguinte.ply)}
                permitidos.add(seguinte.move_uci)
    game = puzzle.game
    abertura = ""
    if game is not None and pos is not None:
        abertura = _tokens_san(game.pgn, PLIES_ABERTURA)
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
        abertura=abertura,
    )


def _linha_analisada(score_brancas: int, san: str, pv_san: list[str]) -> dict:
    """Uma linha da engine na mesma convenção da resposta final: centipeões OU mate, nunca
    o código interno do mate (±(MATE_SCORE - n)). `mate_em` vem assinado: positivo = as
    brancas dão mate, negativo = as pretas."""
    n = mate_in(score_brancas) if is_mate(score_brancas) else None
    return {
        "lance": san,
        "avaliacao_cp": None if n is not None else clamp(score_brancas),
        "mate_em": None if n is None else (n if score_brancas > 0 else -n),
        "avaliacao": format_score(score_brancas),
        "continuacao": list(pv_san)[:8],
    }


def _analisar_posicao(analisar: Analisar) -> Callable[[dict], str]:
    def fn(entrada: dict) -> str:
        fen = str(entrada.get("fen", ""))
        board = chess.Board(fen)  # ValueError em FEN inválida: vira erro de ferramenta
        multipv = max(1, min(3, int(entrada.get("multipv", 3))))
        apos_passar = bool(entrada.get("apos_passar", False))
        if apos_passar:
            # passar a vez é o lance nulo: as melhores linhas do adversário são as ameaças dele
            if not board.is_valid():
                # xeque do lado errado, rei faltando: o lance nulo só esconderia o problema
                raise ValueError(f"posição impossível: {board.fen()}")
            if board.is_check():
                raise ValueError("em xeque: não dá para passar a vez")
            board.push(chess.Move.null())
        a = analisar(board.fen(), multipv)
        sinal = 1 if board.turn == chess.WHITE else -1
        linhas = [_linha_analisada(sinal * int(l["score"]), l["san"], list(l.get("pv_san", [])))
                  for l in a.get("lines", [])]
        saida = {"fen": board.fen(), "lado_a_mover": "brancas" if board.turn else "pretas",
                 "terminal": a.get("terminal"), "linhas": linhas}
        if apos_passar:
            saida["apos_passar"] = True
            saida["quem_ameaca"] = "brancas" if board.turn else "pretas"
        return json.dumps(saida, ensure_ascii=False)
    return fn


def _nome_da_peca(peca: chess.Piece) -> str:
    """`dama branca`, `cavalo preto`: nome em português com a cor concordando."""
    nome = NOME_DA_PECA[peca.piece_type]
    if peca.piece_type in PECAS_FEMININAS:
        return f"{nome} {'branca' if peca.color == chess.WHITE else 'preta'}"
    return f"{nome} {'branco' if peca.color == chess.WHITE else 'preto'}"


def _casas(casas: chess.SquareSet) -> list[str]:
    return sorted(chess.square_name(c) for c in casas)


def _mates_em_1(board: chess.Board) -> list[str]:
    """Lances legais que dão mate na hora (o SAN já sai com `#`)."""
    out = []
    for mv in board.legal_moves:
        if not board.gives_check(mv):
            continue
        san = board.san(mv)
        board.push(mv)
        mate = board.is_checkmate()
        board.pop()
        if mate:
            out.append(san)
    return out[:LIMITE_FATOS]


def _capturas_de_pecas_indefesas(board: chess.Board) -> list[str]:
    """Capturas em que a casa de destino não tem nenhum defensor do adversário."""
    return [board.san(mv) for mv in board.legal_moves
            if board.is_capture(mv) and not board.attackers(not board.turn, mv.to_square)][:LIMITE_FATOS]


def _captura(board: chess.Board, de: int, casa: int) -> chess.Move:
    """A captura de `de` para `casa`, promovendo a dama quando é peão chegando na oitava."""
    peca = board.piece_at(de)
    promove = peca is not None and peca.piece_type == chess.PAWN and chess.square_rank(casa) in (0, 7)
    return chess.Move(de, casa, promotion=chess.QUEEN if promove else None)


def _atacantes_de_fato(board: chess.Board, casa: int, cor: int) -> list[int]:
    """`attackers` é só geometria: peça cravada não ataca nada. Aqui só entram as que
    podem capturar em `casa` de verdade (`board` tem de ser do lado que captura)."""
    return [de for de in board.attackers(cor, casa) if board.is_legal(_captura(board, de, casa))]


def _sem_recaptura(board: chess.Board, de: int, casa: int) -> bool:
    """Depois da captura em `casa`, ninguém do outro lado pode recapturar legalmente --
    é assim que um defensor cravado deixa de contar como defensor."""
    board.push(_captura(board, de, casa))
    recaptura = any(mv.to_square == casa for mv in board.legal_moves)
    board.pop()
    return not recaptura


def _pecas_atacadas_sem_defesa(board: chess.Board) -> list[dict]:
    """Peças (sem peões nem reis) que podem ser capturadas de graça, dos dois lados: a
    explicação fala tanto da peça que o aluno pode ganhar quanto da que ele deixou
    pendurada. Quem captura a peça de quem tem a vez é o adversário, então essa metade
    é medida no tabuleiro do lance nulo (e não existe quando se está em xeque)."""
    passa = None
    if not board.is_check():
        passa = board.copy()
        passa.push(chess.Move.null())
    out = []
    for casa, peca in sorted(board.piece_map().items()):
        if peca.piece_type in (chess.PAWN, chess.KING):
            continue
        # o tabuleiro em que a captura é lance legal: o atual, ou o do lance nulo
        tabuleiro = board if peca.color != board.turn else passa
        if tabuleiro is None:
            continue
        atacantes = _atacantes_de_fato(tabuleiro, casa, not peca.color)
        if not any(_sem_recaptura(tabuleiro, de, casa) for de in atacantes):
            continue
        out.append({"casa": chess.square_name(casa), "peca": _nome_da_peca(peca),
                    "atacada_por": sorted(chess.square_name(de) for de in atacantes)})
    return out[:LIMITE_FATOS]


def fatos_taticos(fen: str) -> dict:
    """Fatos exatos de uma posição, calculados só com o python-chess (sem engine): é
    daqui que saem as afirmações táticas da explicação (ameaça, mate, casa de fuga do
    rei, peça indefesa), que o modelo antes deduzia sozinho e errava."""
    board = chess.Board(fen)  # ValueError em FEN inválida: vira erro de ferramenta
    if not board.is_valid():
        # FEN cortada, sem rei, com xeque do lado errado: responder fatos aqui seria inventar
        raise ValueError(f"posição impossível: {board.fen()}")
    em_xeque = board.is_check()
    ameacas: dict[str, list[str]] = {"mates_em_1": [], "capturas_de_pecas_indefesas": []}
    if not em_xeque:
        # o que o adversário faria se fosse a vez dele: lance nulo (ilegal em xeque)
        passa = board.copy()
        passa.push(chess.Move.null())
        ameacas = {"mates_em_1": _mates_em_1(passa), "capturas_de_pecas_indefesas": _capturas_de_pecas_indefesas(passa)}
    return {
        "fen": board.fen(),
        "lado_a_mover": "brancas" if board.turn == chess.WHITE else "pretas",
        "em_xeque": em_xeque,
        "lances_do_rei": [board.san(mv) for mv in board.legal_moves
                          if board.piece_type_at(mv.from_square) == chess.KING][:LIMITE_FATOS],
        "xeques": [board.san(mv) for mv in board.legal_moves if board.gives_check(mv)][:LIMITE_FATOS],
        "mates_em_1": _mates_em_1(board),
        "capturas_de_pecas_indefesas": _capturas_de_pecas_indefesas(board),
        "pecas_atacadas_sem_defesa": _pecas_atacadas_sem_defesa(board),
        "ameacas_do_adversario": ameacas,
    }


def ferramentas_do_treinador(contexto: ContextoExercicio, analisar: Analisar,
                             estatisticas: Callable[[int], list[dict]] | None,
                             buscar: Callable[[str, int], list[dict]] | None) -> list[Ferramenta]:
    ferr = [
        Ferramenta("analisar_posicao",
                   "Analisa uma posição com o Stockfish. Cada linha traz `lance`, `avaliacao_cp` (centipeões "
                   "inteiros, ponto de vista das brancas) ou `mate_em` (positivo = as brancas dão mate, negativo "
                   "= as pretas; o outro campo vem nulo), `avaliacao` (a mesma coisa como o app mostra: `+1.50`, "
                   "`#1`) e `continuacao` (a linha em SAN). Com `apos_passar` verdadeiro, analisa como se o "
                   "lado a mover passasse a vez: as linhas devolvidas são as AMEAÇAS do adversário (o que ele "
                   "faria se você jogasse um lance calmo). Use na posição do exercício e na posição do erro "
                   "antes de explicar 'por que'.",
                   {"type": "object", "properties": {"fen": {"type": "string"}, "multipv": {"type": "integer", "minimum": 1, "maximum": 3},
                                                     "apos_passar": {"type": "boolean"}},
                    "required": ["fen"], "additionalProperties": False}, _analisar_posicao(analisar)),
        Ferramenta("fatos_taticos",
                   "Fatos exatos de uma posição, calculados sem engine: lances do rei, xeques, mates em 1, "
                   "capturas de peças indefesas, peças atacadas sem defesa (dos dois lados; a cor vem no campo "
                   "`peca`), e o que o adversário faria se fosse "
                   "a vez dele (ameaças). Use antes de afirmar 'a ameaça é X', 'o rei não tem casa de fuga' ou "
                   "'a única defesa é Y'.",
                   {"type": "object", "properties": {"fen": {"type": "string"}},
                    "required": ["fen"], "additionalProperties": False},
                   lambda e: json.dumps(fatos_taticos(str(e.get("fen", ""))), ensure_ascii=False)),
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
