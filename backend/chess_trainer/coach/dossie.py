"""Dossiê de fatos pré-computados (spec §4.3, §7). A estrutura do `por_que` já fixa
QUAIS análises a explicação pede (ameaças, defesa natural, solução): aqui elas são
calculadas antes da primeira chamada ao modelo e vão na mensagem inicial, para ele
redigir em vez de explorar com ferramentas. Puro: recebe a função de análise e reusa
as mesmas funções das ferramentas, para o modelo ver o formato que já conhece."""
from __future__ import annotations

from typing import Callable

import chess

from chess_trainer.coach.tools import ContextoExercicio, analise_da_posicao, fatos_taticos
from chess_trainer.coach.verify import Analisar, limpar_san

# a posição do exercício (e a do erro) com as três melhores linhas; as derivadas
# (depois da solução, depois da defesa natural) com duas
MULTIPV_PRINCIPAL = 3
MULTIPV_DERIVADA = 2
INDISPONIVEL_EM_XEQUE = "em xeque: não dá para passar a vez"


def _secao(calcular: Callable[[], dict | None]) -> dict | None:
    """Uma seção que falha (engine fora do ar, FEN que não presta) vira `{"erro": ...}`:
    as outras continuam sendo calculadas e o dossiê nunca levanta exceção."""
    try:
        return calcular()
    except Exception as exc:  # noqa: BLE001 - qualquer falha da engine ou do python-chess vira erro da seção
        return {"erro": str(exc)}


def _ameacas(analisar: Analisar, fen: str) -> dict:
    """O que o adversário faria se o lado a mover passasse a vez; em xeque não existe."""
    if chess.Board(fen).is_check():
        return {"indisponivel": INDISPONIVEL_EM_XEQUE}
    return analise_da_posicao(analisar, fen, MULTIPV_PRINCIPAL, True)


def _depois_de(fen: str, san: str) -> str | None:
    """A FEN depois de `san`, ou None quando o lance não é legal na posição."""
    board = chess.Board(fen)
    try:
        board.push(board.parse_san(san))
    except ValueError:
        return None
    return board.fen()


def _apos_solucao(analisar: Analisar, fen: str, san: str) -> dict | None:
    """O que o adversário tem depois do lance-chave; sem análise quando a posição acabou."""
    fen_depois = _depois_de(fen, san)
    if fen_depois is None:
        return None
    saida = {"lance": san, "fen": fen_depois, "fatos": fatos_taticos(fen_depois)}
    if chess.Board(fen_depois).is_game_over():
        saida["terminal"] = True
    else:
        saida["analise"] = analise_da_posicao(analisar, fen_depois, MULTIPV_DERIVADA, False)
    return saida


def _lance_natural(contexto: ContextoExercicio, inicial: dict | None) -> tuple[str, str] | None:
    """O lance que o aluno jogaria em vez da solução, e de onde ele veio: a resposta real
    dele na partida, o lance errado dele (quando o exercício começa na posição do erro)
    ou, sem lance real, a segunda linha da engine."""
    resposta = contexto.minha_resposta
    if resposta and not resposta.get("achou"):
        return str(resposta["san"]), "resposta_do_aluno"
    errado = contexto.lance_errado
    if errado and errado.get("de_quem") == "você" and _depois_de(contexto.fen_inicial, str(errado["san"])) is not None:
        return str(errado["san"]), "lance_errado"
    linhas = (inicial or {}).get("linhas") or []
    solucao = limpar_san(contexto.solucao_san[0]) if contexto.solucao_san else None
    if len(linhas) > 1 and limpar_san(str(linhas[1]["lance"])) != solucao:
        return str(linhas[1]["lance"]), "segunda_linha_da_engine"
    return None


def _defesa_natural(analisar: Analisar, contexto: ContextoExercicio, inicial: dict | None) -> dict | None:
    escolha = _lance_natural(contexto, inicial)
    if escolha is None:
        return None
    san, origem = escolha
    fen_depois = _depois_de(contexto.fen_inicial, san)
    if fen_depois is None:
        return None
    return {"lance": san, "origem": origem, "fen": fen_depois,
            "analise": analise_da_posicao(analisar, fen_depois, MULTIPV_DERIVADA, False),
            "fatos": fatos_taticos(fen_depois)}


def montar_dossie(contexto: ContextoExercicio, analisar: Analisar) -> dict:
    """Tudo o que a estrutura do `por_que` pede, já calculado: a posição do exercício, as
    ameaças do adversário (lance nulo), os fatos táticos, a posição depois da solução, a
    defesa natural do aluno e, quando há, a posição do erro. Uma seção não aplicável é
    omitida; uma que falha vem como `{"erro": ...}`. Nunca levanta exceção."""
    fen = contexto.fen_inicial
    dossie: dict = {
        "inicial": _secao(lambda: analise_da_posicao(analisar, fen, MULTIPV_PRINCIPAL, False)),
        "ameacas_inicial": _secao(lambda: _ameacas(analisar, fen)),
        "fatos_inicial": _secao(lambda: fatos_taticos(fen)),
    }
    if contexto.solucao_san:
        dossie["apos_solucao"] = _secao(lambda: _apos_solucao(analisar, fen, contexto.solucao_san[0]))
    dossie["defesa_natural"] = _secao(lambda: _defesa_natural(analisar, contexto, dossie["inicial"]))
    if contexto.fen_erro and contexto.fen_erro != fen:
        fen_erro = contexto.fen_erro
        dossie["erro"] = _secao(lambda: analise_da_posicao(analisar, fen_erro, MULTIPV_PRINCIPAL, False))
        dossie["ameacas_erro"] = _secao(lambda: _ameacas(analisar, fen_erro))
        dossie["fatos_erro"] = _secao(lambda: fatos_taticos(fen_erro))
    return {chave: secao for chave, secao in dossie.items() if secao is not None}
