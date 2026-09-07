# Ciclo B2 (editor de estudos) — pendências

Itens levantados durante o ciclo do branch `feat/editor-de-estudos` que **não**
foram corrigidos aqui: limitações conhecidas, escolhas adiadas e riscos que
valem uma olhada depois. Nada disso é bloqueio de merge.

## Frontend

- **Saída da tela do editor só é barrada nos links dele** (`ChapterEditorPage.tsx`):
  fechar a aba ou recarregar cai no `beforeunload`, e os links "Voltar ao estudo"
  e "Ver como leitura" pedem confirmação no `onClick`. Qualquer outra navegação
  interna (menu lateral, botão "voltar" do navegador) sai sem avisar. A correção
  de verdade é o `useBlocker` do react-router, que exige um **data router**
  (`createBrowserRouter` + `RouterProvider`) — hoje o `main.tsx` monta
  `BrowserRouter` + `<Routes>`, então a troca mexe na raiz do app e em todas as
  rotas.
- **"Novo capítulo" não parte da posição atual**: o modal oferece "posição
  padrão" ou "FEN colada", porque não tem tabuleiro. Quem quer começar de uma
  posição montada passa pela Análise ("Salvar como capítulo"). Um mini-tabuleiro
  no modal resolveria.
- **O editor não recarrega o formulário com a resposta do `PUT`**: se o servidor
  normalizar o nome ou a árvore ao salvar, a tela segue com o que o usuário
  digitou até recarregar a página. É proposital (não desfazer o que foi digitado
  enquanto a requisição estava no ar), mas esconde normalizações do servidor.
- **`ErrorBox` depende de `ApiError.details`**: o 422 do editor só sai item a
  item porque `routes/studies.py` manda `detail` como lista de strings. Se algum
  dia virar a lista de objetos do pydantic, a caixa volta a mostrar o JSON cru.

## Backend

- **Duplicar sempre cria uma cópia de leitura** (`duplicate_chapter`): a única
  `(fen_start, kind, source)` de `puzzles` não deixa dois exercícios de estudo
  partirem da mesma posição inicial, então a cópia entra como `read` e quem
  duplicou precisa mudar a posição (ou a linha) e escolher "exercício" ao
  salvar. Uma chave que incluísse o capítulo — ou uma solução como parte da
  identidade do exercício — tiraria essa amarra.
- **Dois capítulos não podem partir da mesma posição inicial**: no editor os
  dois caminhos de colisão agora recusam o salvamento com 422 (o capítulo que já
  tem exercício e o que ainda não tem), o que ao menos avisa em vez de gravar um
  capítulo sem exercício calado. Mas a recusa é uma amarra do esquema, não uma
  regra do domínio: dois capítulos com a mesma posição inicial e linhas
  diferentes são dois exercícios legítimos. A correção de verdade é a chave do
  exercício incluir o capítulo — trocar a única `(fen_start, kind, source)` de
  `puzzles` por algo como `(fen_start, kind, source, chapter_id)` —, o que exige
  mexer no índice em `core/db.py` (`uq_puzzle_fen_kind_source`, criado à mão nos
  bancos antigos) e conferir quem depende dele: o upsert da importação
  (`_upsert_puzzle`, que hoje procura o "gêmeo" por essa chave) e a adoção de
  exercícios órfãos. Feito isso, caem juntas esta recusa e a cópia de leitura
  obrigatória do `duplicate_chapter`.
- **Ids de nó reaproveitados** (`nextId` em `frontend/src/analysis/moveTree.ts`): o
  próximo id é `n<maior + 1>`, então apagar o nó de maior número e criar outro
  devolve o mesmo `n<k>`. Hoje nada persistente é indexado por id (o menu do nó
  guarda o id só enquanto está aberto, e o `setTree` compara o **caminho** de
  lances), mas qualquer estado de UI guardado por id passaria a apontar para
  outro lance.
- **Contorno do limite de profundidade do pydantic-core** (`_chapter_response`
  em `api/routes/studies.py`): a árvore de um capítulo longo aninha centenas de
  dicionários, bem mais fundo do que o serializador do pydantic aceita (ele
  acusa "circular reference"). A rota serializa o modelo com `exclude={"tree"}`
  e encaixa a árvore crua no corpo. Funciona, mas a árvore deixa de passar pela
  validação do modelo na saída — se um dia a estrutura mudar, o contrato do
  `ChapterDetail` não pega o erro.
- **`[%eval]` e `[%clk]` somem na importação** (`clean_comment` em
  `core/studies/tree.py`): o comentário é limpo de todos os comandos `[%…]`, e
  só `[%cal]`/`[%csl]` são recuperados como marcações. Estudo com avaliações ou
  relógios anotados perde essa informação, e ela não volta na exportação.
- **Reimportar um PGN exportado daqui cria outro estudo**: a exportação não
  escreve `[ChapterURL]` (esses capítulos não existem no Lichess), e o upsert
  casa os capítulos justamente por essa chave. Colar de volta o PGN de um estudo
  local cria um estudo novo, com exercícios novos e sem o histórico do original.
  Só vale a pena resolver se a ida-e-volta pelo arquivo virar um caminho comum
  (uma chave própria no cabeçalho resolveria).

## Verificação manual pendente

- **Importar um estudo de verdade do Lichess**: os testes cobrem a importação
  com PGN de fixture e HTTP dublado (`tests/fixtures/study_4JKVAfaE.pgn`), e a
  conferência na tela foi feita com estudos locais. Falta o caminho completo com
  a rede: colar a URL de um estudo público, ver o job andar, abrir os capítulos
  importados no editor e no modo leitura (comentários, setas e casas do autor) e
  exportar o PGN de volta. É o único ponto do ciclo sem verificação de ponta a
  ponta.

## Configurações

- **Não existe uma configuração de "autor"**: o autor sugerido em "Novo estudo"
  e em "Salvar como capítulo" vem de `chesscom_username`, que é o usuário do
  chess.com — serve porque costuma ser a mesma pessoa, mas é um empréstimo. Um
  campo próprio em Configurações (com o nome do chess.com como padrão) seria
  mais honesto.
