# Chess Trainer — Treinador com IA, fase 1: explicar o erro

Data: 2026-09-11
Status: aprovado em conversa (arquitetura, avaliação, observabilidade, Docker); spec para revisão do usuário antes do plano.
Depende de: tudo o que está na `main` (commit 05f7fa8).
Próximo: plano de implementação; fases 2 a 4 em specs separados (ver §14).

## 1. Motivação

O app já transforma os erros do usuário em exercícios e mostra a refutação da
engine, mas não explica *por que* o lance foi ruim nem liga o erro ao que o
usuário está estudando. Quem treina sozinho fica com a engine de um lado
(números sem explicação) e os livros do outro (explicações sem ligação com as
próprias partidas). A fase 1 junta as duas pontas: um botão "Explicar" na tela
de resultado do exercício chama um treinador que escreve, em português, o que
aconteceu, por que o lance perde, qual é o padrão, onde ele aparece nos estudos
que o usuário está lendo, e o que treinar.

O treinador é um agente com LLM munido de ferramentas (engine, contexto da
partida, estatísticas do usuário, busca nos estudos). Ele não substitui o
material do usuário; ele o aproveita: cada explicação cita o capítulo e o lance
onde o padrão aparece, e o link abre o capítulo no modo livro.

Propriedade central do domínio, que define o produto: toda afirmação sobre uma
posição de xadrez é verificável pela engine. Um LLM sozinho alucina lances; por
isso o texto só chega ao usuário depois de um verificador reproduzir cada linha
citada no tabuleiro e conferir avaliações e citações. O que não bate é
corrigido ou mostrado com aviso, nunca escondido. A qualidade do treinador é
medida de forma contínua (avaliação offline contra um baseline, relatório
publicado), porque um treinador que erra lance faz o aluno regredir.

Esta fase é o primeiro passo de um treinador pessoal: quando ele enxerga os
erros, as estatísticas e o material do usuário, o passo seguinte é montar o
plano de estudo e a sequência de exercícios sob medida (fase 4, §14).

## 2. Decisões já tomadas

- Superfície: explicar o erro na tela de resultado. Chat livre e relatório
  semanal ficam fora (§15).
- Provedor: API da Anthropic, SDK oficial em Python (`anthropic` 1.x), atrás
  de uma interface própria. Bedrock fica previsto na interface, sem
  implementação nesta fase. Chave criada pelo usuário no Console, com teto de
  gasto configurado lá.
- Modelo padrão `claude-opus-5`; `claude-sonnet-5` como alternativa nas
  Configurações. A avaliação (§8) decide se o Sonnet basta. Thinking adaptativo,
  `effort` configurável (padrão `high`).
- Agente com o loop de ferramentas do próprio SDK e o fluxo (contexto,
  recuperação, geração, verificação, correção) escrito em Python como máquina
  de estados pequena. Sem LangChain/LangGraph.
- Observabilidade com LangFuse rodando localmente via Docker Compose (Docker
  Desktop já instalado, WSL 2). LangFuse Cloud é plano B sem mudança de código.
- Custo: uso pontual (uma explicação por exercício); estimativa de 2 a 10
  centavos de dólar por explicação conforme o modelo.

## 3. Privacidade e conteúdo de terceiros

- Cada explicação envia à API a posição, o contexto do exercício e os trechos
  recuperados dos estudos. A Anthropic não treina com dados da API e retém por
  30 dias. O usuário aceitou isso para o uso pessoal.
- Regra de produto mantida: o app não distribui conteúdo de terceiros;
  fixtures de teste e capturas de tela usam só lances e texto sintético; o
  índice de embeddings fica no SQLite local; LangFuse local guarda os traces na
  máquina do usuário.
- A chave da API segue o padrão do token do Lichess: digitada em
  Configurações, guardada na tabela `settings`, nunca devolvida pela API
  (`anthropic_api_key_set: bool`).

## 4. Pacote `chess_trainer/coach/`

Tudo novo fica em `backend/chess_trainer/coach/`. Pontos de contato com o
código existente: rota nova (§9), campos novos em `AppSettings`, gancho no
salvar capítulo (§6) e um botão e um cartão no frontend (§10).

```
coach/
  llm.py          interface LlmClient + AnthropicClient (SDK, loop de ferramentas)
  tools.py        as quatro ferramentas do agente
  prompts.py      system prompt e formato da resposta
  retrieval/
    chunks.py     árvore do capítulo -> trechos
    embeddings.py fastembed (ONNX, CPU), modelo multilíngue
    store.py      tabelas coach_chunks + vetor (sqlite-vec; fallback numpy)
    index.py      indexar capítulo / recriar índice
  verify.py       verificador de lances, avaliações e citações
  explain.py      pipeline: contexto -> agente -> verificar -> corrigir -> gravar
  costs.py        tabela de preços por modelo e cálculo do custo
  observability.py LangFuse (decoradores); no-op sem chaves
```

### 4.1 Cliente LLM

- `LlmClient` (Protocol): `run_agent(system, user, tools, output_schema,
  effort) -> AgentResult` com `text`, `structured`, `usage` (entrada, saída,
  leitura e escrita de cache), `tool_calls` (lista para o trace) e
  `stop_reason`.
- `AnthropicClient`: `anthropic.Anthropic(api_key=...)`; usa o tool runner do
  SDK para o loop; resposta final com saída estruturada (`output_config.format`)
  no esquema de §4.4. Prompt caching: `cache_control` no system prompt e nas
  definições de ferramentas (estáveis); o contexto do exercício vai na mensagem
  do usuário, depois do último ponto de cache. Thinking adaptativo; `effort` da
  configuração. `max_tokens` 16 000 na resposta final (texto, linhas e citações
  mais o raciocínio adaptativo saem do mesmo orçamento). Trata `stop_reason`
  `refusal` e `max_tokens` sem entrega como erro legível. Erros do SDK mapeados
  por classe (§11).
- `FakeLlm` (em `tests/fakes.py`): roteiro de chamadas de ferramenta e resposta
  final fixa; usado em todos os testes sem rede.
- Segundo modelo, mais barato, para a checagem de afirmações (§5, regra 8):
  `MODELO_CHECAGEM` em `costs.py` (Sonnet), fixo, criado com a mesma chave ao lado
  do cliente principal na rota e na avaliação offline. Lê a prosa e devolve, pela
  mesma ferramenta final e com esquema estrito, cada afirmação sobre o tabuleiro
  como dado estruturado; sem ferramentas, esforço baixo, teto curto de tokens.

### 4.2 Ferramentas do agente

Todas finas, em cima do que existe; recebem `db` e `app.state` por fechamento.

| Ferramenta | Entrada | Saída | Implementação |
| --- | --- | --- | --- |
| `analisar_posicao` | `fen`, `multipv` (1–3), `apos_passar` (padrão falso) | linhas com `lance`, `avaliacao_cp` **ou** `mate_em` (assinado: positivo = as brancas dão mate), `avaliacao` formatada, `continuacao` em SAN, `material_fim` (saldo de material no fim da linha, brancas menos pretas) e `ganho_material` (em português, o que muda de material na linha, do ponto de vista de quem move primeiro nela: `brancas ganham a dama pela torre (+4)`, `troca igual`, `nada`; `material em disputa` quando a linha para logo depois de uma captura que o outro lado ainda pode responder, e o texto neutro `ganham material (+N)` quando há promoção) — na mesma convenção de §4.4, nunca o código interno do mate. Com `apos_passar`, analisa a posição do lance nulo (o lado a mover passa a vez): as linhas são as **ameaças** do adversário e a saída traz `apos_passar` e `quem_ameaca`; em xeque ou em posição impossível, erro de ferramenta | `InteractiveAnalyzer.analyse` (cache e engine já existentes) |
| `fatos_taticos` | `fen` | fatos exatos da posição, sem engine: `lances_do_rei`, `xeques`, `mates_em_1`, `capturas_de_pecas_indefesas`, `pecas_atacadas_sem_defesa` (dos dois lados), `ameacas_do_adversario` (o que ele faria se fosse a vez dele, pelo lance nulo) e `apoios` (para cada mate e captura listados, dos dois lados, quem apoia a casa de chegada — `apoiado_por`, peças do lado que move, medidas depois do lance, raio X inclusive — e quem a defende — `defendido_por`, só quem pode recapturar de verdade —, como `Nf5`, `Pe5`: é daí que sai qualquer "apoiada por", "defendida por", "atacada por" da explicação); atacante e defensor conferidos por lance legal (peça cravada não ataca nem defende) e FEN impossível recusada; cada lista com no máximo 12 itens | python-chess puro |
| `contexto_do_exercicio` | nenhuma (fixo por chamada) | puzzle, erro (`mistake`), lances da partida ±6 plies em SAN, `abertura` (os 6 primeiros plies, que a busca usa para "mesma abertura"), lance real do usuário, solução, avaliações antes/depois | `PuzzleOut` + `Position` + `Game.pgn` |
| `estatisticas_por_tema` | `dias` (padrão 90) | linhas de `theme_stats` | `core/stats.theme_stats` |
| `buscar_estudos` | `consulta`, `k` (padrão 5) | trechos `{chunk_id, estudo, capitulo, caminho_san, texto, url}` | §6 |

O contexto do exercício também vai *inteiro* na mensagem inicial (é pequeno);
a ferramenta existe para o agente pedir de novo campos específicos e para a
variante "só prompt" da avaliação ser comparável.

### 4.3 Prompt

System prompt em português, fixo e versionado em `prompts.py`
(`PROMPT_VERSION`), gravado em cada explicação. Conteúdo, em linhas gerais:

- papel: treinador de xadrez explicando para o aluno o erro dele naquele
  exercício; tom direto, sem elogio vazio; 120 a 200 palavras somando os dois
  blocos de prosa (`na_partida` e `por_que`).
- dossiê (prompt v8): a mensagem inicial traz, entre o contexto e os trechos,
  um dossiê de fatos já calculados pela engine e pelo python-chess
  (`dossie.py`), no mesmo formato que as ferramentas devolvem, para o modelo
  redigir em vez de explorar. Seções: `inicial` (a posição do exercício, 3
  melhores linhas); `ameacas_inicial` (a análise com `apos_passar`: o que o
  adversário faria se o aluno passasse a vez; em xeque vem `indisponivel`);
  `fatos_inicial` (os fatos táticos da posição); `apos_solucao` (a posição
  depois do lance-chave, com os fatos e a análise dela, ou `terminal` quando a
  partida acabou ali); `defesa_natural` (o lance que o aluno jogaria em vez da
  solução — a resposta real dele na partida, o lance errado dele quando o
  exercício começa na posição do erro, ou a segunda linha da engine —, com a
  `origem`, a análise e os fatos da posição depois dele; omitida quando não há
  lance a comentar); e, quando há posição do erro diferente da inicial, `erro`,
  `ameacas_erro` e `fatos_erro`. Uma seção que não pôde ser calculada vem como
  `erro` e o modelo não pode inventar o que ela diria. As ferramentas
  `analisar_posicao` / `fatos_taticos` ficam só para uma posição que o dossiê
  não cobre (mais adiante numa linha); nunca repetir uma análise que já está
  nele. No caso comum a explicação sai em uma chamada à API.
- estrutura fixa do `por_que`, nesta ordem: (1) as ameaças do adversário (de
  `ameacas_inicial`), nomeando o mate *e* qualquer outra linha que ganhe
  material (`ganho_material`); (2) a defesa natural e por que ela falha — o
  lance de `defesa_natural`: a primeira linha da análise dela é o que o
  adversário faz na posição depois dele, seguida até onde o material muda (e,
  se essa defesa também for boa, a menos de 100 centipeões em módulo e mate só
  contra mate, dizer que ela resolve); sem `defesa_natural`, vai direto à
  solução; (3) a solução: a primeira linha de `inicial`, e `apos_solucao` diz o
  que o adversário tem depois do lance-chave. Em xeque, onde não dá para passar
  a vez, (1) começa pela ameaça que já está no tabuleiro.
- regras duras: toda afirmação tática (a ameaça, o mate, o xeque, a casa de
  fuga do rei, a peça indefesa) vem dos fatos táticos naquela posição (os do
  dossiê, ou `fatos_taticos` numa posição que ele não cobre) ou de uma linha de
  análise, nunca da dedução do modelo, e lance escrito com
  `+` ou `#` só vale dentro de uma linha declarada que chegue à posição em que ele
  é legal; quem apoia, defende ou ataca uma casa ("a dama apoiada pelo cavalo de
  f5") só sai do campo `apoios` dos fatos táticos ou de `atacada_por` em
  `pecas_atacadas_sem_defesa`, nunca da dedução do modelo; nomear *todas* as
  ameaças relevantes do adversário em `ameacas_inicial` (e `ameacas_erro`), não
  só a maior; só citar lances que vieram do dossiê, de
  `analisar_posicao` ou do contexto; toda linha começa da posição inicial do
  exercício, da posição do erro ou de um dos lances nulos (`ameaca`, `ameaca_erro`),
  declarada;
  avaliações sempre da engine, em peões (`+1,5`) ou `M3`; citar estudos só quando
  o trecho recuperado for pertinente, pelo `chunk_id`; nunca inventar nome de
  abertura ou de padrão sem apoio.
- resposta em blocos, lida ao lado do tabuleiro: sem repetir o FEN, sem lista
  dentro da prosa.
- lances numerados na prosa (`na_partida`/`por_que`), como numa anotação
  (`32...Qh3 33.Rh8+ Kxh8`): é pelo número que o segmentador do frontend acha a
  posição certa quando a explicação cita várias linhas; em `linhas[].lances`
  continua só o SAN, sem número.

### 4.4 Formato da resposta (saída estruturada)

```json
{
  "na_partida": "…1 ou 2 frases: o lance errado e o que o aluno jogou…",
  "por_que": "…2 a 4 frases com a ideia e a linha, em SAN, com marcadores [c:ID]…",
  "linhas": [
    {"inicio": "inicial" | "erro" | "ameaca" | "ameaca_erro", "lances": ["Cf3", "Cc6", "…"], "avaliacao_cp": 150 | null,
     "mate_em": null | 3 | -2 | 0}
  ],
  "citacoes": ["ID", "…"],
  "padrao": "bateria de dama e torre contra f1" | null,
  "treinar": ["…de 1 a 3 ações curtas, no imperativo…"]
}
```

Todos obrigatórios: `na_partida`, `por_que` (texto), `padrao` (texto ou nulo) e
`treinar` (lista de 1 a 3). `padrao` é um rótulo curto em português, de 2 a 5
palavras. A prosa que o verificador, a avaliação e
o juiz leem é derivada: `na_partida` + `por_que`, e é ela que vai em `text` no
banco (a resposta inteira fica em `structured_json`).

`mate_em` vem com sinal: positivo = as brancas dão mate, negativo = as pretas;
`0` quer dizer que a linha termina em mate, seja de quem for. `avaliacao_cp` e
`mate_em` são exclusivos (um deles é `null`) e a ferramenta `analisar_posicao`
(§4.2) devolve os dois na mesma convenção.

`inicio = "inicial"` significa `puzzle.fen_start`; `"erro"` significa a
posição antes do lance errado (`fen_before` do puzzle ou a posição do erro na
partida, conforme o tipo); `"ameaca"` e `"ameaca_erro"` significam a posição
inicial do exercício ou a posição do erro com o lado a mover passando a vez
(lance nulo), de onde parte a ameaça do adversário — o primeiro lance da linha é
dele; `"ameaca_erro"` num exercício sem posição do erro é `lance_ilegal`. Toda sequência de lances que
aparecer na prosa deve estar em `linhas`.

## 5. Verificador (`verify.py`)

Entrada: resposta estruturada, puzzle, trechos recuperados, acesso à engine.
Saída: `Verificacao {ok: bool, issues: list[Issue]}` com `Issue {tipo,
gravidade ("erro" | "aviso"), detalhe, linha_idx | None}`.

Regras:

1. **Legalidade**: cada linha é reproduzida com python-chess a partir da
   posição declarada — numa linha de ameaça, a posição inicial (`ameaca`) ou a do
   erro (`ameaca_erro`) com o lance nulo aplicado; lance ilegal ou SAN não reconhecido → `erro` `lance_ilegal` na
   linha, e a linha para ali. Linha de ameaça com o lado a mover em xeque também
   é `lance_ilegal`: não existe passar a vez em xeque; e `ameaca_erro` sem posição
   do erro também.
2. **Aderência à engine**: para cada linha, a posição de partida é analisada
   com `multipv=3`; o primeiro lance da linha deve ser um dos três primeiros da
   engine, *ou* ser o lance errado do usuário/adversário (quando a linha mostra
   a refutação), *ou* ser um lance da solução do puzzle. Fora disso → `aviso`
   `lance_fora_das_principais`. Numa linha de ameaça a análise é a da posição do
   lance nulo e os lances do exercício não valem como desculpa: o primeiro lance
   é do adversário. Lances seguintes da linha não são cobrados
   individualmente (a engine já validou o início, e linhas longas são
   ilustrativas).
3. **Avaliação**: se `avaliacao_cp` ou `mate_em` vier, compara com a engine na
   posição final da linha (do ponto de vista das brancas). Diferença > 100 cp,
   mate ausente, número de lances diferente ou `mate_em` com o sinal do lado
   errado (positivo = as brancas dão mate; `0` serve para os dois lados) → `erro`
   `avaliacao_errada`. Se a engine dá mate e o texto diz avaliação numérica, `aviso`.
4. **Lances soltos, mates e xeques do texto**: SAN encontrado no `texto` (mesma
   expressão regular do `moveText` do frontend, portada) que não aparece em nenhuma
   linha → `aviso` `lance_sem_linha`; token que é só nome de casa (`h1`, `g3`) conta
   como lance apenas quando é um lance de peão legal numa das posições do exercício.
   Os lances do texto também são conferidos contra as posições alcançáveis (as duas do
   exercício, as dos lances nulos das duas — de onde saem as ameaças — e cada posição
   depois de um prefixo legal de cada linha, inclusive as de ameaça): lance escrito
   com `#` que não é mate em nenhuma delas → `erro` `mate_falso`; lance escrito com
   `+` que não dá xeque em nenhuma delas → `aviso` `xeque_falso`. Issues idênticas
   (mesmo tipo e mesmo detalhe) entram uma vez só. Lance numerado na prosa
   (`19.Qc5`, `32...Qh3`) que está numa linha declarada mas não naquela altura
   (mesmo número, mesmo lado) → `aviso` `lance_fora_de_linha`: a prosa pode pular
   lances, a linha não, e é pela linha que o cartão acha a posição do lance. Lance
   que nenhuma linha traz já saiu como `lance_sem_linha` e não vira os dois avisos.
5. **Citações**: cada `[c:ID]` do texto e cada item de `citacoes` deve ser um
   `chunk_id` entre os trechos recuperados *nesta* execução → senão `erro`
   `citacao_inexistente`. Texto que menciona "no estudo" sem citação → `aviso`.
6. **Tamanho**: `texto` fora de 60 a 400 palavras → `aviso`.
7. **Peças e relações**: sobre as mesmas posições alcançáveis da regra 4, com duas
   conferências no `texto`. (a) Existência: cada "peça de casa" escrita ("o bispo
   de f4", "a torre em d8"; dama, torre, bispo, cavalo, peão, rei; `de/do/da/em/no/na`)
   tem de ter uma peça daquele tipo, de qualquer cor, naquela casa em pelo menos
   uma das posições → senão `erro` `peca_falsa` ("não há bispo em f6 em nenhuma
   posição da explicação"). (b) Relação: em cada "apoiada / defendida / protegida /
   coberta / atacada / controlada pela peça de casa", o alvo é resolvido dentro da
   mesma frase (frases separadas por `.!?:;` seguido de espaço, para o ponto de
   `2.Qxg7#` não cortar) pela última referência antes da expressão: a casa de chegada
   do último lance escrito (roque não conta) ou a casa da última "peça de casa" (o
   sujeito: "a dama de d4 está atacada pelo cavalo de f5" → d4), o que vier por
   último; sem alvo, nada é conferido. Tem de existir uma posição alcançável em que
   a peça nomeada está na casa dita E o alvo está no alcance dela (`board.attacks`:
   geometria pura, com as casas de captura do peão) → senão `erro` `peca_falsa`
   ("o bispo de f4 não ataca g7 em nenhuma posição da explicação"). O caso real: um
   mate certo "com a dama apoiada pelo bispo de f4" em que quem apoiava g7 era o
   cavalo de f5. Issues idênticas entram uma vez só.
8. **Checagem de afirmações** (`afirmacoes.py`, roda no pipeline depois do
   verificador, quando há modelo de checagem): a regra 7 só entende a voz passiva
   ("atacada pela dama de g4"); a prosa afirma coisas em qualquer forma de frase
   ("o cavalo de f5 e a dama de g4 atacam d4 mais vezes do que as pretas
   defendem" — falso: só o cavalo ataca d4, e as pretas defendem duas vezes). Um
   segundo modelo lista toda afirmação verificável do texto como dado estruturado,
   sem julgar: `ataca` (a peça da casa X ataca/apoia/defende/cobre/controla a casa
   Y), `mais_atacantes` (um lado ataca a casa mais vezes do que o outro defende),
   `indefesa`, `cravada`, `unico_lance`, `unica_casa_do_rei`, `garfo` (a peça ataca
   todas as casas listadas), `xeque`, `mate`, `peca_em_casa` (a existência) e
   `outro` (o que não cabe: o extrator lista, a conferência ignora). Cada item traz
   o trecho exato da prosa. O python-chess confere cada uma nas mesmas posições
   alcançáveis das regras 4 e 7, com a mesma semântica permissiva: a afirmação vale
   se é verdade em pelo menos uma delas. Falsa em todas → `erro` `afirmacao_falsa`,
   com o trecho e um motivo concreto calculado na posição inicial ("«a dama de g4
   ataca d4»: g4 não ataca d4 (quem ataca d4: f5)"; "as brancas atacam d4 1 vez e
   as pretas defendem 2"; "Kh1 não é o único lance do rei: também Kf1"). Campo
   malformado (casa inválida, dado faltando) é ignorado em silêncio; issues
   idênticas entram uma vez só. A mensagem de correção diz o que fazer com ela:
   reescrever a frase com o que os fatos dizem ou tirar a afirmação.

`ok` é verdadeiro sem nenhum `erro`. Avisos não bloqueiam, mas aparecem no
cartão. O verificador é puro (recebe uma função `analisar(fen, multipv)`), o
que permite testá-lo com engine falsa e reusá-lo na avaliação offline.

## 6. RAG sobre os estudos

### 6.1 Trechos

`chunks.py` percorre `chapter_tree(chapter)`:

- um trecho `intro` por capítulo com `intro_comment` não vazio;
- um trecho `comment` por nó com comentário não vazio, com `fen` do nó,
  `caminho_san` (lances desde a raiz, ex.: `1.e4 e5 2.Cf3`), `ply`, `node_id`.
- comentários curtos (< 40 caracteres) são juntados ao trecho anterior do mesmo
  ramo; trechos longos (> 1200 caracteres) são partidos em frases.
- texto indexado = `"{estudo} — {capítulo} — {caminho_san}: {comentário}"`
  (o cabeçalho ajuda a busca por abertura/nome).
- `content_hash` (sha1 do texto) evita reembutir o que não mudou.

### 6.2 Embeddings

`fastembed` (ONNX, CPU, sem PyTorch no backend) com um modelo multilíngue da
lista suportada pela biblioteca, escolhido na implementação (primeira opção
`paraphrase-multilingual-MiniLM-L12-v2`, ~250 MB quantizado, 384 dimensões).
O download do modelo acontece uma vez, no primeiro `recriar índice`, **com
aviso prévio ao usuário** (regra de trabalho: perguntar antes de baixar). O
modelo e a dimensão ficam gravados na tabela para invalidar o índice se mudar.

### 6.3 Armazenamento e busca

- `coach_chunks(id, chapter_id, node_id | null, kind, text, fen, path_san,
  ply, content_hash, model, dim, embedded_at)` no mesmo SQLite.
- Vetores em `coach_chunks_vec` (tabela virtual `vec0` do `sqlite-vec` 0.1.9,
  wheel `win_amd64` disponível), `chunk_id` como chave.
- `store.py` expõe `upsert(chunks, vectors)`, `delete_chapter(chapter_id)`,
  `search(vector, k) -> [(chunk_id, distancia)]`. Se a extensão não carregar
  (Python sem `enable_load_extension`), o mesmo módulo cai num índice em
  memória com numpy (cosseno por força bruta; para alguns milhares de trechos é
  instantâneo) e registra um aviso em `GET /api/coach/status`. A interface não
  muda.
- Busca híbrida simples: os `k` vizinhos por cosseno mais até 3 trechos cujo
  `path_san` compartilha os primeiros 6 plies com a partida do exercício
  (mesma abertura), sem duplicar.

### 6.4 Atualização do índice

- Ao salvar um capítulo (`studies/service.py`), `index.index_chapter(chapter)`
  roda em linha (um capítulo são poucas dezenas de trechos; < 1 s em CPU).
- Ao importar estudo ou apagar capítulo, idem por capítulo.
- `POST /api/coach/reindex` recria tudo como tarefa do `jobs` existente
  (nome `coach_reindex`), para o primeiro uso e para troca de modelo.
- `GET /api/coach/status` informa `index_chunks`, `index_model`,
  `index_stale` (capítulos com `updated_at` posterior ao último índice).

## 7. Pipeline de explicação (`explain.py`)

```
explicar(puzzle_id, review_id | None):
  1. contexto  = montar_contexto(puzzle)            # dict de §4.2, também vira texto
  2. trechos   = buscar_estudos(consulta derivada: tema + caminho SAN + trecho da partida)
  2b. dossie   = montar_dossie(contexto, analisar)   # as análises que o "por que" pede, prontas (§4.3)
  3. resultado = llm.run_agent(system, user(contexto, dossie, trechos), tools, schema, effort)
  4. verif     = verificar(resultado.structured, puzzle, trechos, analisar)
  4b. afirmacoes = extrair_afirmacoes(llm_checagem, texto)    # o segundo modelo lista (§5, regra 8)
      verif.issues += conferir_afirmacoes(afirmacoes, posicoes alcançáveis da resposta)
  5. se not verif.ok:
       resultado2 = llm.run_agent(..., user + "Relatório de verificação: …corrija…")
       verif2 = verificar(resultado2…) + a mesma checagem de afirmações (4b)
       usa (resultado2, verif2) se verif2 tiver menos erros; marca repaired=True
  6. grava CoachExplanation (§7.1); devolve
```

- Passo 4b (checagem de afirmações) roda depois de cada verificação, a primeira e
  a da correção, quando o pipeline recebe o modelo de checagem (`llm_checagem`);
  sem ele, nada muda. As posições em que as afirmações são conferidas são as
  mesmas que o verificador usa nas regras 4 e 7. O tempo dela é `checagem_ms` em
  `tempos`, e `afirmacoes` conta as afirmações extraídas; o span é `checagem`.

- Passo 2 (recuperação prévia) existe para que a variante "agente + RAG" tenha
  sempre algo citável e para o custo ficar previsível; o agente ainda pode
  chamar `buscar_estudos` com outra consulta.
- Passo 2b (dossiê) roda antes da primeira chamada ao modelo, nas três variantes
  (a variante "só prompt" passa a ter as análises sem ferramenta nenhuma): até
  seis análises da engine (posição inicial e ameaças com 3 linhas; depois da
  solução e depois da defesa natural com 2; posição do erro e ameaças dela com 3)
  mais os fatos táticos de cada posição. Nunca aborta a explicação: uma seção que
  falha vem como `erro` e as outras seguem. O tempo dele é `dossie_ms` em
  `tempos`, e a linha de tempos do log o traz logo depois do total.
- Custo: `costs.py` tem a tabela de preços por modelo (entrada, saída, leitura
  e escrita de cache, em USD por milhão de tokens) copiada da página oficial,
  com data; o custo da explicação é a soma das chamadas (inclusive a correção) mais
  o custo do modelo de checagem, somado ao `cost_usd` gravado. Os tokens gravados
  (`input_tokens` etc.) são só do modelo principal; os do modelo de checagem ficam
  em `uso_checagem` no resultado.
- Teto: se a soma de tokens de saída das chamadas passar de 20 000 na explicação,
  aborta com erro `custo_excedido` (não deveria acontecer; é rede de segurança).
  Conferido nas duas pontas: dentro de cada chamada e na soma da explicação. Fica
  acima do `max_tokens` de uma chamada (§4.1) para não jogar fora uma entrega válida
  e já paga.
- Cada etapa é um span do LangFuse (§8.3).

### 7.1 Modelo de dados

`CoachExplanation`:

| coluna | tipo | nota |
| --- | --- | --- |
| id | str(36) | |
| puzzle_id | FK puzzles | índice |
| review_id | FK reviews, nulo | a revisão que gerou o pedido |
| created_at | datetime | |
| model, prompt_version, effort | str | |
| text | text | prosa final derivada (`na_partida` + `por_que`) |
| structured_json | text | a resposta em blocos de §4.4; `{}` nas explicações antigas |
| lines_json, citations_json | text | do formato §4.4 |
| verification_json | text | `Verificacao` serializada |
| status | str | `ok` \| `warnings` \| `errors` |
| repaired | bool | houve segunda chamada |
| input_tokens, output_tokens, cache_read_tokens, cache_write_tokens | int | somados |
| cost_usd | float | |
| trace_id | str, nulo | LangFuse |
| duration_ms | int | |

`coach_chunks` e a tabela vetorial (§6.3). Migração via o `migrate(engine)`
existente em `core/db.py` (tabelas novas: `create_all`; a tabela virtual é
criada pelo `store.py` ao abrir).

## 8. Avaliação offline

Pasta `backend/evals/coach/` (fora do pacote, dentro do repositório).

### 8.1 Conjunto

- `dataset.py` gera `dataset/v1.json`: todos os puzzles `own` do banco do
  usuário no momento da geração (hoje 81; gravados como FEN, solução, lance
  errado, avaliações, sem PGN inteiro) mais 120 puzzles do Lichess
  estratificados por tema principal (10 temas mais comuns) e faixa de rating
  (< 1400, 1400–1800, > 1800), semente fixa. Cada item traz o gabarito da
  engine (`multipv=3` na posição inicial e na posição do erro, profundidade
  fixa) calculado uma vez e guardado, para as métricas não dependerem do
  Stockfish na hora da rodada.
- Nenhum texto de terceiros no conjunto. Os trechos de estudo usados nas
  rodadas vêm do banco local e não são versionados.

### 8.2 Rodadas e métricas

`run.py --variante {prompt,agente,agente_rag} --modelo {opus,sonnet} --n N
[--batch]`:

- `prompt`: uma chamada, sem ferramentas, contexto inteiro na mensagem
  (baseline).
- `agente`: ferramentas, sem `buscar_estudos` e sem recuperação prévia.
- `agente_rag`: o pipeline de produção.
- `--batch` usa a Batch API (metade do preço) para as variantes sem
  ferramentas; as variantes com ferramentas rodam em série com o cliente
  normal.

`metrics.py` calcula, por rodada: proporção de explicações com `erro` do
verificador (por tipo), média de avisos, lances ilegais por 100 explicações,
citações inexistentes, custo médio e p50/p95 de latência, tokens médios. Mais
a **nota pedagógica** 1–5 por LLM-as-judge (`judge.py`, modelo configurável,
padrão `claude-opus-5`, rubrica fixa em português: correção, clareza, foco no
erro do aluno, ação concreta). Calibração: o usuário avalia 20 itens à mão na
mesma rubrica; o relatório traz a concordância (Spearman) juiz × humano.

`report.py` escreve `docs/coach-eval.md` (tabela por variante × modelo, com
data, `PROMPT_VERSION`, tamanho do conjunto e custo total da rodada) e envia
cada rodada como *dataset run* ao LangFuse (dataset `coach-eval-v1`, um item
por puzzle, scores por métrica).

### 8.3 Observabilidade

- `observability.py`: se `langfuse_public_key`, `langfuse_secret_key` e
  `langfuse_host` estiverem nas Configurações, inicializa o SDK do LangFuse
  (v4, OpenTelemetry) e expõe `observe(nome)`; sem chaves, `observe` é um
  decorador identidade.
- Trace `coach.explain` com spans `contexto`, `recuperacao`, `dossie`, `llm`
  (uma geração por chamada à API, com modelo, tokens, custo), `verificacao`,
  `correcao`; metadados `puzzle_id`, `prompt_version`, `variante`. O
  `trace_id` vai para a explicação; o cartão mostra um link para o trace quando
  o host está configurado.
- Nada de conteúdo é enviado para fora além do host configurado (local por
  padrão).

## 9. API

| rota | corpo / resposta | notas |
| --- | --- | --- |
| `GET /api/coach/status` | `{configured, model, effort, index_chunks, index_model, index_stale, vector_backend ("sqlite-vec" \| "numpy"), langfuse_configured}` | o frontend decide se mostra o botão |
| `POST /api/coach/explain` | `{puzzle_id, review_id?}` → `CoachExplanationOut` | síncrona; 409 `coach_nao_configurado` sem chave; 502 com `detail` legível em erro da API; 503 se a engine não responder |
| `GET /api/coach/explanations/{puzzle_id}` | última explicação ou 404 | reabrir sem pagar de novo |
| `POST /api/coach/reindex` | `{queued, job}` | via `jobs`; 409 se já há tarefa |
| `PUT /api/settings` | campos novos | `anthropic_api_key` (só escrita), `coach_model`, `coach_effort`, `langfuse_public_key`, `langfuse_secret_key` (só escrita), `langfuse_host` |

`CoachExplanationOut`: `id, puzzle_id, created_at, model, text, lines,
citations [{chunk_id, study_id, study_title, chapter_id, chapter_name,
node_id, path_san, url}], verification {ok, issues}, status, repaired,
cost_usd, tokens {input, output, cache_read, cache_write}, duration_ms,
trace_url | null`. Cada item de `lines` vai com `fen_inicio: str | null` — a FEN
de onde a linha parte, com o lance nulo das linhas de ameaça já incluído —, para
o cartão resolver os lances numerados da prosa pela linha certa em vez de os
ancorar todos na posição do exercício; vem `null` quando não dá para partir dali
(linha de ameaça sem posição do erro, ou com o lado a mover em xeque).

Concorrência: uma explicação por vez por processo (lock), porque a engine
interativa é compartilhada; segunda chamada simultânea recebe 409
`explicacao_em_andamento`.

## 10. Interface

- **Resultado do exercício** (`train/ResultPanel.tsx`): na coluna da direita,
  abaixo do cartão "Meu erro"/"Na partida", o botão "Explicar" aparece quando
  `coach.configured`. Estados do cartão "Treinador": carregando (com aviso de
  que costuma levar cerca de um minuto), erro (mensagem da API, em português), pronto. Se já
  existe explicação para o puzzle, o cartão abre direto com ela e o botão vira
  "Explicar de novo".
- Leitura em blocos, na ordem: "Na partida" (`na_partida`), "Por que"
  (`por_que`), o `padrao` como etiqueta e "Treinar" com a lista de `treinar`,
  cada um com um rótulo pequeno em maiúsculas (`.bloco-rotulo`). Explicação
  gravada antes dos blocos cai no texto corrido (`text`).
- Texto renderizado pelo `TextoComLances` existente (lances clicáveis com
  prévia); marcadores `[c:ID]` viram links "Estudo › Capítulo › 12.Cf3" que
  abrem o capítulo em modo livro no lance (`?lance=`), reusando o formato de
  link dos estudos.
- Selo ao lado do título: "verificado pela engine" quando `verification.ok` sem
  avisos; "com ressalvas (N)" e "não verificado (N)" num `<details>` fechado,
  com as ressalvas sem repetição e os `lance_sem_linha` agrupados numa linha só.
  Nada escondido: tudo a um clique.
- Rodapé discreto numa linha: modelo, custo em dólares (US$ 0,04), tempo, link do
  trace, aviso de índice vazio e o botão secundário "Explicar de novo".
- Em tela larga (≥ 900 px) a coluna do tabuleiro fica `sticky` enquanto a coluna
  da direita rola (`.two-col.tabuleiro-fixo`): a posição não sai da tela quando
  o texto cita um lance. No celular o layout empilhado não muda.
- **Configurações** (`SettingsPage.tsx`): seção "Treinador (IA)": chave da API
  (mesmo padrão do token do Lichess: placeholder "guardada; digite para
  trocar", string vazia apaga), modelo (Opus 5 / Sonnet 5), esforço
  (baixo/médio/alto), LangFuse (host, chaves), estado do índice e botão
  "Recriar índice" (vocabulário: recriar, nunca "regerar").
- Dashboard e Progresso não mudam nesta fase.

## 11. Erros

| situação | comportamento |
| --- | --- |
| sem chave | botão não aparece; rota 409 com texto apontando Configurações |
| `AuthenticationError` | 502 "chave da API recusada; confira em Configurações" |
| `RateLimitError` | 502 "limite de uso da API atingido; tente em alguns minutos" |
| `APIConnectionError` | 502 "sem conexão com a API" |
| `BadRequestError` | um 400 genérico ("Invalid request data", que a API às vezes devolve depois de dezenas de segundos de geração num pedido igual aos anteriores) é repetido uma vez, com o mesmo pedido; se falhar de novo, ou se o 400 vier com mensagem específica, 502 com o `message` da API e registro no log com o corpo e o pedido inteiro |
| `stop_reason == "refusal"` | 502 "o modelo recusou responder" (não deve ocorrer; registrado) |
| `stop_reason == "max_tokens"` sem a entrega | 502 "a resposta passou do limite de tokens e foi cortada" (`resposta_truncada`) |
| engine (Stockfish) indisponível | 503 antes de chamar o modelo: o verificador não roda sem ela |
| engine sem resposta na verificação | explicação entregue com `status = errors` e issue `engine_indisponivel`; cartão mostra "não verificado" |
| resposta fora do esquema | uma nova tentativa; depois 502 |
| índice vazio | pipeline segue sem trechos; cartão avisa "sem estudos indexados" |

Logs no `server.log` existente, com `trace_id` quando houver. A linha de tempos
de cada explicação (total, dossiê, chamadas ao modelo, ferramentas, verificação,
checagem — `checagem <n> afirmacoes, <ms> ms` —, correção) sai também quando ela
morre no meio, com o dossiê, as chamadas à API e as ferramentas feitas até ali.

## 12. Docker

- `Dockerfile` na raiz, dois estágios: `node:22-alpine` faz `npm ci && npm run
  build`; `python:3.13-slim` instala `stockfish` do apt, copia `backend/`,
  `frontend/dist` e roda `uv sync --no-dev`; `CMD ["python", "-m",
  "chess_trainer"]`; porta 8000; volume `/data` para o SQLite e o CSV do
  Lichess. O caminho do banco e do Stockfish passam a aceitar variáveis de
  ambiente (`CHESS_TRAINER_DATA`, `STOCKFISH_PATH`), com os padrões atuais.
- `docker-compose.yml`: serviço `app` (build local, `./backend/data:/data`) e
  os serviços do LangFuse conforme o compose oficial deles (web, worker,
  Postgres, ClickHouse, Redis, MinIO) com volumes nomeados. Portas 8000 (app) e
  3000 (LangFuse). Chaves do LangFuse são criadas na interface dele e coladas
  nas Configurações do app.
- `docs/manual.pt-BR.md` ganha a seção "Rodar com Docker"; `uv run` continua
  sendo o modo de desenvolvimento.

## 13. Testes

Backend (pytest, sem rede, sem Stockfish real salvo `slow`):

- `test_coach_verify.py`: linhas legais/ilegais, início `inicial` × `erro` ×
  `ameaca` × `ameaca_erro` (lance nulo, sem posição do erro, em xeque),
  aderência às três principais (com engine falsa), avaliação dentro/fora da
  tolerância, mate, citação existente/inexistente, lances soltos, tamanho.
- `test_coach_chunks.py`: árvore sintética → trechos (intro, comentário,
  junção de curtos, partição de longos, `path_san`, hash estável).
- `test_coach_store.py`: upsert/busca/delete nos dois backends (sqlite-vec e
  numpy), invalidação por modelo; embeddings falsos determinísticos.
- `test_coach_explain.py`: pipeline com `FakeLlm` (roteiro com chamadas de
  ferramenta), verificação ok, verificação com erro → correção, correção que
  não melhora mantém a primeira, custo somado, gravação, teto de tokens.
- `test_api_coach.py`: status, 409 sem chave, explain feliz, reabrir,
  reindex via jobs, settings com chave nunca ecoada, lock de concorrência.
- `test_coach_costs.py`: preços × usage.
- `evals/tests/test_eval_harness.py`: rodada de 3 itens com `FakeLlm`, métricas
  e relatório gerados.
- `@pytest.mark.slow` + `@pytest.mark.network`: uma explicação real com a
  chave do ambiente (`ANTHROPIC_API_KEY`), pulada sem ela.

Frontend (Vitest): cartão nos três estados, botão condicionado ao status,
"Explicar de novo", links de citação, selo por `verification`, seção de
Configurações (chave não ecoada, recriar índice).

## 14. Fases seguintes (fora deste spec)

1. **Fase 2**: fine-tuning local com LoRA de um modelo pequeno (Hugging Face,
   RTX 3060) para o comentário curto, com dados sintéticos destilados do modelo
   grande e filtrados pelo verificador; servido localmente e medido na mesma
   avaliação de §8. Ambiente Python separado (`ml/`) com PyTorch/CUDA.
2. **Fase 3**: modelo de temas e dificuldade para puzzles próprios, treinado
   na base do Lichess (baseline gradient boosting × CNN), MLflow para os
   experimentos, ONNX no backend.
3. **Fase 4**: o "professor particular": plano de estudo e sequência de
   exercícios gerados a partir dos erros, estatísticas e material do usuário.

## 15. Fora de escopo nesta fase

Chat livre com o tabuleiro; relatório semanal; Bedrock implementado (só a
interface); streaming da resposta na interface; explicações para táticas do
Lichess fora da fila de repetição; várias explicações guardadas por puzzle
(guarda-se só a última); tradução para outros idiomas; conta de usuário.
