"""Prompt do treinador e esquema da resposta (spec §4.3, §4.4). Versionado:
`PROMPT_VERSION` vai gravado em cada explicação e no relatório da avaliação."""
from __future__ import annotations

import json

from chess_trainer.coach.llm import FERRAMENTA_FINAL

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = f"""Você é o treinador de xadrez do aluno dentro do app dele. O aluno acabou de fazer um
exercício criado a partir de um erro (dele ou do adversário) numa partida dele, ou de um estudo, e
quer entender o que aconteceu. Escreva em português do Brasil, direto, sem elogio vazio, entre 120 e
250 palavras.

Regras que você não pode quebrar:
1. Só cite lances que vieram do contexto do exercício ou da ferramenta `analisar_posicao`. Nunca
   invente um lance nem uma continuação. Se tiver dúvida sobre uma linha, analise a posição antes.
2. Escreva os lances em notação inglesa (K, Q, R, B, N; ex.: Nf3, Bxf7+, O-O), como o app mostra.
3. Toda sequência de lances do texto tem de aparecer também em `linhas`, declarando de onde parte:
   `inicial` (a posição do exercício) ou `erro` (a posição imediatamente antes do lance errado).
4. Avaliações sempre da engine, sempre do ponto de vista das brancas, em peões no texto (`+1,5`, `-0,4`,
   `mate em 2`) e em `avaliacao_cp` (centipeões inteiros) ou `mate_em` na linha. Os dois descrevem a
   posição no FIM da linha; `mate_em: 0` quer dizer que a linha termina em mate.
5. Cite um estudo só quando o trecho recebido for pertinente, escrevendo o marcador `[c:ID]` no texto
   logo após a frase que se apoia nele, com o ID exato do trecho. Sem trecho pertinente, não fale de estudos.
6. Não invente nome de abertura nem de padrão tático sem apoio no contexto ou nos trechos.
7. Quando terminar, chame a ferramenta `{FERRAMENTA_FINAL}` exatamente uma vez com a resposta completa.

Estrutura sugerida do texto: o que aconteceu na partida; por que o lance perde (a ideia, não só a
linha); o padrão por trás; onde isso aparece nos estudos do aluno, se aparecer; o que treinar.
`treinar` traz de uma a três ações concretas e curtas. `padrao` é um nome curto do padrão tático em
inglês, no estilo dos temas do Lichess (ex.: `hangingPiece`, `fork`, `backRankMate`), ou nulo.
"""

ESQUEMA_EXPLICACAO: dict = {
    "type": "object",
    "properties": {
        "texto": {"type": "string", "description": "A explicação em português, com os lances e os marcadores [c:ID]."},
        "linhas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "inicio": {"type": "string", "enum": ["inicial", "erro"]},
                    "lances": {"type": "array", "items": {"type": "string"}},
                    "avaliacao_cp": {"type": ["integer", "null"], "description": "Avaliação no fim da linha, ponto de vista das brancas."},
                    "mate_em": {"type": ["integer", "null"], "description": "Mate em N no fim da linha; 0 = a linha termina em mate."},
                },
                "required": ["inicio", "lances", "avaliacao_cp", "mate_em"],
                "additionalProperties": False,
            },
        },
        "citacoes": {"type": "array", "items": {"type": "string"}},
        "padrao": {"type": ["string", "null"]},
        "treinar": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["texto", "linhas", "citacoes", "padrao", "treinar"],
    "additionalProperties": False,
}


def mensagem_inicial(contexto_texto: str, trechos: list[dict]) -> str:
    partes = [contexto_texto, "", "## Trechos dos estudos do aluno"]
    if not trechos:
        partes.append("Nenhum trecho recuperado: não cite estudos nesta explicação.")
    for t in trechos:
        cabecalho = " — ".join(x for x in (t.get("estudo", ""), t.get("capitulo", ""), t.get("caminho_san", "")) if x)
        partes.append(f"- [c:{t['chunk_id']}] {cabecalho}: {t.get('texto', '')}")
    partes += ["", "Explique o erro deste exercício para o aluno e entregue a resposta pela ferramenta."]
    return "\n".join(partes)


def mensagem_de_correcao(resposta_anterior: dict, verificacao: dict) -> str:
    problemas = "\n".join(
        f"- [{i.get('gravidade')}] {i.get('tipo')}"
        + (f" (linha {i['linha_idx']})" if i.get("linha_idx") is not None else "")
        + f": {i.get('detalhe', '')}"
        for i in verificacao.get("issues", [])
    )
    return (
        "\n\n## Sua resposta anterior\n```json\n" + json.dumps(resposta_anterior, ensure_ascii=False) + "\n```\n\n"
        "## Relatório de verificação\nO verificador reproduziu suas linhas no tabuleiro e conferiu com a engine. Problemas:\n"
        + problemas
        + "\n\nCorrija a resposta: reanalise as posições com `analisar_posicao` se preciso, remova ou conserte cada "
        "linha apontada, mantenha só citações que existem, e entregue a versão corrigida pela ferramenta."
    )
