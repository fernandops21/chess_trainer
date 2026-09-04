import httpx

BASE_URL = "https://api.chess.com/pub"


class ChessComError(Exception):
    pass


class ChessComClient:
    def __init__(self, user_agent: str, http: httpx.Client | None = None):
        self._http = http or httpx.Client(timeout=30.0)
        self._headers = {"User-Agent": user_agent}

    def _get_json(self, url: str) -> dict:
        try:
            resp = self._http.get(url, headers=self._headers)
        except httpx.HTTPError as exc:
            raise ChessComError(f"erro de rede ao acessar {url}: {exc}") from exc
        if resp.status_code == 404:
            raise ChessComError("usuário ou arquivo não encontrado no chess.com")
        if resp.status_code == 429:
            raise ChessComError("limite de requisições do chess.com atingido; tente de novo em alguns minutos")
        if resp.status_code >= 400:
            raise ChessComError(f"chess.com respondeu HTTP {resp.status_code}")
        return resp.json()

    def list_archives(self, username: str) -> list[str]:
        user = username.strip().lower()
        data = self._get_json(f"{BASE_URL}/player/{user}/games/archives")
        return list(data.get("archives", []))

    def fetch_month(self, archive_url: str) -> list[dict]:
        data = self._get_json(archive_url)
        return list(data.get("games", []))

    def close(self) -> None:
        self._http.close()
