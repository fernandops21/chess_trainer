# Chess Trainer — "Evitar" completo, resultado explicado e tabuleiro de análise

Data: 2026-09-05
Status: aprovado em conversa
Depende de: specs do ciclo A (backend e frontend), ambos implementados na `main`.

## 1. Motivação

No primeiro uso real, o puzzle "evitar" mostrou-se incompreensível: um lance
(e6) "melhor por +4.3" cuja vantagem só aparece seis lances depois, com a
explicação da engine aberta já na posição final. O usuário teve que ir ao
chess.com para entender. Três correções:

1. **Tela de resultado**: abrir a linha no lance do usuário, numeração correta,
   e mostrar o que ele jogou na partida e a refutação daquele lance.
2. **"Evitar" segue a mesma regra do "punir"**: o usuário joga a linha inteira
   até o ganho se materializar; sem ganho concreto, não há puzzle. Erros
   posicionais ficam na Revisão de erros, não na fila.
3. **Tabuleiro de análise no app**: explorar qualquer posição com a engine, a
   partir da partida, do erro ou do resultado do puzzle.

## 2. Tela de resultado

- A linha navegável abre na posição **após o último lance do solver** (o que o
  usuário acabou de jogar), não no fim da explicação.
- Numeração: o primeiro lance da linha está no ply `puzzle.ply` para "evitar"
  (o solver joga no lugar do erro) e `puzzle.ply + 1` para "punir".
- `PuzzleOut` ganha `mistake` (`move_played`, `move_uci`, `eval_before`,
  `eval_after`, `mistake_level`, `mistake_by`) e `siblings` (lista de
  `{id, kind}` dos outros puzzles da mesma posição).
- Para "evitar", o painel mostra: "Na partida você jogou **X** (`+4.34` →
  `+1.50`). O melhor era **Y**." e, quando existe o puzzle "punir" irmão, uma
  segunda linha navegável "O que acontecia depois de X" (a solução do "punir",
  a partir da posição após X). Sem navegação por teclado na segunda linha.
- Botão **Explorar** abre o tabuleiro de análise na posição inicial do puzzle.

## 3. "Evitar" como linha completa

- Gerado na posição antes do erro do usuário. Primeira busca multipv 3 com
  `puzzle_depth`. Condições: `best.move != lance jogado`; gap
  `best.score − second.score ≥ avoid_gap_cp` (mate a favor conta como gap
  infinito); `best.score ≥ min_solver_eval_cp` ou mate.
- Alvo de material: `floor_to_piece(min(clamp(gap), clamp(best.score)) / 100)`;
  modo mate se `best` é mate. A partir daí, **a mesma máquina do "punir"**:
  o solver joga, a engine responde com a melhor defesa, termina quando o ganho
  se materializa (mate ou captura que sobrevive à resposta), alternativas só
  no lance final, descarte em empate/ambiguidade/limite de lances.
- `end_reason` passa a ser `mate` ou `material_gain` também para "evitar";
  `explanation_pv` fica vazio (mantido no JSON por compatibilidade).
- Posições de erro do usuário sem nenhum puzzle são "posicionais" (ou
  triviais): não entram na fila; a Revisão de erros mostra a etiqueta
  "posicional" e o botão Explorar.
- `POST /api/puzzles/regenerate?kind=avoid`: apaga só os puzzles "evitar" (e
  suas revisões) e os regera; o histórico dos "punir" fica intacto. Sem
  `kind`, comportamento atual (tudo).

## 4. Tabuleiro de análise

### 4.1 Backend

- `POST /api/analyse` com `{"fen": str, "multipv": int = 3}` → `{"fen", "turn",
  "lines": [{"move": uci, "san", "score": cp (POV de quem joga), "pv": [uci],
  "pv_san": [san]}]}`. `400` para FEN inválido; `503` sem engine.
- Engine interativa **separada** da engine dos jobs: instância própria em
  `app.state.analysis_engine`, criada na primeira chamada, protegida por um
  lock (uma análise por vez), `depth = 16`, `max_seconds = 3`. Posições
  terminais devolvem `lines: []` e `terminal: "checkmate" | "stalemate" |
  "draw"`.
- Cache em memória por FEN (até 500 entradas, LRU) para voltar e avançar sem
  esperar.

### 4.2 Frontend

- Rota `/analise?fen=<fen>&orientation=<white|black>&back=<caminho>`.
- `useAnalysis(fenStart)`: pilha de posições (`fens`, `sans`), `play(uci)`,
  `undo()`, `reset()`, `current`; legalidade pelo chess.js; ambos os lados
  jogáveis.
- Componente `AnalysisBoard`: tabuleiro com destinos legais; avaliação em
  número (`+1.25`, `#3`); seta verde do melhor lance (autoShape com `orig` e
  `dest`); três linhas em SAN, clicáveis (clicar joga a linha inteira até o
  fim, lance a lance, com animação); botões ◀ (desfazer), ⏮ (posição inicial),
  inverter, e "Voltar" para `back`. Lista dos lances explorados com clique para
  voltar a qualquer ponto. Indicador "analisando…" enquanto a resposta não
  chega; erro visível se a engine falhar.
- Entradas: botão "Explorar daqui" no detalhe da partida (posição atual),
  "Explorar" na ficha do erro e no resultado do puzzle.

## 5. Testes

- Backend: `PuzzleOut.mistake/siblings`; gerador "evitar" com engine falsa
  (linha que materializa gera puzzle de vários lances; melhor lance = lance
  jogado não gera; sem materialização não gera; mate); `regenerate?kind=avoid`
  preserva "punir" e suas revisões; `POST /api/analyse` (linhas, SAN, FEN
  inválido 400, cache, terminal).
- Frontend: `LineViewer` com `initialPos`; `useAnalysis` (play/undo/reset,
  ilegal ignorado); `api.analyse`.
- Manual: resolver um "evitar" novo; abrir Explorar do resultado, jogar a
  alternativa da partida, ver a avaliação cair, voltar.

## 6. Fora de escopo

Explicação em linguagem natural (fase futura com modelo de linguagem),
gráfico de avaliação, treino de erros posicionais.
