"""Preços dos modelos em dólares por milhão de tokens.

Copiados da página de preços da Anthropic (platform.claude.com/docs/en/about-claude/pricing)
em 2026-09-11. Quando mudarem, muda aqui e a data."""
from dataclasses import dataclass

PRECOS_LIDOS_EM = "2026-09-11"


@dataclass(frozen=True)
class Preco:
    entrada: float
    escrita_cache: float  # cache de 5 minutos: 1,25x a entrada
    leitura_cache: float  # 0,1x a entrada
    saida: float


PRECOS: dict[str, Preco] = {
    "claude-opus-5": Preco(5.0, 6.25, 0.50, 25.0),
    "claude-sonnet-5": Preco(2.0, 2.50, 0.20, 10.0),
}
MODELOS: tuple[str, ...] = tuple(PRECOS)
MODELO_PADRAO = "claude-opus-5"
EFFORTS: tuple[str, ...] = ("low", "medium", "high")


@dataclass(frozen=True)
class Uso:
    """Tokens de uma ou mais chamadas à API, somáveis."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, outro: "Uso") -> "Uso":
        return Uso(
            self.input_tokens + outro.input_tokens,
            self.output_tokens + outro.output_tokens,
            self.cache_read_tokens + outro.cache_read_tokens,
            self.cache_write_tokens + outro.cache_write_tokens,
        )

    def to_dict(self) -> dict:
        return {"input": self.input_tokens, "output": self.output_tokens,
                "cache_read": self.cache_read_tokens, "cache_write": self.cache_write_tokens}


def custo_usd(model: str, uso: Uso) -> float:
    """Custo em dólares; modelo fora da tabela (fakes de teste) custa zero."""
    p = PRECOS.get(model)
    if p is None:
        return 0.0
    total = (uso.input_tokens * p.entrada + uso.cache_write_tokens * p.escrita_cache
             + uso.cache_read_tokens * p.leitura_cache + uso.output_tokens * p.saida)
    return round(total / 1_000_000, 6)
