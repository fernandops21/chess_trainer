# Chess Trainer

Treino de xadrez a partir dos seus próprios erros: importa partidas do chess.com, analisa com Stockfish,
gera puzzles dos erros (seus e do adversário) e agenda com repetição espaçada.

## Rodar

    cd frontend && npm install && npm run build
    cd ../backend && uv sync && uv run python -m chess_trainer

Abra http://127.0.0.1:8000 (ou, no celular na mesma rede, o endereço mostrado em Configurações).
Stockfish: ver backend/README.md.

Tabuleiro de análise livre (`/analise`, com avaliação do Stockfish no backend): pelo item "Análise" do
menu, pelo link "Explorar" no resultado do treino (abre em nova aba, para não perder a sessão em
andamento), pelo botão "Explorar daqui" na partida e pelo botão "Explorar" na revisão de erros. É
também por ali que se começa um capítulo de estudo (ver "Criar estudos aqui").

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

Como importar: **Estudos → "Importar do Lichess"**, cole o endereço (`lichess.org/study/<id>`, com ou
sem o capítulo no fim) e clique em "Importar"; ou clique em "colar PGN" e cole o PGN exportado. A
importação roda em segundo plano e o andamento ("2/5 capítulos") aparece no cartão "Tarefas". Ao
terminar, a mensagem diz quantos capítulos e exercícios entraram e quais foram pulados (capítulo com
lance ilegal, por exemplo).

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

Atalhos: **←** e **→** andam na linha, **↑** e **↓** trocam de variação, **Home** volta à posição
inicial e **Ctrl+S** salva (o botão "Salvar" fica embaixo do tabuleiro). O cabeçalho mostra o estado
("alterações não salvas" / "salvo às HH:MM"), e sair da tela com pendências pede confirmação.

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

## Fontes de exercício

A repetição espaçada mistura três fontes: **seus erros** (das partidas importadas do chess.com),
**táticas guardadas do Lichess** e **capítulos de estudos**. No início do treino dá para escolher quais
fontes entram na sessão (e, com "Estudos", qual estudo). O cartão "Estado" do Painel mostra quantos
exercícios de cada fonte estão na repetição.

Qualquer exercício pode sair da repetição sem ser apagado: no resultado do treino, "Tirar da repetição"
(e "Voltar para a repetição" para desfazer). Uma tática do Lichess só entra na repetição quando você
clica em "Guardar para repetir" no resultado.

## Desenvolvimento

Backend: `cd backend && uv run python -m chess_trainer` (API em :8000, docs em /docs).
Frontend: `cd frontend && npm run dev` (Vite em :5173 com proxy para /api).
Testes: `cd backend && uv run pytest -q` · `cd frontend && npm test`.
