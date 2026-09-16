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
| descoberta | peças adversárias (exceto o rei) que passam a ser atacadas por **outras** peças do solucionador por causa do lance: tipo e casa, as duas mais valiosas |
| ataques | peças adversárias (exceto o rei) que passam a ser atacadas pela **própria** peça que moveu: tipo e casa, as duas mais valiosas |

Mais a casa do rei adversário na posição do puzzle. As respostas do adversário
não entram: são o que varia entre puzzles do mesmo golpe.

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
| completo | destinos mais a casa de origem | depuração e rotulagem; fino demais para treino |

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

## 4. Dados e tarefa de preparo

### 4.1 Tabelas

- `lichess_puzzle_signatures`: `puzzle_id` (PK, FK), `versao`, `esqueleto`,
  `destinos`, `destinos_esp`, `completo` (inteiros), `texto_completo`,
  `zona_rei`, `n_lances`. Índices em `destinos`, `destinos_esp`,
  `(esqueleto, zona_rei)`.
- `puzzle_signatures`: o mesmo para os exercícios próprios (`puzzles`).
  Calculada quando o exercício é criado e refeita quando a versão muda.
- `puzzles.sibling_of` (texto, nulo, FK `puzzles.id`): o exercício de origem de
  um irmão salvo pelo bloco (§6). É o vínculo que o perfil futuro usa.
- `golpe_labels` (§8).
- Fase B: `lichess_puzzle_vectors` e `puzzle_vectors` (§7).

### 4.2 Tarefa "Preparar golpes"

- Botão em Configurações, no executor de tarefas existente (`JobRunner`), com
  progresso e cancelamento. Percorre `lichess_puzzles` em lotes de 5 000,
  calcula só as linhas sem assinatura ou com versão antiga, grava por lote.
  Cancelar e retomar continua de onde parou.
- No fim, grava em `settings` a **cobertura** por nível: quantos puzzles têm
  grupo de tamanho ≥ 5, ≥ 2 e 1 (sozinhos). É o primeiro número da calibração
  (§8) e aparece na tela de dev.
- Estimativa: dez minutos na primeira vez (reprodução de três a seis lances por
  puzzle no python-chess). O banco cresce uns 60 MB.

## 5. Busca de irmãos (`core/golpes/service.py`)

`irmaos(db, âncora, faixa_de_rating, excluir, k=5)` devolve até k puzzles do
Lichess, cada um com a **camada** de onde veio, em cascata (*fallback tiers*):

1. **mesmo golpe**: `destinos` igual ao da âncora;
2. **parecido por regra**: `destinos` igual ao `destinos_esp` da âncora
   (espelho), depois `esqueleto` e `zona_rei` iguais;
3. **parecido pela rede** (fase B): vizinhos por cosseno no índice vetorial,
   fora dos que as camadas anteriores já deram.

Em cada camada: rating dentro da faixa do usuário (a mesma janela que a sessão
de táticas já usa), `popularity ≥ 50` e `nb_plays ≥ 50` para evitar puzzles
ruins, excluídos os já vistos (`tactics_attempts`), os já salvos na fila e a
própria âncora. Dentro da camada os candidatos são ordenados por rating e o
bloco pega k deles espalhados ao longo da faixa, para ir **do fácil ao
difícil**. A resposta traz, por item, `tier`, rating e os campos do puzzle; e a
assinatura da âncora em texto.

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
  `sibling_of` apontando para a âncora. A partir daí é revisado como qualquer
  exercício, misturado e espaçado.
- **Configurações**: `golpes_enabled` (padrão ligado) e `golpes_bloco` (padrão
  5, de 3 a 10).

### 6.1 Imagem do golpe

Rota `GET /api/golpes/{origem}/{id}/imagem.svg` (`origem` = `own | lichess`):
o servidor desenha o tabuleiro com `chess.svg`, solucionador embaixo, os lances
do solucionador em setas verdes, descobertas e ataques em setas vermelhas, casa
do rei adversário e casas de destino marcadas. Estática, cacheável, serve no
cartão e, mais adiante, para salvar ou compartilhar.

### 6.2 API

- `GET /api/golpes/{origem}/{id}/irmaos?k=5` → `{assinatura, itens: [{tier,
  puzzle...}]}`; 404 sem assinatura ou com o recurso desligado.
- `GET /api/golpes/{origem}/{id}/imagem.svg`.
- `POST /api/tactics/{lichess_id}/save` ganha `sibling_of` opcional.
- `POST /api/golpes/preparar` dispara a tarefa; o status vem pelo executor.
- Rotas de rotulagem (§8) só com `CHESS_TRAINER_ROTULAGEM=1`.

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

## 8. Rotulagem e conjunto de ouro (só em dev)

- Tela `/rotulagem`, atrás de `CHESS_TRAINER_ROTULAGEM=1`: uma âncora (exercício
  próprio ou puzzle do Lichess) com a imagem do golpe, e candidatos das camadas
  todas embaralhados, sem dizer a origem. Para cada candidato, uma de três
  respostas: **mesmo golpe**, **parecido**, **nada a ver**.
- `golpe_labels`: `id`, `anchor_origem`, `anchor_id`, `candidate_id`,
  `tier_na_hora`, `versao_assinatura`, `label`, `created_at`. Exportado por
  comando para `ml/golpes/gold/<data>.jsonl`, versionado no repositório.
- Meta: ~300 julgamentos nas primeiras sessões. Com a rede treinada, a tela
  passa a priorizar os pares em que regra e rede discordam (**aprendizado
  ativo**), onde cada resposta vale mais.

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
  isolada; níveis e hashes estáveis.
- Busca: conjunto pequeno em memória cobrindo a cascata, a faixa de rating, a
  exclusão de vistos e salvos, o espalhamento do fácil ao difícil.
- Tarefa: lotes, versão antiga refeita, cancelar e retomar, cobertura gravada.
- API e interface: rotas de irmãos e imagem, `sibling_of` no salvamento, cartão
  de resultado (erro com botão, acerto só imagem, sem irmãos nada), bloco com
  lista fixa e resumo, recurso desligado.
- Modelo: codificador de planos (forma, simetria da normalização), conjunto de
  dados num fixture minúsculo, treino de fumaça de poucos passos em CPU com rede
  pequena, exportação ONNX igual ao PyTorch, avaliação com ouro sintético.

## 11. Ordem de construção

Cada passo é utilizável sozinho.

1. Assinatura, tarefa de preparo, cobertura.
2. Rota de irmãos, imagem, cartão de resultado.
3. Bloco de N e entrada na repetição espaçada com `sibling_of`.
4. Tela de rotulagem, exportação do ouro, primeira calibração do nível com o
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
