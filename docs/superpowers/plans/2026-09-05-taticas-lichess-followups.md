# Táticas do Lichess — pendências e decisões

Plano: `2026-09-05-taticas-lichess.md`. Spec: `../specs/2026-09-05-taticas-lichess-design.md`.
Executado em janela de autonomia (usuário ausente, 2026-09-05/06) com subagentes e revisão por tarefa.

## Medições (arquivo real, 6,1 milhões de linhas, 304 MB)

| O quê | Valor |
|---|---|
| Importação completa (filtro 2000/90) | ~5,5 min, 1.056.428 táticas, banco +431 MB |
| Filtro antigo (200/60) | 3,93 milhões de táticas, banco de 1,6 GB (descartado) |
| `pick_next` (sorteio por ponto de rating, temas via EXISTS) | 4–30 ms; com tema, 20–150 ms dependendo da máquina |
| `pick_next` da versão inicial (`ORDER BY random()` na janela + `NOT IN`) | 1,7–4,3 s (substituída) |
| `theme_counts` / contagem total | em cache (`lichess_theme_counts`, `lichess_count`), atualizado ao fim de cada importação |

## Decisões registradas

- Padrão do filtro: mínimo 2000 partidas e popularidade 90 (spec atualizado).
- Rating: Elo simplificado K = 32, piso 400, teto 3200; acerto com dica conta como erro.
- Errados há mais de 1 dia voltam antes dos nunca vistos; errados há menos de 1 dia não voltam; corretos nunca voltam.
- Janela alarga de 100 em 100 até 1200 quando não há candidatos.
- Importação cancelada mantém os lotes já gravados e atualiza o cache de contagens; `lichess_imported_at` só é gravado em importação completa.
- Cancelar durante o download não é erro (job termina "cancelado", `.part` apagado).

## Pendências (não bloqueantes)

1. `download_file` não confere `done == total` antes de renomear o `.part`; um corpo truncado vira arquivo final. Auto-corrige na próxima execução (a comparação de tamanho no HEAD baixa de novo).
2. `tactics_rating` é editável em Configurações e também gravado a cada tentativa: salvar o formulário durante uma sessão de táticas sobrescreve o rating com o valor do formulário.
3. Validação do rating no formulário aceita 400–3200; o importador só guarda puzzles de 400–3000. Sem efeito prático (a janela alarga).
4. `TacticSession` refaz `GET /api/tactics/status` a cada tentativa (invalidação de `["tactics"]`), embora o rating do cabeçalho venha da resposta da tentativa após a primeira.
5. Painel faz duas requisições extras (`tactics/status`, `stats/themes`); erros nelas são silenciosos (os cartões somem, o resto renderiza).
6. Caminho de recurso do `pick_next` sem tema (`rating BETWEEN … ORDER BY random()`) ainda custa segundos, só se os 8 pontos de rating sorteados vierem vazios (faixas quase vazias, > 2900).
7. `exclude` na query string é limitado aos últimos 200 ids da sessão; uma tática vista há mais de 200 na mesma sessão pode voltar (só se ainda não foi resolvida).
8. Teste `tacticSession.test.tsx` usa um `setTimeout` real de 10 ms para o status resolver; se ficar instável, trocar por `waitFor`.
9. `test_analyze_single_game` (backend) oscilou uma vez por tempo durante a execução; passou nas outras 10+ rodadas.
10. Temas de abertura (`OpeningTags`) ficam guardados mas sem filtro na interface (fora de escopo).
11. ~~Spec §5 previa botão "limpar temas" na mensagem "sem candidatos"~~ — resolvido: o resumo mostra "Nova sessão sem temas" quando o motivo do fim é "nenhuma tática disponível".
12. O mapa de rótulos dos temas existe duas vezes (`core/tactics/themes.py` e
    `frontend/src/lib/format.ts`); `/api/tactics/themes` já devolve o `label`,
    então a tela poderia usar só ele (ou o backend poderia servir o mapa) em vez
    de manter as duas listas em sincronia na mão.
13. Não há como remover o banco de táticas importado (~430 MB no SQLite): sugerido
    um botão "remover banco de táticas" em Configurações, apagando
    `lichess_puzzles`/`lichess_puzzle_themes` e o cache de contagens (as tentativas
    e o rating ficam).
14. O download não retoma de onde parou: cancelar ou cair a rede apaga o `.part` e
    a próxima tentativa recomeça os ~300 MB do zero (falta `Range`/`If-Range`).
15. Os limites de `tactics_rating` (400–3200), `tactics_window` (≥ 50),
    `lichess_min_plays` (≥ 0) e `lichess_min_popularity` (−100 a 100) passaram a
    ser validados também no servidor (`SettingsIn`), não só no formulário.
