"""Livro de aberturas: consulta ao explorador do Lichess (mestres e jogadores).

As respostas ficam em memória por (base, FEN): na análise a mesma posição é
revisitada o tempo todo (voltar um lance, tentar outra linha) e o explorador
tem limite de requisições. O token é pessoal, vem das Configurações e só
aparece no cabeçalho `Authorization` — nunca em log, mensagem de erro ou
resposta da API.
"""

import copy
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

import httpx

EXPLORER_URL = "https://explorer.lichess.ovh/{db}"
USER_AGENT = "chess-trainer/0.1"
TIMEOUT_S = 10.0
CACHE_TTL_S = 24 * 60 * 60.0
CACHE_MAX_ENTRIES = 500
DBS = ("masters", "lichess")


def _cache_fen(fen: str) -> str:
    """Chave do cache: só peças, lado, roques e en passant. O explorador ignora os
    contadores de lances, então posições iguais por ordens diferentes de lances
    compartilham a entrada."""
    return " ".join(fen.split()[:4])

MSG_SEM_TOKEN = "configure o token do Lichess em Configurações"
MSG_TOKEN_RECUSADO = "token do Lichess recusado; gere outro em Configurações"
MSG_LIMITE = "limite do Lichess; tente em instantes"
MSG_INDISPONIVEL = "explorador do Lichess indisponível"


def default_http_factory() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_S, follow_redirects=True)


class OpeningsError(Exception):
    """Falha na consulta, já com o código HTTP que a rota deve devolver."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _params(fen: str, db: str) -> dict[str, Any]:
    """Parâmetros da consulta. Na base de jogadores, ritmos e faixas de rating
    limitam a amostra ao xadrez lento de quem está perto do nível do usuário —
    bullet e blitz de qualquer rating trariam lances que não ensinam nada."""
    if db == "lichess":
        return {
            "variant": "standard",
            "speeds": "rapid,classical",
            "ratings": "1600,1800,2000,2200,2500",
            "fen": fen,
            "topGames": 0,
            "recentGames": 0,
        }
    return {"fen": fen, "topGames": 0}


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize(payload: dict) -> dict:
    """Resposta do explorador no formato que a interface usa.

    As duas bases têm campos diferentes (a de jogadores traz `performance` e
    partidas recentes), então só o que interessa passa adiante, com o total de
    partidas por lance já somado e os lances do mais jogado para o menos."""
    moves = []
    for m in payload.get("moves") or []:
        white, draws, black = _int(m.get("white")), _int(m.get("draws")), _int(m.get("black"))
        moves.append({
            "uci": str(m.get("uci") or ""),
            "san": str(m.get("san") or ""),
            "games": white + draws + black,
            "white": white,
            "draws": draws,
            "black": black,
            "avg_rating": m.get("averageRating"),
        })
    moves.sort(key=lambda m: m["games"], reverse=True)
    white, draws, black = _int(payload.get("white")), _int(payload.get("draws")), _int(payload.get("black"))
    opening = payload.get("opening")
    return {
        "opening": {"eco": str(opening.get("eco") or ""), "name": str(opening.get("name") or "")}
        if isinstance(opening, dict) else None,
        "total": white + draws + black,
        "white": white,
        "draws": draws,
        "black": black,
        "moves": moves,
    }


class OpeningExplorer:
    """Consulta o explorador com cache LRU por (base, FEN) e validade de 24 h."""

    def __init__(
        self,
        http_factory: Callable[[], httpx.Client] | None = None,
        ttl_s: float = CACHE_TTL_S,
        max_entries: int = CACHE_MAX_ENTRIES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http_factory = http_factory or default_http_factory
        self._ttl_s = ttl_s
        self._max_entries = max_entries
        self._clock = clock
        # (base, fen) -> (vence em, livro normalizado); o mais recente no fim
        self._cache: OrderedDict[tuple[str, str], tuple[float, dict]] = OrderedDict()
        # rotas síncronas do FastAPI rodam em threads: o cache é compartilhado
        self._lock = threading.Lock()

    def fetch(self, fen: str, db: str = "masters", token: str = "", http: httpx.Client | None = None) -> dict:
        token = (token or "").strip()
        if db not in DBS:
            raise ValueError(f"base desconhecida: {db}")
        if not token:
            raise OpeningsError(400, MSG_SEM_TOKEN)
        cached = self._get(db, fen)
        if cached is not None:
            return cached
        client = http or self._http_factory()
        try:
            data = self._request(client, fen, db, token)
        finally:
            if http is None:
                client.close()
        self._put(db, fen, data)
        return copy.deepcopy(data)

    def _request(self, client: httpx.Client, fen: str, db: str, token: str) -> dict:
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        try:
            resp = client.get(EXPLORER_URL.format(db=db), params=_params(fen, db), headers=headers)
        except httpx.HTTPError as exc:
            # a mensagem do httpx não é repassada: ela cita a requisição, e nada
            # que veio do token pode escapar para a interface ou para um log
            raise OpeningsError(502, MSG_INDISPONIVEL) from exc
        if resp.status_code in (401, 403):
            raise OpeningsError(400, MSG_TOKEN_RECUSADO)
        if resp.status_code == 429:
            raise OpeningsError(503, MSG_LIMITE)
        if resp.status_code >= 400:
            raise OpeningsError(502, MSG_INDISPONIVEL)
        try:
            payload = resp.json()
        except ValueError as exc:
            raise OpeningsError(502, MSG_INDISPONIVEL) from exc
        if not isinstance(payload, dict):
            raise OpeningsError(502, MSG_INDISPONIVEL)
        return normalize(payload)

    def _get(self, db: str, fen: str) -> dict | None:
        key = (db, _cache_fen(fen))
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            expires_at, data = entry
            if self._clock() > expires_at:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            # cópia: quem chamou pode mexer no dicionário sem estragar o cache
            return copy.deepcopy(data)

    def _put(self, db: str, fen: str, data: dict) -> None:
        with self._lock:
            key = (db, _cache_fen(fen))
            self._cache[key] = (self._clock() + self._ttl_s, data)
            self._cache.move_to_end(key)
            while len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
