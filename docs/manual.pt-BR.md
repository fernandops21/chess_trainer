# Chess Trainer — manual (português)

> **Status: projeto pessoal, em desenvolvimento e em testes.** Uso este app todo dia para treinar, mas ele
> muda com frequência, não tem garantias, não tem contas de usuário e foi feito para rodar localmente,
> na máquina de uma pessoa só. Está público para quem quiser ver o código ou usar por conta própria.

Treino de xadrez a partir dos seus próprios erros: importa partidas do chess.com, analisa com Stockfish,
gera puzzles dos erros (seus e do adversário) e agenda com repetição espaçada. Também importa estudos do
Lichess e arquivos PGN, deixa criar estudos com um editor de variações e comentários, e treina táticas
do banco público do Lichess. "Chessable, mas o curso é você mesmo."

Licença: AGPL-3.0 (ver `LICENSE` na raiz). O tabuleiro (chessground) é GPL-3.0 e os sons vêm do Lichess
(AGPL-3.0). Os estudos, partidas e livros que você importa são seus: o app não distribui conteúdo de
terceiros.

## Rodar

    cd frontend && npm install && npm run build
    cd ../backend && uv sync && uv run python -m chess_trainer

Abra http://127.0.0.1:8000 (ou, no celular na mesma rede, o endereço mostrado em Configurações).
Stockfish: ver backend/README.md.

Tabuleiro de análise livre (`/analise`, com avaliação do Stockfish no backend): pelo item "Análise" do
menu, pelo link "Explorar" no resultado do treino (abre em nova aba, para não perder a sessão em
andamento), pelo botão "Explorar daqui" na partida e pelo botão "Explorar" na revisão de erros. É
também por ali que se começa um capítulo de estudo (ver "Criar estudos aqui").

### Rodar com Docker

`docker compose up -d` sobe o app em http://localhost:8000 (com o Stockfish dentro da imagem e o
banco em `backend/data`) e o LangFuse em http://localhost:3000. Copie `.env.example` para `.env` e
troque os segredos antes. Para desenvolvimento, `uv run` e `npm run dev` continuam valendo.

## Táticas do Lichess

Além dos puzzles dos seus erros, dá para treinar com o banco público de táticas do Lichess
(https://database.lichess.org/#puzzles, licença CC0 — domínio público). São posições tiradas de partidas
reais, cada uma com rating, temas e a sequência de lances da solução.

Como importar: **Configurações → Banco de táticas (Lichess) → "Baixar e importar"**. O app baixa
~300 MB de database.lichess.org, guarda o arquivo em `backend/data/lichess_db_puzzle.csv.zst` e importa
só o que passa no filtro. O processo todo leva uns 5 minutos; o andamento aparece no cartão "Tarefas" do
Painel e pode ser cancelado (para no fim do lote atual, mantendo o que já entrou).

Filtro (em Configurações, vale só para a próxima importação):

- **Mínimo de partidas jogadas** (padrão 2000) e **Popularidade mínima** (padrão 90, escala de −100 a 100):
  descartam táticas pouco jogadas ou mal avaliadas. Com o padrão sobra cerca de 1 milhão de táticas.

Rating: você começa no **Rating inicial de táticas** (padrão 1200) e ele sobe ou desce a cada tática
resolvida, comparado ao rating da própria tática (Elo). O sorteio pega táticas dentro da **Janela de
rating (±)** (padrão 150) em volta do seu rating. Para treinar: botão "Treinar táticas" no Painel, ou
Treinar → fonte "Táticas do Lichess", onde dá para filtrar por tema. O Painel mostra o acerto por tema
dos últimos 30 dias e qual tema está mais fraco.

## Estudos do Lichess

Um estudo do Lichess é uma coleção de capítulos (posições comentadas pelo autor). Capítulos no modo
**gamebook** ("Estudo → capítulo → modo Gamebook", em que o autor define a sequência certa e comenta os
lances) viram exercícios da repetição espaçada; os outros capítulos entram como **leitura**, sem
exercício.

O app baixa o PGN pela API pública do Lichess, então só funciona com **estudos públicos**. Para um
estudo privado (ou seu), exporte o PGN no Lichess (menu do estudo → "Export → Study PGN") e cole o
texto no app.

Como importar: **Estudos → "Importar"**, cole o endereço (`lichess.org/study/<id>`, com ou
sem o capítulo no fim) e clique em "Importar"; ou clique em "colar PGN" e cole o PGN exportado. A
importação roda em segundo plano e o andamento ("2/5 capítulos") aparece no cartão "Tarefas". Ao
terminar, a mensagem diz quantos capítulos e exercícios entraram e quais foram pulados (capítulo com
lance ilegal, por exemplo).

### Quem joga no exercício

Nem sempre o aluno é o lado a jogar na posição inicial do capítulo: é comum o autor abrir com um lance
do adversário e deixar o exercício a partir do segundo. Na hora de montar o exercício o app decide de
quem ele é seguindo quatro regras, nesta ordem, e a primeira que decidir vence. Primeiro o **texto do
autor** — o enunciado ou o comentário do primeiro lance —, quando diz "Jogam as pretas", "Brancas
jogam", "White to move" e afins (maiúsculas e acentos não importam). Depois o **resultado** do capítulo
(`[Result]`): `1-0` é exercício das brancas e `0-1` das pretas, enquanto `1/2-1/2` e `*` não decidem
nada. Depois o lado que joga o **último lance** da linha principal, porque o autor costuma parar logo
depois do lance do aluno. E, sem nenhum sinal, vale o **lado a jogar na FEN**. Quando o aluno não é o
lado a jogar, o primeiro lance da linha vira a introdução: o exercício abre na posição do capítulo,
anima o lance do adversário e só então libera as peças — igual às táticas do Lichess. Reimportar (ou
salvar o capítulo no editor) corrige exercícios que entraram com os lados trocados, sem perder o
histórico da repetição.

### Importar um arquivo PGN

No mesmo cartão "Importar" há o campo **"Arquivo PGN"**: escolha um arquivo `.pgn` do computador e ele
vira um estudo com **um capítulo por partida**. Serve para coleções de partidas — livros comprados em
PGN, bases exportadas de outro programa —, não só para estudos do Lichess.

Os nomes saem dos headers de cada partida: o título do estudo é o nome do arquivo (sem a extensão) e
cada capítulo vira `"Kasparov, Garry × Karpov, Anatoly (Linares, 1993)"`, com o torneio e o ano que
houver. Sem os jogadores fica o torneio; sem nada, "Capítulo 1", "Capítulo 2"… Partidas inteiras
entram como **leitura**; uma partida que comece de uma posição própria e tenha linha curta vira
exercício, como já acontece nos capítulos comuns de um estudo.

Na lista, cada estudo mostra autor, quantos capítulos, quantos exercícios estão na repetição e quantos
venceram hoje, com os botões:

- **Treinar este estudo** — abre Treinar já filtrado só por esse estudo.
- **Reimportar** — busca de novo o PGN no Lichess (só para estudos vindos por URL). Títulos, nomes e
  linhas são atualizados sem perder o histórico dos exercícios; capítulos que sumiram do estudo saem da
  repetição em vez de serem apagados.
- **Tirar da repetição / Voltar para a repetição** — liga e desliga todos os capítulos do estudo de uma
  vez, sem apagar nada.
- **Remover** — apaga o estudo, os capítulos, os exercícios e o histórico deles (pede confirmação).

Clicando no título abre o detalhe: capítulos em ordem, com o enunciado do autor, a etiqueta do modo,
"Treinar este" (capítulos com exercício e na repetição) e "ver no Lichess".

Estudo importado também se edita aqui: "Editar" num capítulo abre o mesmo editor dos estudos feitos no
app, e dá para acrescentar variações, comentar, renomear e reordenar capítulos. O detalhe do estudo
avisa que **reimportar sobrescreve** essas edições — o PGN do Lichess volta a mandar. Para não perder
o que você escreveu, exporte o PGN antes de reimportar (ou deixe o estudo importado quieto e trabalhe
numa cópia feita aqui).

## Criar estudos aqui

Além de importar, dá para escrever estudos no próprio app.

O começo é sempre uma posição num tabuleiro editável: a tela **Análise** (`/analise`), aberta em branco
ou já numa posição vinda de uma partida ou de um erro. Ali você joga os lances, olha a avaliação do
Stockfish e, quando a linha está do jeito que quer, clica em **"Salvar como capítulo"** — o modal
pergunta se é um estudo que já existe ou um novo (título e autor, este já preenchido com o nome
configurado) e abre o editor do capítulo. O caminho mais direto também serve: **Estudos → "Novo
estudo"** e depois **"Novo capítulo"** (posição padrão ou uma FEN colada).

O editor do capítulo (`/estudos/:id/capitulos/:cid/editar`) tem, no cabeçalho, nome, **modo**
(exercício ou leitura), **orientação** do tabuleiro e o **enunciado** (o comentário da posição
inicial); ao lado do tabuleiro ficam a avaliação do motor e a **árvore de lances** no formato do
Lichess — linha principal corrida e variações recuadas entre parênteses. No editor você pode:

- **jogar lances** no tabuleiro para criar a linha; um lance que já existe só navega até ele;
- **comentar** o lance atual na caixa embaixo do tabuleiro (na posição inicial ela é o enunciado);
- **marcar a qualidade do lance** com NAGs (`!`, `?`, `!!`, `??`, `!?`, `?!`), promover uma variação a
  linha principal ou apagar dali para a frente — tudo no menu que abre com o botão direito (ou o toque
  longo, no celular) em cima do lance na árvore;
- **desenhar setas e casas** com o botão direito no tabuleiro: elas ficam salvas naquele lance e
  aparecem para quem lê o capítulo depois;
- aproveitar o motor: cada linha sugerida tem **"adicionar como variação"**, que entra com a sequência
  inteira a partir do lance atual.

Lances escritos no comentário viram links: clique para ver a posição no tabuleiro (a faixa "prévia"
acima dele traz o "voltar"); no editor, os lances do comentário aparecem embaixo da caixa e a prévia
ganha um **"adicionar como variação"**, que entra com a linha inteira na árvore. Quem lê o capítulo
tem os mesmos links nos comentários e no enunciado.

**Modo livro.** Na leitura do capítulo (`Ver como leitura`) cada lance é uma página, como no
Chessable: a coluna da direita mostra só o comentário do lance atual, inteiro e em fonte de leitura
(na posição inicial, o enunciado), e a lista de todos os lances fica embaixo do tabuleiro, compacta,
com uma marca nos lances que têm comentário. As setas ◀ ▶ (ou do teclado) viram a página.

Atalhos: **←** e **→** andam na linha, **↑** e **↓** trocam de variação, **Home** volta à posição
inicial e **Ctrl+S** salva (o botão "Salvar" fica embaixo do tabuleiro). O cabeçalho mostra o estado
("alterações não salvas" / "salvo às HH:MM"). Com pendências, os links da própria tela ("Voltar ao
estudo" e "Ver como leitura") pedem confirmação, e fechar ou recarregar a aba também — o menu lateral
não pergunta nada, então salve antes de sair por ele.

Capítulo no modo **exercício** vira um puzzle da repetição espaçada, com a linha principal como
solução; no modo **leitura** ele fica só para ler, sem exercício. Trocar o modo e salvar de novo tira
ou devolve o exercício sem perder o histórico dele.

Cada capítulo tem também:

- **Ver como leitura** — a mesma árvore sem edição, com os comentários e as marcações do autor
  aparecendo conforme se navega. É como o capítulo vai ser lido.
- **Exportar PGN** (do capítulo ou do estudo inteiro) — o arquivo sai no formato que o Lichess importa
  ("Estudo → Import PGN" lá), com os comentários, as setas, os NAGs e a orientação.
- **Duplicar** — a cópia entra logo depois, como **leitura**: dois exercícios de estudo não podem
  partir da mesma posição inicial. Mude a posição (ou a linha) da cópia e escolha "exercício" ao salvar.
- **Apagar** — leva junto o exercício e o histórico dele; pede confirmação.

Limites por capítulo: **2 000 lances** na árvore e **4 000 caracteres** por comentário. O servidor
confere ainda a FEN e a legalidade de cada lance; o que não passar volta como uma lista de mensagens
em português, em cima da tela do editor.

**Ida e volta pelo PGN.** O PGN do **estudo inteiro** leva um header próprio com o id do estudo
(`[ChessTrainerStudy "…"]`). Colar esse texto de volta em **Estudos → Importar → PGN** atualiza o
estudo que o gerou em vez de criar uma cópia, e o exercício e o histórico da repetição espaçada de
cada capítulo continuam de pé. Os capítulos que têm `ChapterURL` (os que vieram do Lichess) casam
pela URL; os que não têm casam pelo nome e, se o nome mudou, pela posição no arquivo — só renomear
**e** reordenar o mesmo capítulo na mesma volta faz dele um capítulo novo. Serve para editar o
estudo fora do app (num editor de texto, no Lichess) e trazer de volta, ou para levar o estudo para
outra máquina — lá o id não existe ainda e o PGN entra como estudo novo.

O PGN de **um capítulo** sai sem esse header, de propósito: colado de volta ele vira um estudo novo,
sem mexer no estudo de origem. Se ele casasse o estudo inteiro pelo id, todos os capítulos que não
estivessem no texto colado sairiam da repetição.

## Livro de aberturas

No tabuleiro de análise, o painel da direita tem duas abas: **Engine** e **Aberturas**. A aba
Aberturas mostra, para a posição na tela, o que já foi jogado dali: cada lance com o número de
partidas, uma barra com a fatia de vitórias das brancas, empates e vitórias das pretas, e o rating
médio quando a base informa. Clicar num lance joga ele no tabuleiro, como as linhas do motor. Quando
a posição tem nome, ele aparece em cima ("C50 · Italian Game"); quando ninguém jogou dali, o painel
diz "Sem partidas nesta posição."

Há duas bases, no seletor do painel (a escolha fica guardada):

- **Mestres** — partidas de torneio de jogadores titulados.
- **Jogadores (Lichess)** — partidas de rapid e clássico do Lichess, com rating a partir de 1600.

Os dados vêm do explorador do Lichess, que pede um **token pessoal**. Crie um em
<https://lichess.org/account/oauth/token> **sem marcar nenhuma permissão** e cole em
**Configurações → Livro de aberturas (Lichess)**. O token fica só no banco local desta instalação:
ele nunca aparece de volta na tela nem nas respostas da API (Configurações só mostra "token
configurado", com um botão "Remover"). Sem token, a aba Aberturas mostra o aviso com o atalho para
Configurações.

As consultas ficam em cache por 24 horas, então voltar a uma posição já vista não chama o Lichess de
novo. Se o limite do serviço estourar, o painel avisa para tentar em instantes.

## Classificação de lances

Na Análise, cada lance do caminho aberto (da posição inicial até o lance na tela) ganha um selo no
estilo do chess.com, calculado pela engine local: **livro** 📖, **brilhante** `!!`, **ótimo** `!`,
**melhor** `★`, **excelente** `✓`, **bom** `·`, **imprecisão** `?!`, **erro** `?` e **blunder** `??`.
O selo aparece colado ao lance na árvore (com o nome em português no `title`) e, para o lance da
posição na tela, também num círculo colorido sobre a casa de destino, no tabuleiro. O cabeçalho do
painel da engine mostra a linha "lance: melhor (−0.12)" com o quanto o lance perdeu.

Como a conta é feita: para cada lance, a engine analisa a posição de onde ele parte e a posição a que
ele leva; a perda é a diferença entre a melhor avaliação dali e a avaliação depois do lance. "Melhor"
é o lance que a engine escolheria; "ótimo" é o melhor quando ele é a única boa jogada; "brilhante" é o
melhor quando ele sacrifica material e a posição continua de pé (ou o mate dado com menos material
que o adversário). Os limiares de **imprecisão** e **erro** são os mesmos de Configurações (`mistake`
e `blunder`); acima do de blunder o lance vira blunder. Lance que está na base de mestres é **livro**
e não é medido.

Só o caminho atual é classificado (os 60 últimos meios-lances, de modo que o lance na tela nunca fica
de fora) e cada posição é analisada uma única vez — o resultado fica em cache enquanto a posição
estiver em uso, mais os 5 minutos de folga do React Query —, então navegar pela árvore não repete
trabalho. As marcações `!`/`?` do autor do estudo (NAGs) continuam como eram: são outra coisa.

Dá para desligar tudo em **Configurações → Engine → "Classificar lances na Análise (usa a engine)"**;
desligado, a engine só analisa a posição na tela.

## Modos de treino

A tela **Revisar** (item do menu, `/revisar`) não tem escolha nenhuma: entra direto na fila de
vencidos, de todas as fontes, sem filtro e sem tempo planejado — vai até a fila acabar. É o modo do
dia a dia, e o número no badge do menu ao lado de "Revisar" é exatamente essa fila (os vencidos de
hoje na repetição espaçada). Fila vazia, a tela oferece **Fazer novos** e **Estudos**.

A tela **Treinar** é a das sessões com escolha — modo (ou estudo), filtros e tempo:

- **Repetição espaçada** — só exercícios que você já revisou ao menos uma vez e que venceram.
  Os mais atrasados vêm primeiro; os do mesmo dia vêm embaralhados. Nada de estreia aqui: um
  exercício nunca revisado não aparece nesse modo. Os filtros de fonte, tipo, cor e categoria valem.
  Com algum filtro marcado a tela mostra `N vencido(s) com estes filtros · M no total`: assim dá
  para ver na hora quanto o filtro corta em relação ao badge do menu. Os filtros não ficam
  guardados — cada sessão começa sem nenhum, para um filtro esquecido não esconder vencidos.
- **Novos (meus erros)** — a primeira vez dos exercícios das suas partidas, até o limite diário
  (**Configurações → puzzles novos por dia**). A ordem vem de **Configurações → Ordem dos novos**:
  *aleatória* (padrão) ou *mais recentes primeiro* (a partida mais nova antes). Num dia em que dá
  vontade de fazer mais, marque **"ignorar o limite diário hoje"**: a fila vem com todos os novos
  que houver, sem descontar o que já foi feito. A marca vale só para aquela sessão — ela não fica
  guardada e não mexe no limite das Configurações.
- **Táticas do Lichess** — sessão do banco de táticas, sorteada perto do seu rating. Ao guardar uma
  tática ("Guardar para repetir"), ela entra na repetição já agendada com o resultado da tentativa.
- **Treinar este estudo** — escolha um estudo no seletor (ou use o botão nas telas de Estudos): todos
  os exercícios do estudo, feitos ou não, na ordem dos capítulos e sem limite diário.

No Painel, **Revisar (N)** abre a tela Revisar com os N vencidos e **Fazer novos** abre a estreia dos
seus erros. `?mode=review|new|study` e `?study=<id>` no endereço já chegam com a escolha feita, e a
última escolha de modo fica guardada para a próxima sessão.

Cada exercício tem um **código curto** — o começo do identificador dele, mostrado como `#ff466803`
no cabeçalho do treino, no cartão do resultado, na revisão de erros e no resumo da sessão. Clicar na
etiqueta copia o identificador inteiro. Para voltar a um exercício anotado, use **abrir por código**
na tela Treinar (o `#` pode ficar ou sair) ou ponha o código direto no endereço,
`/treinar?puzzle=ff466803`. No caso improvável de dois exercícios começarem igual, o app avisa em vez
de abrir um deles ao acaso — aí vale o identificador inteiro.

Sair da tela no meio de uma sessão (trocar de menu, voltar no navegador) ou fechar a aba encerra a
sessão no servidor: ela não fica aberta contando tempo que ninguém treinou.

Durante o exercício, os botões **⏮ ◀ ▶ ⏭** embaixo do tabuleiro (e as setas **←**/**→**, com
**Home**/**End** para os extremos) andam pelo histórico da posição: dá para voltar e rever o lance do
adversário que abriu o exercício, ou os lances já jogados na sessão. Voltar é só olhar — o tabuleiro
não aceita lances até o **voltar ao lance atual**.

### Resultado do exercício

Depois de resolver (ou de errar), o painel de resultado não é uma imagem parada: ele é o mesmo
tabuleiro de análise da tela `/analise`, já na última posição da solução. Ali dá para:

- **navegar a solução** pelos lances da lista, pelo teclado (setas) ou pelos botões;
- **jogar variantes** no tabuleiro a partir de qualquer posição — os lances entram como variação e
  o som do lance toca a cada um;
- abrir a **Análise completa** no link **Explorar**, que leva a posição do exercício para `/analise`
  numa aba nova (com engine, livro de aberturas e classificação dos lances);
- nos exercícios de **evitar** (o erro foi seu), ver o cartão "Meu erro": a posição da partida com o
  seu lance ruim destacado, a avaliação de antes e depois e os atalhos para a partida e para a
  revisão de erros;
- nos exercícios de **punir** (o erro foi do adversário), ver o cartão "Na partida": a posição do
  exercício com a sua resposta destacada e o texto "Você respondeu X … e deixou passar Y" quando na
  partida você não achou o lance, ou "Você achou Y na partida" quando achou.

No "evitar", o lance que você jogou na partida aparece como variação da posição do exercício, com a
continuação que o punia.

Acima e abaixo do tabuleiro (no treino e na análise) ficam as barras de material capturado — as
peças que cada lado tomou e o `+N` de quem está na frente —, e em tela larga o painel da engine
sai de baixo dos cartões de resultado e fica ao lado deles.

### Refutação do lance errado

Ao jogar um lance que não é a solução, o lance entra no tabuleiro, a engine responde com a melhor
réplica e o app explica por que não serve: `h3? Qg2 — avaliação cai de +9.00 para -5.00` (com a
continuação e, nos estudos, o comentário do autor para aquele lance errado). O botão **Tentar de
novo** desfaz tudo e devolve a posição do exercício. A tentativa continua contando como erro.

Os lances escritos na mensagem (o lance errado, a réplica e a continuação) são links: clicar mostra
a posição no tabuleiro, e a faixa "prévia" traz o "voltar". O mesmo vale para o comentário do autor
no "Certo! — …" dos estudos.

Ligue ou desligue em **Configurações → Refutar o lance errado com a engine** (ligado por padrão).
Desligada — ou sem Stockfish disponível — a tentativa é só recusada, como antes.

## Golpes

Errar um exercício ensina pouco sozinho: o que fixa uma ideia é repetir o mesmo golpe (a mesma
combinação de peças, casas e capturas) em outras posições, várias vezes seguidas. Para isso o app
calcula uma **assinatura** de cada puzzle — a geometria da solução: quais peças jogam, para onde,
o que capturam, os xeques e o que fica atacado ou descoberto — e usa ela para achar **irmãos**:
outros puzzles do banco de táticas do Lichess com o mesmo golpe.

Antes de usar, prepare a base em **Configurações → Golpes → "Preparar golpes"**: a tarefa calcula
a assinatura (e os trechos dela) de todos os puzzles do banco de táticas (precisa dele já
importado — ver "Táticas do Lichess"), leva uns quinze minutos na primeira vez, aparece no cartão
"Tarefas" do Painel e pode ser cancelada e retomada de onde parou. Terminada, a linha abaixo do
botão mostra quantos puzzles ficaram com assinatura, quantos têm cinco ou mais irmãos e quantos
trechos foram calculados ("N de M puzzles com assinatura · K com cinco ou mais irmãos · T
trechos"). Depois de atualizar o app para esta versão, rode "Preparar golpes" de novo: os puzzles
já assinados ganham os trechos que ainda não tinham.

Na tela de resultado de um exercício — dos seus próprios ou de uma tática do Lichess — aparece o
cartão **"Repetir o golpe"** com a imagem do golpe desenhada no tabuleiro: setas verdes para os
lances do solucionador, setas vermelhas para o que eles descobrem ou atacam. Quando você **erra**,
o cartão traz o botão **"Treinar N parecidos"**, que abre um bloco de N puzzles do Lichess com o
mesmo golpe, do mais fácil ao mais difícil. Um irmão pode compartilhar a combinação inteira ou só
um trecho dela — o lance de abertura do golpe, o golpe final, ou um pedaço do meio — e, faltando
ainda, o espelhado (a mesma ideia do outro lado do tabuleiro) ou o mesmo esqueleto com o rei
adversário na mesma zona. Cada puzzle do bloco que você tenta — acerte ou erre — entra na sua fila
de repetição espaçada, junto com os outros exercícios.

Os irmãos são procurados em qualquer rating — quem decide se é "o mesmo golpe" é a geometria da
solução, não a dificuldade. O rating só escolhe **quais** aparecem no bloco: a faixa preferida vai
do seu rating de táticas para cima, com **"Faixa do bloco: pontos abaixo do meu rating"** (padrão
100) e **"Faixa do bloco: pontos acima do meu rating"** (padrão 500), ambas em
**Configurações → Golpes**. Faltando irmãos dentro da faixa, o bloco completa com os mais
próximos de fora dela.

Em **Configurações → Golpes** dá para desligar o cartão ("Mostrar 'Repetir o golpe' no resultado
dos exercícios") e ajustar o tamanho do bloco em **"Irmãos por bloco"** (de 3 a 10, padrão 5).

Ao final de cada irmão do bloco, depois de resolver, um cartão pergunta **"Tem a ver com o seu
erro?"** com três respostas — mesmo golpe, parecido, nada a ver. Votar é opcional ("Próximo"
funciona sem votar) e alimenta um conjunto de referência que hoje calibra a assinatura e, mais
adiante, serve para avaliar um modelo de semelhança aprendido. O placar por procedência aparece em
**Configurações → Golpes → "Votos por procedência"**, e o conjunto se exporta com
`uv run python -m chess_trainer.core.golpes.exportar_ouro`, rodado em `backend/`.

## Treinador (IA)

Em desenvolvimento: vem desligado; para experimentar, inicie o servidor com `CHESS_TRAINER_COACH=1`.
O treinador ainda não está no nível do resto do app: desligado, nem o botão **Explicar** nem a seção
**Treinador (IA)** das Configurações aparecem.

Na tela de resultado de um exercício, o botão **Explicar** pede a um treinador com IA que escreva,
em português, o que aconteceu na partida, por que o lance perde, qual é o padrão, onde ele aparece
nos seus estudos e o que treinar. O treinador é um agente: consulta o Stockfish, o contexto da
partida, as suas estatísticas por tema e busca nos comentários dos capítulos dos seus estudos.

A resposta vem em quatro blocos curtos, para ler de um olhar: **Na partida** (uma ou duas frases sobre
o lance errado e o que você jogou), **Por que** (a ideia e a linha principal), **Padrão** (o nome do
padrão por trás, em duas a cinco palavras) e **Treinar** (de uma a três ações). Em tela larga o
tabuleiro fica parado enquanto o texto rola ao lado: a posição não sai da vista na hora em que a
explicação cita um lance.

Antes de mostrar o texto, a engine confere a explicação: reproduz cada linha citada no tabuleiro,
vê se o primeiro lance está entre os três melhores, compara as avaliações e confirma que cada
citação existe. A explicação só aparece quando passa nessa verificação — daí o selo **verificado
pela engine** ao lado do título; quando não passa, o app diz isso no lugar do texto e oferece
**Explicar de novo**.

Afirmação tática não sai da cabeça do modelo: ele consulta os **fatos da posição**, calculados lance
por lance sem engine — as casas do rei, os xeques, os mates em um, as capturas de peças sem defesa e o
que o adversário faria se fosse a vez dele. O treinador enxerga as ameaças analisando a posição como
se você passasse a vez: as melhores linhas do adversário ali são exatamente o que ele faria se você
jogasse um lance calmo, e é assim que a explicação nomeia todas as ameaças (o mate e o ganho de
material), não só a maior. O treinador explica também por que a defesa natural falha: o lance que você
jogaria ali (o seu lance real, quando a partida tem um) é seguido até onde o material muda, para ficar
claro o que se perde nele. Do outro lado, a verificação da engine cobre também o que está
escrito na prosa: mate anunciado que não é mate, xeque que não dá xeque ou lance que não existe em
nenhuma posição da explicação a reprovam, e nome de casa no meio da frase (o rei em h1, a torre em
g3) deixou de ser confundido com lance.

Os lances do texto são links (prévia no tabuleiro) e as citações abrem o capítulo no modo livro, no
lance certo. O rodapé mostra o modelo, o custo em dólares, o tempo, o aviso de índice vazio quando
for o caso e o botão **Explicar de novo**.

### Configurar

Em **Configurações → Treinador (IA)**: cole a chave da API da Anthropic (crie no Console e defina lá
um teto de gasto; cada explicação custa alguns centavos de dólar), escolha o modelo (Opus 5 ou
Sonnet 5) e o esforço. A chave fica só no seu banco e nunca sai pela API do app. O verificador
precisa do Stockfish: sem a engine configurada, o **Explicar** recusa na hora em vez de gastar a
chamada paga.

**Busca nos estudos**: o primeiro **Recriar índice** baixa um modelo de embeddings (~250 MB) e indexa
os comentários de todos os capítulos; depois disso, salvar um capítulo atualiza o índice sozinho.
O índice fica no mesmo SQLite (extensão `sqlite-vec`; sem ela, o app usa numpy).

**LangFuse** (opcional): com o Docker Compose do projeto ele roda em http://localhost:3000; crie um
projeto, cole host e chaves, e cada explicação vira um trace com as etapas, os tokens e o custo.

### Avaliação

A pasta `backend/evals/coach` mede o treinador contra um conjunto de exercícios com gabarito da
engine, em três variantes (só prompt, agente, agente com busca) e dois modelos. Gere o conjunto com
`uv run python -m evals.coach.dataset`, rode com `uv run python -m evals.coach.run --variante agente_rag
--modelo opus` (chave em `ANTHROPIC_API_KEY`) e monte o relatório com `uv run python -m evals.coach.report`.
O relatório fica em `docs/coach-eval.md`.

## Fontes de exercício

A repetição espaçada mistura três fontes: **seus erros** (das partidas importadas do chess.com),
**táticas guardadas do Lichess** e **capítulos de estudos**. No início do treino, na repetição
espaçada, dá para escolher quais fontes entram na sessão. O cartão "Estado" do Painel mostra quantos
exercícios de cada fonte estão na repetição.

Qualquer exercício pode sair da repetição sem ser apagado: no resultado do treino, "Tirar da repetição"
(e "Voltar para a repetição" para desfazer). Uma tática do Lichess só entra na repetição quando você
clica em "Guardar para repetir" no resultado.

Nos exercícios dos seus erros, a resposta do adversário dentro da solução é a **defesa mais
resistente** na mesma profundidade (e no mesmo tempo de busca) do lance do solver — as duas buscas
são a mesma, então a solução não mostra uma defesa mais fraca que a apontada pela Análise.

### Continuação enquanto o lance for único

Um exercício de ganho de material não para na captura: a solução segue enquanto **só houver um
lance** para você. A cada vez sua, a engine é consultada com três linhas; o lance continua no
exercício se estiver à frente do segundo por pelo menos a distância configurada em
"lance único: distância mínima para a 2ª linha (cp)" (Configurações → "Erros e treino", 150 cp por
padrão) e se ainda ganhar. Quando o segundo lance chega perto, a linha acaba ali — daquele ponto em
diante seria técnica, não tática. Se a linha terminar em mate, o mate é o último lance; a solução
nunca termina com um lance do adversário. Os exercícios que já acabam em mate não mudam.

Isso vale para os exercícios criados dali em diante. Para alongar os que já existem, use
**Estender exercícios**, em Configurações (cartão "Exercícios", perto do fim da página). O botão não
pede confirmação porque não apaga nada: cada exercício continua sendo o mesmo, com as revisões, o
intervalo e a data do próximo encontro intactos — só a solução fica mais longa. Se a continuação
terminar em mate, o exercício passa a ser de mate (o tema vira "mate em N").

O andamento aparece no cartão "Tarefas" do Painel, como "exercício 3 de 120", e dá para cancelar. As
contagens só aparecem quando a tarefa termina: a mensagem final diz quantos exercícios foram
examinados e quantos foram estendidos (e, se a engine tiver falhado em algum, quantos ficaram "com
erro"). Cancelando, a mensagem é "cancelado" — sem contagens —, a tarefa para depois do exercício
atual e tudo o que já tinha sido estendido fica como está.

## Progresso

A tela `/progresso` (link no Painel, ao lado dos botões de treino) junta o que mudou no período —
30, 90 ou 365 dias, escolhidos no seletor do topo:

- **cartões**: dias seguidos com revisão (a mesma sequência do Painel), revisões no período com o
  acerto em porcentagem e quantos exercícios estão na repetição;
- **revisões por dia**: colunas empilhadas, certas embaixo e erradas em cima. Dias sem revisão não
  entram na lista — o gráfico mostra só os dias em que você treinou;
- **rating de táticas**: um ponto por tentativa, em ordem cronológica;
- **por fonte** e **por tema**: revisões (ou tentativas), certas e o acerto em porcentagem.

Sem nenhuma revisão no período, o lugar dos gráficos traz "Ainda não há revisões neste período." e a
tabela por fonte fica zerada.

Tudo vem de `GET /api/stats/progress?days=90` (`backend/chess_trainer/api/routes/stats.py`, lógica em
`core/stats.py: progress`), que só lê o banco. Os gráficos são SVG escrito à mão em
`frontend/src/components/charts/` (`LineChart`, `BarChart`), sem biblioteca: cada um é um `role="img"`
com `aria-label` resumindo os números, e as cores saem dos tokens (`--ok`, `--bad`, `--brand`,
`--muted`, `--line`) para valerem nos dois temas.

## Som

Efeitos sonoros curtos para lance, captura, xeque, erro, dica e exercício resolvido. Valem no
treino (incluindo a refutação do lance errado), ao jogar lances no tabuleiro de análise — o da tela
`/analise` e o do resultado do exercício — e ao navegar pela linha da solução na revisão de erros.
Navegar pela árvore de lances não toca nada: só o lance jogado tem som.

Os sons são as amostras do conjunto "standard" do Lichess (`frontend/public/sound/`, licença
AGPL-3.0 — ver `frontend/public/sound/LICENSE.txt`), carregadas e decodificadas pela Web Audio API
na primeira vez que cada uma é tocada e reaproveitadas depois via `AudioBufferSourceNode`. Se a
amostra ainda não chegou (ou o carregamento falha), um som sintetizado na hora entra no lugar dela,
para o efeito nunca ficar mudo.

O botão 🔊/🔇 na barra de navegação liga e desliga tudo; a escolha fica guardada no navegador
(`sound.enabled`). Navegadores só liberam áudio depois de um clique ou tecla na página — o primeiro
gesto já destrava, e o som começa ligado.

## Tema

Claro e escuro. O botão ☀️/🌙 no fim da barra de navegação alterna os dois e guarda a escolha no
navegador (`tema`). Sem escolha guardada, a interface segue o `prefers-color-scheme` do sistema —
inclusive se ele mudar com a página aberta.

A paleta inteira mora em `frontend/src/styles/tokens.css`: o tema claro nas variáveis de `:root`, o
escuro trocando as mesmas variáveis em `:root[data-theme="dark"]`. Nenhuma regra de
`frontend/src/styles/base.css` precisa saber em qual tema está — para uma cor nova, crie um token
nos dois blocos em vez de escrever o valor na regra. O atributo é aplicado por
`frontend/src/lib/theme.ts` (`getTema`, `setTema`, `useTema`, `aplicarTema`), chamado em `main.tsx`
antes do primeiro render para a tela não piscar clara.

Ficam de fora do tema, de propósito: o tabuleiro e as peças (tema marrom do chessground), a barra de
avaliação — que é preta e branca porque representa as peças — e as cores dos ícones de classificação
de lance, que são as do chess.com.

## Desenvolvimento

Backend: `cd backend && uv run python -m chess_trainer` (API em :8000, docs em /docs).
Frontend: `cd frontend && npm run dev` (Vite em :5173 com proxy para /api).
Testes: `cd backend && uv run pytest -q` · `cd frontend && npm test`.
