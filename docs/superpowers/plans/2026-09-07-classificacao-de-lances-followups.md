# Classificação de lances — pendências e decisões

Plano: `2026-09-07-classificacao-de-lances.md`. Itens levantados na revisão final do
branch `feat/classificacao-de-lances` que **não** foram corrigidos na rodada de
ajustes. Nada aqui é bloqueio de merge: são melhorias e riscos conhecidos.

## Pendências (não bloqueantes)

1. **Vaga liberada por erro sem teste** (`frontend/src/analysis/useMoveClassification.ts`):
   a janela de consultas em voo ignora as posições cuja consulta já falhou, senão
   uma engine indisponível travaria o resto do caminho (a consulta com erro não é
   reintentada). Nenhum teste cobre esse caminho — todos os testes da janela usam
   respostas pendentes ou resolvidas, e a regressão passaria em silêncio.
2. **Custo do `classify_moves: true` por padrão** (`backend/chess_trainer/config.py`):
   abrir um capítulo longo dispara, de saída, até 61 análises da engine (as 60
   últimas posições do caminho mais a de partida), duas por vez. A engine é local e
   serializa tudo, então o capítulo demora a ficar todo classificado e a máquina fica
   ocupada nesse meio-tempo. Vale medir num estudo de verdade antes de decidir se o
   padrão continua ligado (ou se o teto de 60 deveria ser menor).
3. **Selo do tabuleiro passa da borda** (`frontend/src/board/Board.tsx`,
   `.board-badge` em `frontend/src/styles/base.css`): o círculo é posicionado com
   `margin: -18% -18% 0 0` sobre a casa de destino, então em casas da última fileira
   ou da coluna h ele sai para fora do tabuleiro. Não corta (o contêiner não tem
   `overflow: hidden`), mas encosta na moldura e pode cobrir as coordenadas.
4. **Selos da árvore sem `role="img"`** (`frontend/src/analysis/MoveTreeView.tsx`):
   o selo é um `<span>` com o símbolo (`!!`, `?!`, `★`…) e o nome em português no
   `title`. Leitor de tela lê a pontuação solta e o `title` de um `span` sem papel
   não é anunciado de forma confiável; `role="img"` com `aria-label` resolveria.
   (O selo do tabuleiro é `aria-hidden`, de propósito: é decoração do mesmo dado.)
5. **FENs repetidas no mesmo caminho** (`useMoveClassification.ts`): um caminho que
   volta à mesma posição (repetição de lances) gera duas entradas de `useQueries`
   com a mesma chave. O React Query mantém uma consulta só — o resultado sai certo —,
   mas a janela conta as duas como se fossem posições diferentes e "gasta" vaga à toa.

## Decisões registradas

- **Janela de duas posições em voo** (`MAX_EM_VOO = 2`): a engine do servidor tem
  lock e resolve uma consulta por vez; uma janela maior só ocupava as conexões do
  navegador. As consultas saem da posição na tela para trás, que é a ordem em que
  interessam.
- **O teto de 60 meios-lances corta a cabeça do caminho**, não a cauda: o lance que
  está na tela é sempre classificado. A caminhada das FENs continua saindo da raiz,
  então as posições são as mesmas de `useAnalyse` (mesma chave de cache).
- **Mate como sacrifício**: o mate é o fim da linha, não há resposta do adversário
  para medir, e nenhum lance derruba o próprio material — a diferença "antes × depois
  da resposta" nunca acusaria sacrifício num mate. Por isso, quando o lance dá mate,
  a medida é a diferença de material na própria posição do mate: quem mata com 200 cp
  ou mais de desvantagem entregou o material nos lances de antes e o mate fecha o
  sacrifício ("brilhante"). Mate sem desvantagem material continua "melhor".
