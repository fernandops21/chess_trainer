import jsonschema  # se não estiver instalado: `uv add --dev jsonschema`

from chess_trainer.coach.llm import FERRAMENTA_FINAL
from chess_trainer.coach.prompts import ESQUEMA_EXPLICACAO, PROMPT_VERSION, SYSTEM_PROMPT, mensagem_de_correcao, mensagem_inicial


def test_esquema_estrito_valida_uma_resposta_boa_e_recusa_uma_ruim():
    boa = {"texto": "x", "linhas": [{"inicio": "erro", "lances": ["Nf6", "Qxf7#"], "avaliacao_cp": None, "mate_em": 0}],
           "citacoes": [], "padrao": None, "treinar": ["mates com dama e bispo"]}
    jsonschema.validate(boa, ESQUEMA_EXPLICACAO)
    import pytest
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"texto": "x"}, ESQUEMA_EXPLICACAO)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**boa, "linhas": [{"inicio": "meio", "lances": []}]}, ESQUEMA_EXPLICACAO)
    assert ESQUEMA_EXPLICACAO["additionalProperties"] is False


def test_prompt_de_sistema_tem_as_regras_duras():
    assert PROMPT_VERSION == "v1"
    for trecho in ("analisar_posicao", "ponto de vista das brancas", "[c:", "inicial", "erro", FERRAMENTA_FINAL, "português"):
        assert trecho in SYSTEM_PROMPT, trecho


def test_mensagens():
    m = mensagem_inicial("## Exercício\nFEN: x", [{"chunk_id": "ab12", "estudo": "E", "capitulo": "C", "caminho_san": "1.e4", "texto": "Comentário sintético."}])
    assert "## Exercício" in m and "[c:ab12]" in m and "Comentário sintético." in m and "E — C — 1.e4" in m
    vazio = mensagem_inicial("ctx", [])
    assert "nenhum trecho" in vazio.lower()
    c = mensagem_de_correcao({"texto": "antes"}, {"ok": False, "issues": [{"tipo": "lance_ilegal", "gravidade": "erro", "detalhe": "'Qxf8' não é legal", "linha_idx": 0}]})
    assert "lance_ilegal" in c and "Qxf8" in c and "antes" in c
