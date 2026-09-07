# Chess Trainer — Ciclo B2: editor de estudos

Data: 2026-09-06
Status: proposto; aguarda ok do usuário (que autorizou executar B2 logo após B1, se este spec for aprovado).
Depende de: ciclo B1 (fontes de exercício e estudos importados).

## 1. Motivação

O professor do usuário monta os exercícios das aulas como estudos do Lichess
(capítulos "gamebook" com posição, linha principal, variações comentadas e
setas). O usuário quer que isso possa ser feito aqui, para que, quando o
produto abrir, um professor crie o estudo no app e os alunos treinem por
repetição espaçada. Neste ciclo: criar e editar estudos localmente, com
exportação PGN compatível com o Lichess. Contas e compartilhamento ficam
para depois.

## 2. Modelo

- `Study` ganha `origin` (`lichess` | `local`) e `updated_at`.
- `StudyChapter` ganha `tree_json` (árvore de lances, fonte da verdade do
  editor) e `updated_at`; `pgn` passa a ser gerado a partir da árvore no
  salvamento. Capítulos importados do Lichess recebem `tree_json` na
  importação (parser do B1 devolve a árvore).
- Árvore (JSON):
  ```
  {"fen": "<FEN inicial>", "orientation": "white|black", "intro": "...",
   "root": {"children": [node, ...]}}
  node = {"id": "n12", "uci": "e2e4", "san": "e4", "comment": "...",
          "shapes": [{"orig":"e2","dest":"e4","brush":"green"}],
          "nags": [1], "children": [node, ...]}
  ```
  O primeiro filho é a linha principal; os demais, variações. `id` é
  estável dentro do capítulo (gerado no cliente).
- Puzzle do capítulo: regerado ao salvar (linha principal, `wrong_moves` das
  variações comentadas no lance do solver, `comments`, `shapes`,
  `intro_comment`), mantendo id e histórico quando `fen` e linha principal
  não mudam (mesma regra do reimport do B1). Capítulo `read` não gera
  puzzle; alternar para `gamebook` gera.

## 3. Editor (frontend)

- Tela Estudos: "Novo estudo" (título; autor = nome configurado ou vazio),
  "Editar" nos estudos locais e nos importados (edição local; reimportar
  sobrescreve com aviso). "Exportar PGN" no estudo e no capítulo.
- Editor de capítulo (`/estudos/:id/capitulos/:cid/editar`):
  - Cabeçalho: nome, modo (`gamebook`/`read`), orientação, posição inicial
    (FEN colada, posição padrão, "a partir desta partida" via `/partidas/:id`
    no lance escolhido, ou a posição atual do tabuleiro de análise), enunciado.
  - Tabuleiro jogável dos dois lados (legalidade pelo chess.js), com
    marcações do botão direito **salvas** no nó atual.
  - Árvore de lances ao lado, no formato do Lichess (linha principal
    corrida, variações entre parênteses, recuadas): clicar vai para o nó;
    jogar um lance que já existe segue o nó; lance novo cria filho (variação
    se não for o primeiro); teclas ← → ↑ ↓ para navegar.
  - Menu do nó (botão direito no lance da árvore): "Promover a linha
    principal", "Apagar daqui", "Comentar" (caixa de texto abaixo do
    tabuleiro, salva ao perder o foco), NAGs básicos (!, ?, !!, ??, !?, ?!).
  - "Analisar" abre a avaliação da posição atual (reusa `POST /api/analyse`)
    com as 3 linhas e "adicionar como variação" (insere a linha como nós
    filhos).
  - Salvar (Ctrl+S e botão): `PUT /api/studies/{id}/chapters/{cid}` com a
    árvore; o servidor valida (lances legais a partir da FEN), gera o PGN e
    regenera o puzzle; resposta traz o capítulo atualizado. Aviso de
    alterações não salvas ao sair.
  - Reordenar capítulos por arrastar na lista do estudo; "Novo capítulo"
    duplica a posição inicial padrão; "Duplicar capítulo".
- Capítulos `read` (partidas anotadas) ganham leitura navegável: a mesma
  árvore, só leitura, com comentários e marcações do autor (fecha a pendência
  do B1).

## 4. PGN e compatibilidade com o Lichess

- Exportação do estudo: um jogo PGN por capítulo, na ordem, com os headers
  `[Event "<título>: <capítulo>"]`, `[Site]`, `[Result "*"]`, `[FEN]` e
  `[SetUp "1"]` quando a posição não é a inicial, `[Orientation]`,
  `[ChapterMode "gamebook"]` quando aplicável, `[StudyName]`,
  `[ChapterName]`; comentários com `[%cal …]`/`[%csl …]` para as marcações
  e o enunciado como comentário antes do primeiro lance; variações e NAGs
  no formato padrão. Gerado no backend com python-chess.
- Round trip: exportar um estudo importado e reimportá-lo (via PGN) produz a
  mesma árvore (teste com o estudo real). Um estudo criado aqui importa no
  Lichess por "Importar PGN" com capítulos, comentários e setas.
- Importação de PGN local (B1) também aceita PGN exportado daqui.

## 5. API

- `POST /api/studies` `{title, author}`; `PUT /api/studies/{id}` `{title,
  author, chapter_order}`; `POST /api/studies/{id}/chapters` `{name, fen,
  orientation, mode}`; `PUT /api/studies/{id}/chapters/{cid}` `{name, mode,
  orientation, tree}`; `DELETE …/chapters/{cid}`; `POST …/chapters/{cid}/
  duplicate`; `GET /api/studies/{id}/pgn` e `GET …/chapters/{cid}/pgn`
  (texto, `Content-Disposition` para download).
- Validação no servidor: FEN válida, todos os lances legais, árvore com no
  máximo 2 000 nós, comentários até 4 000 caracteres.

## 6. Testes

- Backend: árvore → PGN → árvore (round trip, incluindo variações
  aninhadas, NAGs, `%cal`/`%csl`, enunciado); validação de lances ilegais;
  regeneração do puzzle preservando histórico; exportação do estudo real
  reimportada sem perdas; rotas.
- Frontend: hook da árvore (`useMoveTree`: play, goTo, promote, deleteFrom,
  comment, shapes, navegação por teclado); editor salva a árvore certa;
  aviso de não salvo; leitura de capítulo `read`.
- Manual: recriar um capítulo do Basso do zero, exportar, importar no
  Lichess e conferir.

## 7. Fora de escopo

Contas, compartilhamento e publicação; publicar direto no Lichess pela API
(precisa de OAuth); edição colaborativa; relógios; sincronização com o
Lichess após a importação.
