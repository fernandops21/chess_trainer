# Chess Trainer — Golpes: irmãos do erro, repetição e codificador

Data: 2026-09-16. Estado: aprovado em conversa; pronto para o plano.

## 1. Motivação

O app transforma os erros do usuário em exercícios e traz a base de puzzles do
Lichess (1,06 milhão de puzzles com rating e temas). Duas queixas ficam de fora:

- Errar um exercício ensina pouco sozinho. O que fixa uma ideia é repetir **o
  mesmo golpe em outras posições**, várias vezes seguidas, e depois reencontrá-lo
  espaçado no tempo.
- Os temas do Lichess são grossos demais para isso. "Mate em 2" tem milhares de
  puzzles sem nada em comum; "garfo" idem. O que o jogador reconhece é a
  geometria: as peças que participam, as casas, o que é descoberto ou capturado.

Este spec define a **assinatura do golpe**, a busca de **irmãos** (puzzles do
Lichess com o mesmo golpe), o fluxo no treino (bloco de repetição imediata e
entrada na repetição espaçada) e, numa segunda fase, um **codificador** treinado
por contraste que aprende o "parecido" que a regra não descreve. Tudo sem modelo
de linguagem e sem custo por uso.

## 2. Decisões

- "Mesmo golpe" é geometria da **solução**, não etiqueta: peças que movem, casas
  de destino, capturas, xeques, ataques descobertos, casa do rei adversário.
- A assinatura sai de regras (python-chess) e serve a dois fins: busca exata e
  **supervisão fraca** (*weak supervision*) para o codificador. Sem a regra a
  rede não tem rótulo; sem a rede a busca fica presa ao que a regra descreve.
- O codificador é **um modelo só, treinado uma vez** no Lichess e distribuído
  com o app (ONNX). Nada é treinado por usuário. O que é pessoal é o perfil e a
  fila.
- A rede só entra no produto se ganhar da regra numa medida definida antes
  (§9). Se não ganhar, o produto fica com a regra e o experimento fica
  documentado.
- **O treino roda na máquina do usuário, disparado por ele.** Nenhum agente ou
  tarefa automática executa treino; os scripts são entregues prontos e a
  execução e o aviso de término são do usuário.
- Downloads (torch com CUDA, ~2,5 GB) só com o ok explícito do usuário.

## 3. Assinatura do golpe (`core/golpes/assinatura.py`, pura)

### 3.1 Entrada

- Posição do puzzle (a que o solucionador joga), lista de lances da solução a
  partir dela em UCI, alternando solucionador e adversário, e a cor do
  solucionador.
- Lichess: `moves` traz primeiro o lance de preparação do adversário; a posição
  do puzzle é depois dele. Exercícios próprios: `fen_start` e `solution.moves`
  (`by = solver | engine`).

### 3.2 Normalização

- Se o solucionador joga de pretas, o tabuleiro é espelhado verticalmente com as
  cores trocadas (`Board.mirror()`): o solucionador é sempre as brancas e o rei
  adversário é sempre o preto. O mesmo golpe jogado por qualquer cor tem a mesma
  assinatura.
- Espelhar esquerda-direita **não** normaliza: um golpe na ala do rei e o mesmo
  na ala da dama são "parecidos", não "o mesmo" (§5).

### 3.3 O que se anota por lance do solucionador (até os três primeiros)

| campo | valor |
| --- | --- |
| peça | K, Q, R, B, N, P |
| origem | casa (só no nível completo) |
| destino | casa |
| captura | tipo da peça capturada, ou nada; en passant conta como P |
| xeque | `+` simples, `++` duplo, `d+` descoberto (quem dá xeque não é a peça que moveu), `#` mate |
| promoção | peça promovida, quando houver |
| descoberta | peças adversárias (nem rei nem peões) que passam a ser atacadas por **outras** peças do solucionador por causa do lance: tipo e casa, as duas mais valiosas |
| ataques | peças adversárias (nem rei nem peões) que passam a ser atacadas pela **própria** peça que moveu: tipo e casa, as duas mais valiosas |

Mais a casa do rei adversário na posição do puzzle. As respostas do adversário
não entram: são o que varia entre puzzles do mesmo golpe. Peões não contam como
alvo de descoberta ou ataque (quase todo lance "ataca um peão"; seria ruído que
separaria golpes iguais). Num lance de mate, descobertas e ataques ficam vazios:
a partida acabou, o que a peça ataca não descreve o golpe.

Exemplos (solucionador embaixo, notação da assinatura):

```
Francesa, avanço (9.Bb5+ descobre a dama):  rei e8 | B b5 + descobre Q d4 | Q xd4
Beijo grego:                                rei g8 | B xh7 + | N g5 + | Q h5
Garfo de cavalo com xeque:                  rei g8 | N e7 + ataca Q c8 | N xc8
```

### 3.4 Três níveis

| nível | conteúdo | uso |
| --- | --- | --- |
| esqueleto | zona do rei; por lance: peça, captura (tipo), xeque, promoção, descoberta e ataques só por tipo de peça; sem casas | camada mais larga da busca; calibração |
| destinos (padrão) | esqueleto com casa do rei e casas de destino, descobertas e ataques com casa | "mesmo golpe nas mesmas casas"; classe do contraste |
| completo | destinos mais a casa de origem | depuração e julgamento manual; fino demais para treino |

Zona do rei: coluna (a–c ala da dama, d–e centro, f–h ala do rei) × fila (7–8
fundo, outras exposto): seis zonas.

Cada nível é gravado como texto canônico e como inteiro de 64 bits (os 8
primeiros bytes do BLAKE2b do texto, como inteiro com sinal). A busca compara
inteiros. Junto vai `destinos_esp`: o hash do nível de destinos do puzzle
espelhado esquerda-direita (`flip_horizontal`), para a busca do parecido por
espelho ser uma igualdade.

A regra tem um número de **versão** (`VERSAO_ASSINATURA`). Mudar a regra sobe a
versão; a tarefa de preparo refaz o que estiver com versão antiga.

Puzzles de lance quieto (sem captura, xeque, descoberta nem ataque novo) ficam
com assinatura fraca: só peça e destino. Aceito e medido (§9), não resolvido.

### 3.5 Trechos

Medido nos dados do usuário (129 exercícios, leitura): exigir a assinatura da
solução **inteira** só acha algum irmão em 58 dos 129 (45%) — soluções de um
lance quase nunca coincidem inteiras (só 4% dos puzzles do Lichess têm um
lance só) e soluções de três lances são específicas demais. Deixando o
casamento acontecer com um **trecho** contíguo da solução — a sequência da
âncora inteira, senão os dois primeiros lances, senão só o primeiro —
aparecendo em QUALQUER posição da solução de um candidato (mesmas casas, rei
na casa de quando o trecho começa), 101 dos 129 (78%) acham cinco ou mais
irmãos (só o início: 85; só o fim: 76). Essa é a motivação dos trechos.

- `Trecho(inicio, n, posicao, assinatura)`: um pedaço de `n` lances do
  solucionador começando no `inicio`-ésimo (0-based) de uma solução.
  `assinatura` é a `Assinatura` desse pedaço (`anotar` a partir do tabuleiro
  de quando o trecho começa — o rei aparece na casa de NAQUELE momento, não
  na da posição do puzzle).
- `posicao` é relativa a TODOS os lances do solucionador da solução:
  `"inteira"` quando o trecho cobre todos, `"inicio"` quando começa no
  primeiro, `"fim"` quando termina no último, senão `"meio"`.
- `trechos(fen, lances, max_solver=6, tamanhos=(1,2,3))` gera todos os trechos
  de 1, 2 e 3 lances começando em cada um dos até seis primeiros lances do
  solucionador (normaliza como `assinar`).
- O esqueleto de um trecho de **um lance só** é ruído: bate com quase
  qualquer coisa (não descreve geometria nenhuma sozinho) e por isso nunca é
  gravado nem entra numa busca por esqueleto — só o nível `destinos` (e seu
  espelho) usa trechos de um lance.

### 3.6 Padrões de mate (`core/golpes/mates.py`, puro)

Motivação: um exercício do usuário que termina em mate ("36.Rb8+ Qd8 37.Rxd8+
Ne8 38.Rxe8#") tem uma assinatura específica demais para achar irmãos por
geometria exata — o golpe todo bate com zero puzzles do Lichess, os dois
primeiros lances com 25 — mas é um **padrão nomeado** ("rei preso atrás dos
próprios peões, torre entra na última fila"), o nível que o usuário reconhece
("mate de Philidor", não "mate em 2"). O Lichess já etiqueta esse padrão em
`lichess_puzzle_themes`; o exercício do usuário, não. A solução: detectar o
padrão na posição final do exercício por regra e buscar os irmãos pela
etiqueta do Lichess, sem passar pela assinatura.

`padrao_de_mate(board)` roda, na posição final de xeque-mate, os detectores
abaixo — só peças, casas e python-chess, sem heurística de avaliação — na
ordem do mais específico ao mais geral, e devolve o primeiro tema (nome do
Lichess) que bater, ou `None` fora do xeque-mate ou sem padrão aprovado:

1. **`smotheredMate`** (mate sufocado): xeque de cavalo só, todas as oito
   casas ao redor do rei ocupadas por peças da própria cor (nenhuma fuga nem
   bloqueio possível).
2. **`arabianMate`** (mate árabe): rei num canto do tabuleiro, torre
   adjacente (distância 1) dando o único xeque, protegida por um cavalo.
3. **`backRankMate`** (mate do corredor): rei na própria última fila, torre
   ou dama dando xeque nela, e as três casas à frente do rei (fora da última
   fila) todas ocupadas por peças da própria cor.

`padrao_do_exercicio(fen, lances)` repete a solução inteira a partir de `fen`
e, terminando em xeque-mate com um padrão aprovado, devolve `(tema, n)` — `n`
é quantos lances o solucionador jogou; `None` sem mate, sem padrão, FEN
inválida ou lance ilegal (nunca levanta — é um degrau opcional da cascata).

**Medição** (script de leitura `evals/golpes/medir_mates.py`, contra as
242 413 posições de mate do Lichess, prototipagem fora do produto): recall e
precisão de cada detector contra a etiqueta correspondente do Lichess.

| padrão | recall | precisão | as sobras da precisão |
| --- | --- | --- | --- |
| sufocado | 100% | 100% | — |
| árabe | 100% | 77% | pillsbury, vukovic, outros mates de canto sem etiqueta |
| corredor | 100% | 26% | a regra tolera UMA casa vazia à frente do rei quando o adversário a cobre (o exercício real que motivou o degrau é assim: f7 e g7 com peões, h7 vazia e coberta pela dama); com as três casas ocupadas a precisão era 58%, e o que sobra o Lichess exclui por regra (§3.6.1), não por esquecimento. O detector só classifica o exercício do usuário; os irmãos vêm sempre da etiqueta do Lichess |

Só estes três foram aprovados. Protótipos de **dovetail**, **epaulette** e
**boden** não bateram com a definição do Lichess (recall abaixo do piso) e
ficam de fora. Regra para aprovar um detector novo: recall ≥ 95% contra a
etiqueta do Lichess, com as sobras da precisão inspecionadas à mão — precisão
baixa sozinha não reprova um detector quando as sobras são estruturalmente
corretas (o caso do corredor e do árabe acima); recall abaixo do piso, sim.

Achado ao portar os detectores: a regra do corredor exige as três casas à
frente do rei OCUPADAS por peça própria, não só cobertas a distância — uma
posição real onde a fuga é coberta por uma peça de longo alcance em vez de
bloqueada por um peão não bate com a regra literal, mesmo sendo um corredor
"na ideia". Aceito (mesma régua de precisão/recall acima) e não resolvido
para não arriscar as taxas medidas com uma condição mais frouxa.

### 3.6.1 Duas regras, dois usos — etiquetas próprias para o Lichess (2026-09-19)

Medido depois, lendo (sem escrever) as 242 413 mates do Lichess: o detector do
corredor com a regra FROUXA acima (qualquer peça própria à frente do rei, sem
exigir peão) acha 9 224 mates que o Lichess não etiquetou `backRankMate`.
Correção honesta: uma afirmação anterior dizia que esses 9 224 extras eram
"corredores sem etiqueta"; inspecionando uma amostra deles à mão, metade não
era — era outra ideia, uma torre ou dama presa por cravada bem na frente do
rei, não bloqueando por ser um peão dele. A regra frouxa não distingue as duas
situações.

**A regra exata do Lichess**, reconstruída e conferida contra as etiquetas dele
nos 242 413 mates (cobertura 100%, zero extras): rei na primeira fila, xeque de
torre ou dama pela fila, toda casa à frente ocupada por peça própria **e
nenhuma dessas casas atacada por quem dá mate**. Ou seja, para o Lichess só é
corredor quando o rei está preso EXCLUSIVAMENTE pelas próprias peças. Os extras
das nossas regras não foram "esquecidos": foram excluídos por essa condição.
Ela junta dois casos que para o jogador são diferentes:

- um **peão** do escudo atacado de passagem (`Qe8#` contra f7/g7/h7 com uma
  torre branca em f1 mirando f7): continua sendo corredor — o peão não recua
  para bloquear e o rei não toma o próprio peão, então o ataque não muda nada;
- uma **peça** à frente do rei que só não ajuda porque está cravada (`Rxd8#`
  com a torre de f7 cravada pelo bispo de d5, puzzle `oMSgP`): aí a cravada é
  a ideia e o corredor é o cenário; o Lichess etiqueta `pin`.

Exigir PEÕES à frente (a regra apertada abaixo) separa exatamente esses dois.

**As etiquetas não se excluem.** No Lichess um puzzle leva vários temas: dos
12 813 `backRankMate`, 52% também são `sacrifice`, 12% `xRayAttack`, 11%
`deflection`, 11% `fork`, 2% `pin` (a cravada no caminho, com o mate final
limpo); 1 415 puzzles têm dois mates nomeados. Por isso `padroes_de_mate` /
`padroes_do_exercicio` devolvem a LISTA de padrões (do mais específico ao mais
geral), a cascata roda o degrau para cada um, e o cartão mostra
"mate árabe + mate do corredor". Os nomes no singular (`padrao_de_mate`…)
ficam como atalho para o mais específico.

A resposta foi separar a regra em duas, para dois usos diferentes:

- **`corredor`** (`core/golpes/mates.py`), tolerante — continua exatamente
  como estava: classifica a assinatura do EXERCÍCIO DO USUÁRIO (`padrao_de_mate`
  /`padrao_do_exercicio`, tema `backRankMate` de `PADROES`), tolerando uma casa
  vazia coberta a distância, porque é assim que o exercício real que motivou o
  degrau se parece (§3.6 acima).
- **`corredor_apertado`** (`PADROES_PARA_CANDIDATOS`, `padrao_para_candidato`),
  apertada — nunca classifica o exercício do usuário; só GERA UMA ETIQUETA
  PRÓPRIA para puzzles do Lichess que ele mesmo não etiquetou (§4, tabela
  `lichess_puzzle_padroes`). Exige toda casa à frente do rei ocupada por um
  PEÃO da própria cor (não qualquer peça) e a torre/dama do xeque NÃO
  adjacente ao rei. Medida contra os 242 413 mates: recall 93,8% da etiqueta
  `backRankMate` (12 004/12 802) e 4 451 extras sem etiqueta — uma amostra
  desses foi inspecionada à mão e é textbook (`Qe8#` contra f7/g7/h7, `Rf8#`
  com o rei em h8 atrás de g7/h7), a mesma régua de aprovação usada nos três
  padrões originais (recall ≥ 95%, sobras inspecionadas à mão). O pool de
  puzzles com o tema `backRankMate` (etiqueta do Lichess OU própria) sobe de
  12,8 mil para uns 17,3 mil.

O degrau `padrao-mate` da cascata (§5) passa a buscar irmãos nas DUAS fontes —
a etiqueta do Lichess em `lichess_puzzle_themes` e a etiqueta própria em
`lichess_puzzle_padroes` — e `Procedencia.nivel` marca de qual delas veio cada
irmão: `"{tema}:lichess"` ou `"{tema}:regra"` (ex. `"backRankMate:regra"`).
Isso deixa o placar de votos (§8) responder se os irmãos rule-tagged são tão
bons quanto os oficiais do Lichess, em vez de assumir que são.

## 4. Dados e tarefa de preparo

### 4.1 Tabelas

- `lichess_puzzle_signatures`: `puzzle_id` (PK, FK), `versao`, `esqueleto`,
  `destinos`, `destinos_esp`, `completo` (inteiros), `texto_completo`,
  `zona_rei`, `n_lances`. Índices em `destinos`, `destinos_esp`,
  `(esqueleto, zona_rei)`.
- `puzzle_signatures`: o mesmo para os exercícios próprios (`puzzles`).
  Calculada quando o exercício é criado e refeita quando a versão muda.
- `lichess_puzzle_trechos` (spec §3.5): `puzzle_id` (FK, cascade),
  `inicio`, `n` (chave junto com `puzzle_id`), `posicao`, `destinos`,
  `destinos_esp` (inteiros), `esqueleto` (inteiro, nulo quando `n == 1`).
  Índices em `destinos`, `destinos_esp`, `esqueleto`. Uns 4,5 trechos por
  puzzle em média.
- `puzzles.sibling_of` (texto, nulo, FK `puzzles.id`): o exercício de origem de
  um irmão salvo pelo bloco (§6). É o vínculo que o perfil futuro usa.
- `puzzles.sibling_tier`: o degrau da cascata (§5) que trouxe esse irmão,
  espelhando `Procedencia.degrau` de quando ele entrou (§6).
- `golpe_labels` (§8), com a procedência do candidato na hora do julgamento:
  `n_lances`, `posicao`, `nivel`, `espelhado` (§8).
- `lichess_puzzle_padroes` (§3.6.1, "etiquetas próprias"): `puzzle_id` (FK
  `lichess_puzzles.id`, cascade), `padrao` (`String(24)`), chave primária
  (`puzzle_id`, `padrao`), `versao`. Índice em `padrao`. Uma linha por puzzle
  do Lichess que `padrao_para_candidato` classificou com um padrão que ele
  mesmo não etiquetou (hoje só `backRankMate`, via `corredor_apertado`).
- Fase B: `lichess_puzzle_vectors` e `puzzle_vectors` (§7).

### 4.2 Tarefa "Preparar golpes"

- Botão em Configurações, no executor de tarefas existente (`JobRunner`), com
  progresso e cancelamento. Percorre `lichess_puzzles` em lotes de 5 000,
  calcula só as linhas sem assinatura ou com versão antiga, grava a
  assinatura E os trechos (§3.5) da linha por lote. Cancelar e retomar
  continua de onde parou.
- No fim, grava em `settings` a **cobertura** por nível: quantos puzzles têm
  grupo de tamanho ≥ 5, ≥ 2 e 1 (sozinhos); e a contagem de trechos gravados
  (`GET /api/golpes/status` traz `trechos`). É o primeiro número da
  calibração (§8) e aparece na tela de dev.
- Estimativa: quinze minutos (era dez antes dos trechos: cada puzzle reproduz
  a solução mais vezes — uma por trecho, além da assinatura inteira). O banco
  cresce mais que antes (a tabela de trechos tem uns 4,5× as linhas da de
  assinaturas).
- **Passada leve das etiquetas próprias** (`preparar_padroes`, §3.6.1): depois
  da assinatura/trechos acima (mesmo quando não havia nada pendente ali — um
  clique só faz as duas coisas), varre só os puzzles com o tema geral `mate`
  em `lichess_puzzle_themes`, rejoga a solução inteira e grava em
  `lichess_puzzle_padroes` quando `padrao_para_candidato` acha um padrão que
  o Lichess ainda não etiquetou nesse puzzle. Controlada por uma versão
  (`VERSAO_PADROES`, `golpes_padroes_versao` em `settings`): sem mudança na
  versão, não faz nada; mudando (detector candidato novo ou mudado), refaz a
  tabela inteira do zero. Cerca de um minuto — bem mais rápido que a
  assinatura porque só varre os puzzles marcados `mate`, não o banco inteiro
  — e por isso não guarda progresso de retomada: cancelar não grava a versão,
  a próxima chamada recomeça do zero. `GET /api/golpes/status` traz `padroes`
  (quantas linhas existem).

## 5. Busca de irmãos (`core/golpes/service.py`)

`irmaos(db, fen, lances, faixa_de_rating, excluir, k=5)` devolve até k
puzzles do Lichess, cada um com a **procedência** de onde veio: `degrau`
(nome do passo da cascata, mantido em `tier` por compatibilidade), `nivel`
(`destinos` | `destinos_esp` | `esqueleto`), `n` (quantos lances entraram na
comparação), `posicao` (a do trecho **do candidato** que casou) e `espelhado`.

A cascata anda em degraus, na ordem (spec trechos §5; `k = min(n_solver, 3)`
lances da âncora):

1. `inteira` — `destinos` da solução inteira da âncora igual ao do candidato
   (o que já existia, antes chamado "mesmo").
2. `trecho{n}`, para `n = k … 2` — o prefixo de `n` lances da âncora (de
   `trechos(fen, lances)` com `inicio == 0`) igual a um trecho de tamanho `n`
   **em qualquer posição** da solução do candidato. Casando em mais de uma
   posição, fica o de menor `inicio`.
3. `padrao-mate` — só quando `padrao_do_exercicio(fen, lances)` acha um
   padrão aprovado (§3.6): duas subconsultas (sem tabela de assinatura), na
   ordem — primeiro o tema junto de `mateIn{n}` (`n` capado em 5), depois o
   tema sozinho. Cada subconsulta busca nas DUAS fontes (§3.6.1): puzzles
   etiquetados `tema` em `lichess_puzzle_themes` (pelo Lichess) UNIÃO puzzles
   com uma linha em `lichess_puzzle_padroes` para `tema` (etiqueta própria) —
   um puzzle rule-tagged ainda tem a etiqueta geral `mateIn{n}` do Lichess
   (só falta a etiqueta específica do padrão), então o mesmo filtro de
   `mateIn{n}` funciona nas duas fontes. Um puzzle com as duas etiquetas conta
   uma vez só, pela do Lichess. Fica ANTES de `trecho1` e DEPOIS de todo
   `trecho{n}` com `n ≥ 2`: medido no exemplo que motivou este degrau
   (36.Rb8+ Qd8 37.Rxd8+ Ne8 38.Rxe8#), a solução inteira bate com zero
   puzzles do Lichess e os dois primeiros lances com 25 — pouco —, enquanto
   só a etiqueta `backRankMate` já tem 12 813 puzzles (mais as próprias,
   §3.6.1). Para um exercício de mate, "mesmo padrão nomeado" é um irmão
   melhor do que "um lance idêntico" (`trecho1`, o degrau mais frouxo da
   família de trechos); os votos (§8) confirmam ou refutam essa ordem.
4. `trecho1` — o mesmo `trecho{n}` acima, para `n = 1`.
5. `espelho` — `destinos_esp` da âncora igual ao `destinos` do candidato
   (o espelho esquerda-direita); depois `espelho-trecho{n}` para `n = k … 2`
   (mesma ideia, por trecho).
6. `esqueleto` — `esqueleto` e `zona_rei` da âncora iguais aos do candidato
   (o que já existia); depois `esqueleto-trecho{n}` para `n = k … 2` (por
   trecho; o esqueleto de um lance só nunca entra, §3.5).

Cada degrau exclui os puzzles que um degrau anterior já devolveu — inclusive
as duas subconsultas do `padrao-mate` entre si.

A procedência do `padrao-mate` usa os mesmos campos com outro sentido:
`nivel` é o tema do Lichess MAIS a procedência da etiqueta (§3.6.1), separados
por `:` — `"{tema}:lichess"` quando o Lichess mesmo etiquetou, `"{tema}:regra"`
quando só a etiqueta própria achou (ex. `"backRankMate:regra"`, até 19
letras; `"smotheredMate:lichess"`, o mais longo hoje, tem 21 — por isso
`GolpeLabel.nivel` é `String(24)`, não mais `String(10)`); `n` é quantos
lances o solucionador jogou até o mate, `posicao` é sempre `"inteira"` e
`espelhado` é sempre `False`. O placar de votos (§8) agrupa por `nivel`
também, não só por degrau/posição/lances — sem isso, um voto num mate
sufocado e um voto num corredor cairiam na mesma linha (ambos `tier ==
"padrao-mate"`).

Dentro de cada degrau a busca **ignora rating**: só `popularity ≥ 50` e
`nb_plays ≥ 50` para evitar puzzles ruins, excluídos os já vistos
(`tactics_attempts`), os já salvos na fila e a própria âncora. Quem decide o
degrau é o golpe, não o rating — um irmão exato fora da faixa do usuário
continua "inteira", nunca cai para um degrau mais frouxo por causa disso.

O rating só escolhe **quais** irmãos entram no bloco. A faixa preferida é
`[rating − golpes_faixa_abaixo, rating + golpes_faixa_acima]` (padrão 100
abaixo, 500 acima: o bloco sobe a partir do nível do usuário). Dentro de cada
degrau, os candidatos da faixa são espalhados **do fácil ao difícil**;
faltando para completar `k`, entram os mais próximos de fora da faixa —
primeiro os de cima (subindo), depois os de baixo (descendo, o mais perto
primeiro). Por segurança, a consulta de cada degrau corta em `LIMITE_CANDIDATOS`
(5 000) candidatos, os mais próximos do centro da faixa preferida. O bloco
final fica em ordem ascendente de rating, mesmo cruzando degraus (cada item
mantém a `procedencia` de onde veio). A resposta traz, por item, `tier`,
`procedencia`, rating e os campos do puzzle; e a assinatura da âncora em
texto.

A âncora pode ser um exercício próprio ou um puzzle do Lichess: qualquer puzzle
com assinatura tem irmãos.

## 6. Fluxo no treino

- **Cartão "Repetir o golpe"** na tela de resultado de um exercício da fila e na
  de uma tática do Lichess. Quando o usuário **erra**: a imagem do golpe (§6.1)
  e o botão "Treinar N parecidos" (N = tamanho do bloco, padrão 5). Quando
  acerta: só a imagem. Sem irmãos, o cartão não existe.
- **Bloco**: o botão abre a sessão de táticas existente com a lista fixa dos
  irmãos, na ordem do fácil ao difícil. Cada tentativa é registrada como hoje
  (`tactics/attempts`, rating de táticas). No fim, resumo "4 de 5" e volta.
- **Repetição espaçada**: cada irmão do bloco é salvo na fila do usuário pelo
  mecanismo que já salva táticas do Lichess (`tactics/{id}/save`), com
  `sibling_of` apontando para a âncora e `sibling_tier` gravando o degrau da
  cascata (§5) que o trouxe. A partir daí é revisado como qualquer exercício,
  misturado e espaçado; `sibling_tier` fica disponível para o perfil futuro
  medir se golpes achados por trecho se fixam tão bem quanto os "inteira".
- **Voto**: no painel de resultado de cada irmão do bloco, depois da tentativa
  registrada, um cartão opcional "Tem a ver com o seu erro?" com três respostas
  (mesmo golpe, parecido, nada a ver) grava o julgamento em `golpe_labels`
  (§8) — o voto mora no bloco, não numa tela à parte, porque julgar "é o
  mesmo golpe?" exige jogar o irmão, e é isso que o bloco já faz. "Próximo"
  funciona sem votar.
- **Configurações**: `golpes_enabled` (padrão ligado), `golpes_bloco` (padrão
  5, de 3 a 10), `golpes_faixa_abaixo` (padrão 100, de 0 a 1000) e
  `golpes_faixa_acima` (padrão 500, de 0 a 2000) — a faixa preferida do bloco
  em volta do rating de táticas (§5).

### 6.1 Imagem do golpe

Rota `GET /api/golpes/{origem}/{id}/imagem.svg` (`origem` = `own | lichess`):
o servidor desenha o tabuleiro com `chess.svg`, solucionador embaixo, os lances
do solucionador em setas verdes, descobertas e ataques em setas vermelhas, casa
do rei adversário e casas de destino marcadas. Estática, cacheável, serve no
cartão e, mais adiante, para salvar ou compartilhar.

### 6.2 API

- `GET /api/golpes/{origem}/{id}/irmaos?k=5` → `{assinatura, itens: [{tier,
  procedencia, puzzle...}]}`; 404 sem assinatura ou com o recurso desligado.
- `GET /api/golpes/{origem}/{id}/imagem.svg`.
- `POST /api/tactics/{lichess_id}/save` ganha `sibling_of` e `sibling_tier`
  opcionais.
- `POST /api/golpes/preparar` dispara a tarefa; o status vem pelo executor
  (`GET /api/golpes/status` traz `trechos`, a contagem de linhas de trecho).
- `POST /api/golpes/voto` e `GET /api/golpes/voto` (§8): parte do produto,
  atrás só de `golpes_enabled`, sem portão de desenvolvimento.

## 7. Codificador (fase B, `ml/golpes/`)

### 7.1 Entrada

Planos 8×8 com a orientação normalizada (§3.2): 12 planos de peças, 1 de en
passant, 4 de roque, e 6 planos de origem/destino dos três primeiros lances do
solucionador. A rede vê posição e golpe juntos, como a assinatura.

### 7.2 Rede e aprendizado

- ResNet convolucional em PyTorch: cerca de 20 blocos de 192 filtros, vetor
  final de 128 dimensões normalizado (L2). Precisão mista, AdamW, agenda de
  cosseno, lotes de 512. Cabe na RTX 3060 de 6 GB; uma ou duas noites sobre o
  milhão.
- Três cabeças, uma perda somada com pesos:
  - **contraste supervisionado** (*supervised contrastive*, SupCon,
    temperatura 0,1): a classe é o hash de `destinos`; só classes com ≥ 2
    puzzles no treino entram;
  - **temas do Lichess**: entropia cruzada multi-rótulo sobre os ~60 temas;
  - **rating**: regressão (Huber) sobre `(rating − 1500) / 500`.
- Divisão: 90/5/5 por hash do id do puzzle, e **5 % das assinaturas inteiras**
  movidas para o teste (*held-out signatures*): é nessa fatia que se mede se a
  rede generaliza para golpes que nunca viu, e não só decora grupos.

### 7.3 Scripts (executados pelo usuário)

- `preparar_dados.py`: exporta do SQLite para arquivos numpy em
  `data/ml/golpes/` (planos uint8, rótulos, divisão), com hash dos dados.
- `treinar.py`: treino com configuração em arquivo; grava por rodada um json com
  configuração, métricas por época, hash dos dados e o melhor checkpoint.
- `avaliar.py`: métricas automáticas e no ouro (§9); escreve as tabelas de
  `docs/golpes-eval.md`.
- `exportar.py`: ONNX, conferido contra o PyTorch na mesma entrada; vetores do
  milhão calculados e quantizados.
- Dependências no extra opcional `ml` do `pyproject` (torch com CUDA, ~2,5
  GB): só quem treina instala, com ok prévio.

### 7.4 Serviço no app

- Pesos ONNX (~30 MB) como arquivo de release, colocados na pasta de dados; o
  app roda com `onnxruntime` (já presente) para assinar vetor nos exercícios
  próprios na criação.
- `lichess_puzzle_vectors`: tabela vec0 do sqlite-vec com int8[128] (vetor
  normalizado escalado), ~130 MB; `puzzle_vectors` para os próprios. Sem
  sqlite-vec, a camada 3 fica desligada (a busca por regra não depende dela).
- A camada 3 da busca só liga depois do portão (§9) e do arquivo de pesos
  presente.

## 8. Votos no bloco e conjunto de ouro

Revisão de 2026-09-18: a tela `/rotulagem` separada saiu. Ela pedia para
julgar "é o mesmo golpe?" olhando duas posições paradas lado a lado — mas
julgar isso de verdade exige **jogar** o irmão, e é isso que o bloco de
repetição (§6) já faz. A decisão do usuário: "jogo, aparecem os irmãos, vou
jogando e votando em cada um; o módulo de rotulagem pode ser junto com prod,
apenas um botão a mais de voto". O voto entrou no produto, atrás só de
`golpes_enabled` (sem portão de desenvolvimento); `CHESS_TRAINER_ROTULAGEM`,
a tela, a rota `proximo_item` (sorteio de âncora) e o degrau só-de-medição
`espelho-trecho1` (§5) saíram junto — sem uma tela cega e embaralhada, não
havia mais uso para eles.

- No painel de resultado de cada irmão do bloco, depois da tentativa
  registrada, um cartão pergunta "Tem a ver com o seu erro?" com três
  respostas: **mesmo golpe**, **parecido**, **nada a ver** (`VotoDoGolpe`).
  Opcional — "Próximo" funciona sem votar — e nunca mostra a `tier` nem a
  procedência a quem vota; elas só viajam junto do voto para agregar depois.
- `POST /api/golpes/voto` grava o voto; `GET /api/golpes/voto` devolve o já
  gravado para o par, para marcar o botão escolhido ao reabrir a tática.
- `golpe_labels`: `id`, `anchor_origem`, `anchor_id`, `candidate_id`,
  `tier_na_hora`, `versao_assinatura`, `label`, `created_at`, e a procedência
  do candidato na hora (spec trechos §5): `n_lances`, `posicao`, `nivel`,
  `espelhado`. **Uma linha por par** (âncora, candidato) — índice único em
  `(anchor_origem, anchor_id, candidate_id)`: votar de novo no mesmo par
  atualiza o rótulo e a procedência em vez de duplicar (upsert). Exportado
  por comando para `ml/golpes/gold/<data>.jsonl` (as mesmas colunas de
  procedência vão junto), versionado no repositório — sem mudança nesse
  formato.
- **Placar por procedência**: `GET /api/golpes/votos/resumo` devolve,
  agrupado por `(tier, posicao, n_lances, nivel)`, quantos votos de cada
  resposta aquela combinação já recebeu (`mesmo`, `parecido`, `nada`,
  `total`) — `nivel` entra no agrupamento por causa do degrau `padrao-mate`
  (§5): ele usa a mesma `tier_na_hora` para qualquer tema e procedência de
  mate, então sem `nivel` na chave os votos de padrões e fontes diferentes
  ficariam somados numa linha só. Mostrado em **Configurações → Golpes**,
  dentro de um `<details>` "Votos por procedência" com a coluna "nível" — é o
  mesmo sinal de qual degrau (e qual posição do trecho, e agora qual
  procedência do padrão de mate) é ruído, só que alimentado pelo uso normal
  do treino em vez de uma sessão de rotulagem à parte.
- Meta: ~300 julgamentos nas primeiras sessões, agora espalhados pelo uso
  normal. Com a rede treinada, um destino futuro é priorizar no bloco os
  pares em que regra e rede discordam (**aprendizado ativo**); ainda não
  implementado.

## 9. Medição e portão de entrada

| medida | como | serve para |
| --- | --- | --- |
| cobertura por nível | tarefa de preparo (§4.2) | calibrar o nível: fino demais deixa a maioria sozinha |
| precisão da regra no ouro | proporção de "mesmo golpe" na camada 1 e de "mesmo ou parecido" na camada 2, por nível | escolher o nível padrão e a base de comparação |
| recall@10 em assinaturas nunca vistas | dos 10 vizinhos da rede, quantos têm a mesma assinatura (teste *held-out*) | a rede aprendeu a regra e generaliza |
| F1 por tema, erro médio do rating | cabeças auxiliares no teste | sanidade do vetor |
| precisão@5 da rede no ouro | "mesmo ou parecido" nos 5 primeiros da camada 3 | o portão |

**Portão:** a camada 3 entra no produto se a precisão@5 dela no ouro for maior
que a da camada 2 por, no mínimo, 10 pontos, **e** se, nos casos em que a camada
1 tem menos de 5 irmãos (onde a regra não chega), ao menos 70 % do que a rede
completa for "mesmo ou parecido". Senão fica fora, com o resultado registrado.

Relatório em `docs/golpes-eval.md`: cobertura, métricas automáticas, métricas no
ouro, decisão e data.

## 10. Testes

- Assinatura: posições conhecidas (francesa 9.Bb5+, beijo grego, mate sufocado,
  garfo com xeque, promoção, en passant); cores trocadas dão a mesma assinatura;
  espelho dá `destinos_esp`; detecção de descoberta e de ataques testada
  isolada; níveis e hashes estáveis; trechos (§3.5): posição relativa
  (`inteira`/`inicio`/`meio`/`fim`), rei na casa de quando o trecho começa,
  cores trocadas, limite de `max_solver`.
- Busca: conjunto pequeno em memória cobrindo a cascata em degraus (§5), o
  casamento por trecho (início, fim e meio da solução do candidato), o
  esqueleto de um lance nunca combinando, `espelho-trecho1` fora do bloco, a
  faixa de rating, a exclusão de vistos e salvos, o espalhamento do fácil ao
  difícil.
- Tarefa: lotes, versão antiga refeita, cancelar e retomar, cobertura gravada.
- API e interface: rotas de irmãos e imagem, `sibling_of` no salvamento, cartão
  de resultado (erro com botão, acerto só imagem, sem irmãos nada), bloco com
  lista fixa e resumo, recurso desligado.
- Modelo: codificador de planos (forma, simetria da normalização), conjunto de
  dados num fixture minúsculo, treino de fumaça de poucos passos em CPU com rede
  pequena, exportação ONNX igual ao PyTorch, avaliação com ouro sintético.

## 11. Ordem de construção

Cada passo é utilizável sozinho.

Passos 1 a 4 implementados em 2026-09-17 (plano `docs/superpowers/plans/2026-09-16-golpes-fase-a.md`).
Trechos (§3.5, §5, §8) — busca por pedaço da solução, com procedência em cada
irmão e placar por procedência no julgamento — implementados em 2026-09-17,
dentro do passo 4. Voto no bloco (§8, revisão de 2026-09-18) substituiu a tela
de rotulagem separada pelo botão de voto no resultado. Etiquetas próprias de
padrão de mate (§3.6.1, §4.2, §5, §8) — o corredor apertado, a tabela
`lichess_puzzle_padroes`, a passada leve na tarefa de preparo e a procedência
`:lichess`/`:regra` no degrau `padrao-mate` — implementadas em 2026-09-19.

1. Assinatura, tarefa de preparo, cobertura.
2. Rota de irmãos, imagem, cartão de resultado.
3. Bloco de N e entrada na repetição espaçada com `sibling_of`.
4. Voto no bloco, exportação do ouro, primeira calibração do nível com o
   usuário.
5. Preparo dos dados e scripts de treino; treino executado pelo usuário.
6. Avaliação automática e no ouro, relatório, decisão.
7. Exportação ONNX, índice vetorial, camada 3 atrás do portão.

## 12. Fora deste spec

- Modelo de linguagem em qualquer ponto; treino por usuário.
- **Perfil agregado** dos golpes do usuário e fila dirigida por ele: spec própria
  depois que `sibling_of` tiver dados.
- **Preparar o golpe**: voltar alguns lances antes do puzzle, o adversário joga
  o que jogou na partida real, o usuário tem de chegar ao golpe. Tem de valer
  para os irmãos do Lichess, não só para os exercícios próprios, porque a queixa
  é não chegar às posições dos puzzles. Exige guardar o link da partida na
  importação do Lichess e buscar a partida na API dele (uma por puzzle, com
  cache). Regra de "chegou" a definir (reproduzir a partida, ou qualquer lance
  equivalente pela engine que mantenha o golpe). Spec própria.
- Espelhamento além da troca de flancos; assinaturas específicas de finais.
