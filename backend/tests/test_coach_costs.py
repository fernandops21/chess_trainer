from chess_trainer.coach.costs import EFFORTS, MODELOS, Uso, custo_usd


def test_uso_soma_e_serializa():
    total = Uso(100, 10, 50, 5) + Uso(1, 2, 3, 4)
    assert total == Uso(101, 12, 53, 9)
    assert total.to_dict() == {"input": 101, "output": 12, "cache_read": 53, "cache_write": 9}


def test_custo_opus_5_na_tabela_oficial():
    # 1M de entrada + 1M de saída no Opus 5 = 5 + 25 dólares
    assert custo_usd("claude-opus-5", Uso(1_000_000, 1_000_000, 0, 0)) == 30.0
    # leitura de cache é 10% da entrada; escrita 5 min é 125%
    assert custo_usd("claude-opus-5", Uso(0, 0, 1_000_000, 0)) == 0.5
    assert custo_usd("claude-opus-5", Uso(0, 0, 0, 1_000_000)) == 6.25


def test_custo_sonnet_5_e_modelo_desconhecido():
    assert custo_usd("claude-sonnet-5", Uso(1_000_000, 1_000_000, 0, 0)) == 12.0
    assert custo_usd("fake", Uso(1000, 1000, 0, 0)) == 0.0
    assert "claude-opus-5" in MODELOS and "claude-sonnet-5" in MODELOS
    assert EFFORTS == ("low", "medium", "high")
