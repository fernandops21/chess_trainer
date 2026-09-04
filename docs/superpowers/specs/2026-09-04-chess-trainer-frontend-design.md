# Chess Trainer — Frontend do ciclo A

Data: 2026-09-04
Status: aprovado em conversa, aguardando revisão do spec escrito
Depende de: `2026-09-04-chess-trainer-ciclo-a-design.md` (backend, implementado e mergeado na `main`)

## 1. Objetivo e escopo

Interface web para o backend do ciclo A: treinar os puzzles do dia com
repetição espaçada, acompanhar importação e análise, navegar partidas e
revisar erros. Substitui o protótipo descartável (`frontend/dist/index.html`
escrito à mão).

Decisões já tomadas:

- **Uso**: computador e celular na mesma rede local. Layout responsivo com
  toque. Sem login (um usuário; o backend passa a escutar na rede, com aviso
  na tela de Configurações).
- **Escopo do primeiro corte**: as cinco telas do spec do backend (§10), com
  Partidas e Revisão de erros em versão simples (sem gráfico de avaliação,
  sem filtros finos).
- **Pilha**: React 18 + TypeScript + Vite; TanStack Query (dados do
  servidor); React Router; chessground (tabuleiro) + chess.js (validação de
  lances); CSS puro com variáveis; Vitest para testes. Sem biblioteca de
  componentes.
- **Entrega**: `npm run build` gera `frontend/dist`, que o backend já serve
  em `/`. Um comando para rodar tudo (`uv run python -m chess_trainer`).
  Em desenvolvimento, Vite com proxy de `/api` para `:8000`.

## 2. Navegação e layout

Rotas (SPA): `/` Painel, `/treinar`, `/partidas`, `/partidas/:id`, `/erros`,
`/config`. O backend devolve `index.html` para qualquer caminho que não seja
`/api/*` nem um arquivo estático existente, para recarregar uma rota
funcionar.

- **Desktop (≥ 900 px)**: barra lateral fixa à esquerda com os cinco itens e o
  contador de vencidos ao lado de "Treinar"; conteúdo à direita. Treinar em
  duas colunas: tabuleiro (até 640 px) e painel de informações.
- **Celular (< 900 px)**: barra inferior com os cinco ícones; conteúdo em
  coluna única. Treinar: tabuleiro na largura toda; tarefa, mensagem e botões
  logo abaixo, visíveis sem rolar.
- **Toque**: chessground com arrastar e tocar-tocar; destinos legais
  destacados ao selecionar a peça. Alvos de toque com 44 px no mínimo.
- **Tema**: paleta clara e quente (fundo areia, tabuleiro marrom, peças
  cburnett) em variáveis CSS (`styles/tokens.css`). Tema escuro fica para
  depois.
- **Acessibilidade mínima**: foco visível, botões com rótulo, navegação de
  lances por teclado no desktop (← →).

## 3. Tela Treinar

### 3.1 Início da sessão

Painel curto antes do primeiro puzzle: filtros opcionais (categoria, tipo
punir/evitar, cor do solver), modo "até acabar a fila" ou "N minutos" (padrão
25, valor lembrado em `localStorage`), botão Começar. Cria a sessão
(`POST /api/sessions` com os filtros e `planned_minutes`) e carrega a fila
(`GET /api/queue` com os mesmos filtros).

### 3.2 Máquina de estados do puzzle (`usePuzzle`)

Hook puro, sem dependência do tabuleiro, testável no Vitest. Entrada: o
`PuzzleOut` da API. Estado: posição atual (chess.js), índice na solução,
`wrong`, `usedHint`, `phase`.

```
loading → awaiting_move
awaiting_move --lance do solver correto--> (há resposta da engine?) sim → engine_replying → awaiting_move
                                                                    não/último → solved
awaiting_move --lance errado--> awaiting_move  (wrong = true, mensagem, lance não aplicado)
solved → submitting (POST /api/reviews) → result
```

Regras:

- Só o lado do solver é jogável; destinos = lances legais do chess.js.
- Lance correto = igual ao `uci` esperado ou a uma das `alternatives` do
  passo. Promoção: se o lance esperado promove, abre menu de peça; senão a
  promoção padrão é dama (o backend só gera puzzles com promoção quando a
  solução a contém).
- Resposta da engine aplicada com ~350 ms de atraso, com animação.
- Lance errado: desfeito, mensagem "Não é esse. Tente de novo.", `wrong =
  true`, puzzle continua até o fim (spec do backend §8).
- Dica: destaca a casa de origem da peça esperada (chessground
  `autoShapes`), `usedHint = true`, botão desabilitado.
- `duration_ms` medido do primeiro render do puzzle até `solved`.
- `POST /api/reviews` com `puzzle_id`, `session_id`, `correct = !wrong`,
  `used_hint`, `duration_ms`. Falha de rede: mostra erro e botão "Tentar de
  novo"; nunca avança silenciosamente.

### 3.3 Resultado

Veredito (resolvido sem erro / contou como erro), próxima revisão em N dias,
facilidade e lapsos, aviso se virou sanguessuga. Linha da engine navegável
(◀ ▶, teclado ← →, deslizar no celular), com a jogada atual destacada. Para
"evitar", a linha inclui `explanation_pv`. Tema, categoria, link para a
partida no chess.com (`source_id`) e para `/partidas/:id` no lance do erro.
Botão "Próximo".

### 3.4 Relógio da sessão (`useSessionClock`)

Contagem regressiva visível quando há `planned_minutes`. Ao zerar: o puzzle
atual termina normalmente; em seguida abre "Tempo esgotado: continuar ou
encerrar?". Continuar segue na mesma sessão, com o relógio contando para cima
e mostrando o excedente. Encerrar chama `POST /api/sessions/{id}/end` e
mostra o resumo. Sem `planned_minutes`, o relógio mostra o tempo decorrido.

### 3.5 Resumo da sessão

Puzzles feitos, acertos, tempo total, lista dos que contaram como erro com
link para `/erros` na posição correspondente. Botão "Nova sessão".

### 3.6 Fila vazia

Mensagem com o motivo (nenhum vencido e nenhum novo disponível; ou limite
diário de novos atingido, com quantos existem) e atalho "Analisar mais
partidas" que leva ao Painel.

## 4. Painel

- Três números grandes: vencidos hoje, novos disponíveis (e quantos ainda
  cabem hoje), sequência de dias. Botão "Treinar" com o total da fila.
- Cartão de estado: partidas importadas/analisadas, última importação, engine
  encontrada (caminho) ou ausente (link para Configurações).
- Cartão de tarefa: quando há job (`GET /api/status` a cada 2 s enquanto
  `running`), barra de progresso com `done/total` e `message`, botão Cancelar
  (`POST /api/jobs/cancel`). Quando idle: "Importar agora" e "Analisar N
  partidas" (N escolhido ali, padrão 5, lembrado em `localStorage`). Estado
  `error` mostra a mensagem da API e permite tentar de novo. Respostas 409 e
  503 viram mensagens legíveis.

## 5. Partidas

- `/partidas`: lista paginada (50 por página, `limit/offset`), mais recentes
  primeiro: data, adversário, sua cor, resultado, categoria, analisada, seus
  erros. Filtros: categoria, cor, resultado, analisada.
- `/partidas/:id`: tabuleiro orientado para a sua cor; lista de lances em duas
  colunas com erros marcados (amarelo mistake, vermelho blunder); navegação
  por clique, ◀ ▶ e teclado; ao lado do lance atual, avaliação antes/depois
  (formato `+1.25` / `#3`) e melhor lance da engine; em cada erro com puzzle,
  atalho "Treinar este" (abre `/treinar?puzzle=<id>`, que carrega esse puzzle
  fora da ordem da fila; a resolução é registrada como revisão normal). Partida não analisada: lances sem
  avaliação e botão "Analisar esta partida" (`POST /api/analyze?game_id=`).
- Sem gráfico de avaliação nesta versão.

## 6. Revisão de erros

- `/erros`: lista dos seus erros (`GET /api/mistakes?by=me`), mais recentes
  primeiro; filtros por nível e categoria; seletor "incluir erros do
  adversário" (`by=all`). Item: tabuleiro em miniatura (só leitura), lance
  jogado, melhor lance, queda de avaliação, tema do puzzle quando existe.
- Detalhe (painel lateral no desktop, tela cheia no celular): tabuleiro na
  posição do erro; o que foi jogado; a refutação (linha do puzzle "punir")
  e a linha da engine navegáveis; links para a partida e para treinar o
  puzzle. Como a refutação já foi mostrada nesta tela, "Treinar este" a
  partir daqui abre o puzzle com aviso "solução já vista" e a resolução é
  registrada com `used_hint = true` (conta como erro, volta em 1 dia); a
  partir da tela de partida, onde só o lance errado está marcado, a revisão é
  registrada normalmente.
- Seção "Sanguessugas" no topo quando existir alguma (`GET /api/leeches`):
  mesma ficha, botão "Devolver à fila" (`POST /api/puzzles/{id}/unleech`).

## 7. Configurações

- Campos: usuário do chess.com; categorias (caixas de seleção); caminho do
  Stockfish com "Testar" (lê `/api/status`); profundidades de análise e de
  puzzle; limiares de mistake/blunder e gap do "evitar"; novos por dia;
  sanguessuga após N erros.
- Validação no cliente (inteiros, faixas: profundidades 6–30, limiares
  50–1000, novos por dia 1–100, lapsos 2–20); o servidor normaliza o usuário.
  Salvar com feedback de sucesso/erro.
- "Perigo": "Regerar puzzles" com confirmação explicando que apaga o
  histórico de treino (`POST /api/puzzles/regenerate`).
- "Acesso pelo celular": mostra `http://<ip-local>:8000` (IP vindo de
  `GET /api/status`) e o aviso de que qualquer aparelho na rede acessa.

## 8. Camada de API e estrutura

- `src/api/client.ts`: `fetch` com base `/api`, funções tipadas por rota,
  erro HTTP vira `ApiError(status, message)` com a mensagem `detail` do
  FastAPI. Tipos TypeScript espelhando os schemas do backend.
- `src/api/queries.ts`: hooks TanStack Query. Recarga automática do status a
  cada 2 s apenas enquanto `job.state == "running"`. Mutações (review,
  settings, jobs, unleech, sessions) invalidam painel, fila e status.
- Estrutura:

```
frontend/
  package.json, vite.config.ts (proxy /api → 127.0.0.1:8000), tsconfig.json
  index.html
  src/
    main.tsx, App.tsx (rotas, layout, Nav)
    api/        client.ts, types.ts, queries.ts
    board/      Board.tsx (chessground), useBoardMoves.ts, MiniBoard.tsx
    train/      usePuzzle.ts, useSessionClock.ts, TrainPage.tsx, SessionStart.tsx,
                ResultPanel.tsx, SessionSummary.tsx, LineViewer.tsx
    pages/      DashboardPage.tsx, GamesPage.tsx, GameDetailPage.tsx,
                MistakesPage.tsx, SettingsPage.tsx
    components/ Nav.tsx, StatCard.tsx, JobCard.tsx, MoveList.tsx, Modal.tsx
    styles/     tokens.css, base.css
  tests/        usePuzzle.test.ts, useSessionClock.test.ts, client.test.ts
```

## 9. Mudanças no backend (pequenas, entram no mesmo plano)

- Servir `index.html` para rotas desconhecidas que não comecem com `/api`
  (fallback de SPA) quando `frontend/dist` existe.
- `POST /api/analyze?game_id=<id>`: analisa só essa partida (202/404/409/503).
- `GET /api/status` devolve `local_url` (`http://<ip-local>:8000`).
- Servidor escuta em `0.0.0.0:8000` por padrão (configurável por variável
  `CHESS_TRAINER_HOST`).
- `GET /api/puzzles/{id}` já existe; `/treinar?puzzle=<id>` usa isso.

## 10. Testes

- **Vitest, hooks puros**: `usePuzzle` (lance certo avança; errado desfaz e
  marca; dica marca; resposta da engine aplicada; último lance conclui;
  alternativa aceita; promoção pede peça; falha no POST não avança),
  `useSessionClock` (contagem regressiva; zerar dispara a pergunta; continuar
  conta para cima; encerrar chama a API), `client` (URLs, query strings,
  `ApiError` com `detail`).
- **Backend (pytest)**: fallback de SPA; `analyze?game_id`; `local_url` no
  status.
- **Sem ponta a ponta no navegador** nesta versão.
- **Verificação manual**: sessão de treino completa no desktop e no celular
  (mesma rede); importar e analisar pelo Painel com progresso e cancelamento;
  abrir uma partida, navegar, pular para um erro e treinar o puzzle; regerar
  puzzles pela tela de Configurações; recarregar `/treinar` no navegador.

## 11. Fora de escopo

Gráfico de avaliação, tema escuro, filtros por tema na lista de erros,
login, PWA/instalação no celular, testes de ponta a ponta, estatísticas por
sessão além do resumo.
