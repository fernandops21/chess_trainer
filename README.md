# Chess Trainer

Treino de xadrez a partir dos seus próprios erros: importa partidas do chess.com, analisa com Stockfish,
gera puzzles dos erros (seus e do adversário) e agenda com repetição espaçada.

## Rodar

    cd frontend && npm install && npm run build
    cd ../backend && uv sync && uv run python -m chess_trainer

Abra http://127.0.0.1:8000 (ou, no celular na mesma rede, o endereço mostrado em Configurações).
Stockfish: ver backend/README.md.

Tabuleiro de análise livre (`/analise`, com avaliação do Stockfish no backend): acessível pelo link
"Explorar" no resultado do treino (abre em nova aba, para não perder a sessão em andamento), pelo botão
"Explorar daqui" na partida e pelo botão "Explorar" na revisão de erros.

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

## Desenvolvimento

Backend: `cd backend && uv run python -m chess_trainer` (API em :8000, docs em /docs).
Frontend: `cd frontend && npm run dev` (Vite em :5173 com proxy para /api).
Testes: `cd backend && uv run pytest -q` · `cd frontend && npm test`.
