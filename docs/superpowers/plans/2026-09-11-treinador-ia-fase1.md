# Treinador com IA, fase 1 — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Botão "Explicar" na tela de resultado do exercício: um agente com LLM (ferramentas de engine, contexto, estatísticas e busca nos estudos) escreve a explicação em português, um verificador confere lances, avaliações e citações com o Stockfish, e tudo é medido por uma avaliação offline e rastreado no LangFuse.

**Architecture:** Pacote novo `backend/chess_trainer/coach/` com interface própria de cliente LLM (implementação com o SDK oficial da Anthropic, loop de ferramentas manual), RAG sobre os comentários dos capítulos (fastembed + sqlite-vec no mesmo SQLite, fallback numpy), verificador puro reutilizado pela avaliação, pipeline "contexto → agente → verificar → corrigir → gravar". Rota `/api/coach/*`, cartão "Treinador" no `ResultPanel`, seção em Configurações, pasta `backend/evals/coach/` para a avaliação, Dockerfile e Compose com LangFuse.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, python-chess, `anthropic>=1.5`, `fastembed>=0.8`, `sqlite-vec>=0.1.9`, `langfuse>=4`, numpy; React 19 + TypeScript + TanStack Query + Vitest; Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-11-treinador-ia-design.md` (leia antes de cada tarefa; as seções citadas abaixo são dele).

## Global Constraints

- Interface e mensagens em português; dizer **recriar**, nunca "regerar".
- A chave da API e a chave secreta do LangFuse nunca saem pela API (`*_set: bool`), como o token do Lichess.
- Agentes **nunca tocam em `backend/data/*`** (banco real, CSV do Lichess). Testes usam `:memory:`. A geração do conjunto de avaliação (`dataset/v1.json`) contra o banco real é feita pelo usuário.
- Nenhum texto de terceiros em fixtures, testes, capturas ou no conjunto de avaliação: só lances e texto sintético.
- O repositório é público: nada de menção a vagas, entrevistas ou "vitrine" em código, docs ou commits.
- Downloads exigem aviso prévio ao usuário: o modelo de embeddings (~250 MB) só é baixado pelo botão "Recriar índice"; as imagens do Compose (~2,5 GB) só no passo de verificação da Tarefa 14, combinado com o usuário.
- Backend: `cd backend && uv run pytest -q` (sem Stockfish real, sem rede; `-m "not slow and not network"` é o padrão do CI). Frontend: `cd frontend && npm test` e `npm run build` (o build roda `tsc --noEmit`).
- Python `>=3.12` (o ambiente é 3.13.12; `sqlite3` tem `enable_load_extension`).
- Commits em português com o trailer, via arquivo: `printf '...\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n' > "$TEMP/msg.txt" && git commit -F "$TEMP/msg.txt"`.
- Modelo padrão `claude-opus-5`; alternativa `claude-sonnet-5`. Usar só esses ids, sem sufixo de data.
- Pontos de vista de avaliação: `InteractiveAnalyzer.analyse` devolve `score` do **lado a mover**; o treinador e o verificador trabalham com **ponto de vista das brancas** e convertem na borda. Mate codificado como `±(MATE_SCORE - n)` (`core/evals.py`).

## Desvios do spec (decididos ao planejar; o usuário pode reverter)

- **Batch API** (§8.2) fica de fora da fase 1: a rodada completa (≈200 itens × 6 combinações) custa poucas dezenas de dólares e o código de lote dobraria o cliente. Se o custo pesar, vira tarefa própria.
- **Envio das rodadas como datasets do LangFuse** (§8.2) fica de fora: a saída oficial é `docs/coach-eval.md`; os traces de cada explicação continuam indo ao LangFuse. Entra como tarefa própria quando a API de datasets do SDK instalado for confirmada.
- `avaliacao_cp`/`mate_em` descrevem a posição no **fim** da linha (§5 dizia "posição final da linha" para a avaliação; `mate_em` segue a mesma regra, com 0 = termina em mate).

---

## Estrutura de arquivos

Backend (novo salvo indicação):

| arquivo | responsabilidade |
| --- | --- |
| `chess_trainer/coach/__init__.py` | vazio |
| `chess_trainer/coach/costs.py` | tabela de preços, `Uso`, `custo_usd` |
| `chess_trainer/coach/verify.py` | verificador puro (§5) |
| `chess_trainer/coach/retrieval/__init__.py` | vazio |
| `chess_trainer/coach/retrieval/chunks.py` | árvore do capítulo → `Trecho` (§6.1) |
| `chess_trainer/coach/retrieval/embeddings.py` | `Embeddings` (Protocol) + `FastembedEmbeddings` (§6.2) |
| `chess_trainer/coach/retrieval/store.py` | `VectorStore` (sqlite-vec / numpy) (§6.3) |
| `chess_trainer/coach/retrieval/index.py` | `Indexador`: indexar capítulo, recriar, status, buscar (§6.4) |
| `chess_trainer/coach/llm.py` | `LlmClient` (Protocol), `Ferramenta`, `ResultadoAgente`, `AnthropicClient`, `ErroDoTreinador` (§4.1) |
| `chess_trainer/coach/prompts.py` | `PROMPT_VERSION`, `SYSTEM_PROMPT`, `ESQUEMA_EXPLICACAO`, mensagens (§4.3, §4.4) |
| `chess_trainer/coach/tools.py` | `ContextoExercicio`, `contexto_do_exercicio`, `ferramentas_do_treinador` (§4.2) |
| `chess_trainer/coach/explain.py` | `explicar` (pipeline) e `gravar` (§7) |
| `chess_trainer/coach/observability.py` | `Tracer` (Protocol), `NoopTracer`, `LangfuseTracer`, `tracer_de` (§8.3) |
| `chess_trainer/api/routes/coach.py` | rotas `/api/coach/*` (§9) |
| `chess_trainer/core/models.py` (modificar) | `CoachChunk`, `CoachIndexedChapter`, `CoachExplanation` |
| `chess_trainer/core/db.py` (modificar) | carregar sqlite-vec na conexão; `vec_disponivel` |
| `chess_trainer/config.py`, `api/schemas.py`, `api/routes/system.py` (modificar) | campos novos de configuração |
| `chess_trainer/api/app.py` (modificar) | `coach_llm_factory`, `embeddings_factory`, `app.state.coach_*`, variáveis de ambiente |
| `chess_trainer/api/routes/studies.py` (modificar) | ganchos de indexação |
| `chess_trainer/core/analysis/engine.py` (modificar) | `STOCKFISH_PATH` |
| `evals/__init__.py`, `evals/coach/{__init__,dataset,run,metrics,judge,report}.py` | avaliação offline (§8) |
| `tests/fakes.py` (modificar) | `FakeLlm`, `EmbeddingsFalso`, `FakeTracer` |
| `tests/factories.py` (modificar) | `make_puzzle(..., solution=)` |
| `tests/test_coach_*.py`, `tests/test_api_coach.py`, `tests/test_coach_eval.py` | testes |

Frontend: `src/api/types.ts`, `src/api/client.ts`, `src/api/queries.ts` (modificar); `src/train/CoachCard.tsx` (novo); `src/train/ResultPanel.tsx`, `src/pages/SettingsPage.tsx` (modificar); `tests/coachCard.test.tsx` (novo), `tests/resultPanel.test.tsx`, `tests/settingsPage.test.tsx`, `tests/settings.test.ts` (modificar).

Raiz: `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `docker/langfuse.compose.yml`, `.env.example`, `.gitignore` (modificar), `docs/manual.pt-BR.md` e `README.md` (modificar).

---

### Task 1: Dependências, configurações e tabela de custos

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/chess_trainer/config.py`
- Modify: `backend/chess_trainer/api/schemas.py` (`SettingsOut`, `SettingsIn`)
- Modify: `backend/chess_trainer/api/routes/system.py` (`_settings_out`)
- Create: `backend/chess_trainer/coach/__init__.py`, `backend/chess_trainer/coach/costs.py`
- Test: `backend/tests/test_coach_costs.py`, `backend/tests/test_api_system.py` (acrescentar)

**Interfaces:**
- Produces: `AppSettings.anthropic_api_key: str`, `coach_model: str`, `coach_effort: str`, `langfuse_public_key: str`, `langfuse_secret_key: str`, `langfuse_host: str`; `coach.costs.Uso` (dataclass frozen com `input_tokens, output_tokens, cache_read_tokens, cache_write_tokens`, `__add__`, `to_dict()`), `coach.costs.custo_usd(model: str, uso: Uso) -> float`, `coach.costs.MODELOS: tuple[str, ...]`, `coach.costs.EFFORTS = ("low", "medium", "high")`.

- [ ] **Step 1: Adicionar as dependências** (baixa pacotes; o usuário autorizou ao aprovar o plano)

```bash
cd backend && uv add "anthropic>=1.5" "fastembed>=0.8" "sqlite-vec>=0.1.9" "langfuse>=4" "numpy>=1.26"
uv run python -c "import anthropic, fastembed, sqlite_vec, langfuse, numpy; print('ok')"
```

- [ ] **Step 2: Teste de custos (falhando)**

`backend/tests/test_coach_costs.py`:

```python
from chess_trainer.coach.costs import EFFORTS, MODELOS, Uso, custo_usd


def test_uso_soma_e_serializa():
    total = Uso(100, 10, 50, 5) + Uso(1, 2, 3, 4)
    assert total == Uso(101, 12, 53, 9)
    assert total.to_dict() == {"input": 101, "output": 12, "cache_read": 53, "cache_write": 9}


def test_custo_opus_5_na_tabela_oficial():
    # 1M de entrada + 1M de saída no Opus 5 = 5 + 25 dólares
    assert custo_usd("claude-opus-5", Uso(1_000_000, 1_000_000, 0, 0)) == 30.0
    # leitura de cache é 10% da entrada; escrita 5 min é 125%
    assert custo_usd("claude-opus-5", Uso(0, 0, 1_000_000, 0)) == 0.5
    assert custo_usd("claude-opus-5", Uso(0, 0, 0, 1_000_000)) == 6.25


def test_custo_sonnet_5_e_modelo_desconhecido():
    assert custo_usd("claude-sonnet-5", Uso(1_000_000, 1_000_000, 0, 0)) == 12.0
    assert custo_usd("fake", Uso(1000, 1000, 0, 0)) == 0.0
    assert "claude-opus-5" in MODELOS and "claude-sonnet-5" in MODELOS
    assert EFFORTS == ("low", "medium", "high")
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `cd backend && uv run pytest tests/test_coach_costs.py -q`
Expected: FAIL com `ModuleNotFoundError: chess_trainer.coach`

- [ ] **Step 4: Implementar `costs.py`**

`backend/chess_trainer/coach/__init__.py`: vazio.

`backend/chess_trainer/coach/costs.py`:

```python
"""Preços dos modelos em dólares por milhão de tokens.

Copiados da página de preços da Anthropic (platform.claude.com/docs/en/about-claude/pricing)
em 2026-09-11. Quando mudarem, muda aqui e a data."""
from dataclasses import dataclass

PRECOS_LIDOS_EM = "2026-09-11"


@dataclass(frozen=True)
class Preco:
    entrada: float
    escrita_cache: float  # cache de 5 minutos: 1,25x a entrada
    leitura_cache: float  # 0,1x a entrada
    saida: float


PRECOS: dict[str, Preco] = {
    "claude-opus-5": Preco(5.0, 6.25, 0.50, 25.0),
    "claude-sonnet-5": Preco(2.0, 2.50, 0.20, 10.0),
}
MODELOS: tuple[str, ...] = tuple(PRECOS)
MODELO_PADRAO = "claude-opus-5"
EFFORTS: tuple[str, ...] = ("low", "medium", "high")


@dataclass(frozen=True)
class Uso:
    """Tokens de uma ou mais chamadas à API, somáveis."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, outro: "Uso") -> "Uso":
        return Uso(
            self.input_tokens + outro.input_tokens,
            self.output_tokens + outro.output_tokens,
            self.cache_read_tokens + outro.cache_read_tokens,
            self.cache_write_tokens + outro.cache_write_tokens,
        )

    def to_dict(self) -> dict:
        return {"input": self.input_tokens, "output": self.output_tokens,
                "cache_read": self.cache_read_tokens, "cache_write": self.cache_write_tokens}


def custo_usd(model: str, uso: Uso) -> float:
    """Custo em dólares; modelo fora da tabela (fakes de teste) custa zero."""
    p = PRECOS.get(model)
    if p is None:
        return 0.0
    total = (uso.input_tokens * p.entrada + uso.cache_write_tokens * p.escrita_cache
             + uso.cache_read_tokens * p.leitura_cache + uso.output_tokens * p.saida)
    return round(total / 1_000_000, 6)
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd backend && uv run pytest tests/test_coach_costs.py -q`
Expected: 3 passed

- [ ] **Step 6: Teste das configurações (falhando)** — acrescentar em `backend/tests/test_api_system.py`:

```python
def test_configuracoes_do_treinador_nunca_ecoam_segredos(client):
    inicial = client.get("/api/settings").json()
    assert inicial["anthropic_api_key_set"] is False and "anthropic_api_key" not in inicial
    assert inicial["coach_model"] == "claude-opus-5" and inicial["coach_effort"] == "high"
    assert inicial["langfuse_secret_key_set"] is False and inicial["langfuse_host"] == ""

    body = client.put("/api/settings", json={
        "anthropic_api_key": "  sk-ant-segredo  ", "coach_model": "claude-sonnet-5", "coach_effort": "medium",
        "langfuse_public_key": "pk-lf-1", "langfuse_secret_key": "sk-lf-2", "langfuse_host": "http://localhost:3000/",
    }).json()
    assert body["anthropic_api_key_set"] is True and body["langfuse_secret_key_set"] is True
    assert body["coach_model"] == "claude-sonnet-5" and body["coach_effort"] == "medium"
    assert body["langfuse_public_key"] == "pk-lf-1" and body["langfuse_host"] == "http://localhost:3000"
    texto = client.get("/api/settings").text
    assert "sk-ant-segredo" not in texto and "sk-lf-2" not in texto

    # alteração sem os campos mantém as chaves; string vazia apaga
    assert client.put("/api/settings", json={"new_per_day": 3}).json()["anthropic_api_key_set"] is True
    assert client.put("/api/settings", json={"anthropic_api_key": ""}).json()["anthropic_api_key_set"] is False
    # modelo e esforço fora da lista são recusados
    assert client.put("/api/settings", json={"coach_model": "gpt-9"}).status_code == 422
    assert client.put("/api/settings", json={"coach_effort": "max"}).status_code == 422
```

- [ ] **Step 7: Rodar e ver falhar**

Run: `cd backend && uv run pytest tests/test_api_system.py -q -k treinador`
Expected: FAIL (`KeyError: 'anthropic_api_key_set'`)

- [ ] **Step 8: Implementar os campos**

Em `config.py`, no fim de `AppSettings`:

```python
    # --- treinador com IA (spec 2026-09-11) ---
    # chave da API da Anthropic: só neste banco, nunca sai pela API
    anthropic_api_key: str = ""
    coach_model: str = "claude-opus-5"
    coach_effort: str = "high"
    # LangFuse (observabilidade): host vazio = desligado; a chave secreta nunca sai pela API
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""
```

Em `save_settings`, depois da linha do `lichess_token`:

```python
    settings.anthropic_api_key = settings.anthropic_api_key.strip()
    settings.langfuse_public_key = settings.langfuse_public_key.strip()
    settings.langfuse_secret_key = settings.langfuse_secret_key.strip()
    settings.langfuse_host = settings.langfuse_host.strip().rstrip("/")
```

Em `schemas.py`, `SettingsOut` ganha:

```python
    # treinador com IA: os segredos viram sim/não
    anthropic_api_key_set: bool
    coach_model: str
    coach_effort: str
    langfuse_public_key: str
    langfuse_secret_key_set: bool
    langfuse_host: str
```

e `SettingsIn`:

```python
    anthropic_api_key: str | None = None
    coach_model: Literal["claude-opus-5", "claude-sonnet-5"] | None = None
    coach_effort: Literal["low", "medium", "high"] | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str | None = None
```

Em `routes/system.py`, `_settings_out`:

```python
def _settings_out(settings: AppSettings) -> dict:
    """Configurações como a API as devolve: cada segredo vira um sim/não.

    Os valores não podem sair daqui em resposta nenhuma — quem configurou já os
    tem, e a tela só precisa saber se há algo guardado."""
    data = asdict(settings)
    data["lichess_token_set"] = bool(data.pop("lichess_token", ""))
    data["anthropic_api_key_set"] = bool(data.pop("anthropic_api_key", ""))
    data["langfuse_secret_key_set"] = bool(data.pop("langfuse_secret_key", ""))
    return data
```

- [ ] **Step 9: Rodar tudo e ver passar**

Run: `cd backend && uv run pytest -q`
Expected: tudo verde (os testes antigos de configurações continuam passando).

- [ ] **Step 10: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/chess_trainer/coach backend/chess_trainer/config.py backend/chess_trainer/api/schemas.py backend/chess_trainer/api/routes/system.py backend/tests/test_coach_costs.py backend/tests/test_api_system.py
printf 'feat(treinador): dependências, configurações da IA e tabela de custos\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n' > "$TEMP/msg.txt" && git commit -F "$TEMP/msg.txt"
```

---

### Task 2: Verificador (`verify.py`)

**Files:**
- Create: `backend/chess_trainer/coach/verify.py`
- Test: `backend/tests/test_coach_verify.py`

**Interfaces:**
- Consumes: `core.evals.MATE_SCORE, is_mate, mate_in`.
- Produces: `Issue(tipo, gravidade, detalhe, linha_idx=None)` (frozen), `Verificacao(issues)` com `.ok`, `.erros` (contagem), `.avisos`, `.to_dict() -> {"ok", "issues": [...]}`; `Analisar = Callable[[str, int], dict]` (fen, multipv → dict no formato de `InteractiveAnalyzer.analyse`); `verificar(resposta: dict, *, fen_inicial: str, fen_erro: str | None, lances_permitidos: set[str], trechos_ids: set[str], analisar: Analisar) -> Verificacao`; `limpar_san(san) -> str`; `SAN_RE`, `CITACAO_RE`.
- Convenção: `avaliacao_cp` e `mate_em` da resposta descrevem a posição **no fim da linha**, ponto de vista das brancas; `mate_em = 0` quer dizer que a linha termina em mate.

- [ ] **Step 1: Testes (falhando)**

`backend/tests/test_coach_verify.py`:

```python
import chess
import pytest

from chess_trainer.coach.verify import SAN_RE, Verificacao, limpar_san, verificar
from chess_trainer.core.evals import MATE_SCORE

# brancas a jogar: Qxf7# é mate; Nf3 e a3 são lances normais
FEN = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
# posição "do erro": as pretas acabaram de jogar Nf6?? (a mesma FEN serve de exemplo)
FEN_ERRO = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3"
TEXTO_OK = " ".join(["palavra"] * 80)


def analisar_script(fen: str, multipv: int) -> dict:
    """Engine de mentira: na posição inicial, Qxf7# > Bxf7+ > Nf3; nas outras, um lance qualquer com +0,40 para quem move."""
    board = chess.Board(fen)
    if board.is_checkmate() or board.is_game_over():
        return {"fen": fen, "turn": "white" if board.turn else "black", "terminal": "checkmate", "lines": []}
    if board.fen() == chess.Board(FEN).fen():
        lines = [{"move": "h5f7", "san": "Qxf7#", "score": MATE_SCORE - 1, "pv": ["h5f7"], "pv_san": ["Qxf7#"]},
                 {"move": "c4f7", "san": "Bxf7+", "score": 300, "pv": ["c4f7"], "pv_san": ["Bxf7+"]},
                 {"move": "g1f3", "san": "Nf3", "score": 40, "pv": ["g1f3"], "pv_san": ["Nf3"]}]
        return {"fen": fen, "turn": "white", "terminal": None, "lines": lines[:multipv]}
    mv = next(iter(board.legal_moves))
    return {"fen": fen, "turn": "white" if board.turn else "black", "terminal": None,
            "lines": [{"move": mv.uci(), "san": board.san(mv), "score": 40, "pv": [mv.uci()], "pv_san": [board.san(mv)]}]}


def tipos(v: Verificacao) -> set[str]:
    return {i.tipo for i in v.issues}


def checar(resposta, **kw):
    base = dict(fen_inicial=FEN, fen_erro=FEN_ERRO, lances_permitidos=set(), trechos_ids=set(), analisar=analisar_script)
    base.update(kw)
    return verificar(resposta, **base)


def test_limpar_san_e_regex():
    assert limpar_san("Qxf7#!") == "Qxf7" and limpar_san("O-O-O+") == "O-O-O" and limpar_san("e8=Q+?!") == "e8=Q"
    achados = [m.group(0) for m in SAN_RE.finditer("Depois de 4.Qxf7# acabou; já Nc3x não é lance, e Qd1-h5 tampouco.")]
    assert achados == ["Qxf7#"]


def test_linha_legal_e_principal_passa():
    v = checar({"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["Qxf7#"], "avaliacao_cp": None, "mate_em": 0}], "citacoes": []})
    assert v.ok and tipos(v) == set()


def test_lance_ilegal_e_erro():
    v = checar({"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["Qxf8"]}]})
    assert not v.ok and tipos(v) == {"lance_ilegal"} and v.issues[0].linha_idx == 0


def test_fora_das_principais_e_aviso_salvo_lance_permitido():
    resposta = {"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["a3"]}]}
    v = checar(resposta)
    assert v.ok and tipos(v) == {"lance_fora_das_principais"}
    v2 = checar(resposta, lances_permitidos={"a2a3"})
    assert tipos(v2) == set()


def test_linha_a_partir_da_posicao_do_erro():
    # das pretas: Nf6 é legal em FEN_ERRO e ilegal em FEN (é a vez das brancas)
    v = checar({"texto": TEXTO_OK, "linhas": [{"inicio": "erro", "lances": ["Nf6", "Qxf7#"], "mate_em": 0}]})
    assert "lance_ilegal" not in tipos(v)
    v2 = checar({"texto": TEXTO_OK, "linhas": [{"inicio": "erro", "lances": ["Nf6"]}]}, fen_erro=None)
    assert "lance_ilegal" in tipos(v2)


def test_avaliacao_conferida_com_tolerancia_de_um_peao():
    # depois de Nf3 é a vez das pretas: a engine dá +0,40 para quem move (pretas) = -0,40 para as brancas
    ok = checar({"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["Nf3"], "avaliacao_cp": -30}]})
    assert "avaliacao_errada" not in tipos(ok)
    ruim = checar({"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["Nf3"], "avaliacao_cp": 300}]})
    assert not ruim.ok and "avaliacao_errada" in tipos(ruim)


def test_mate_declarado_confere_com_a_engine():
    assert checar({"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["Qxf7#"], "mate_em": 0}]}).ok
    errado = checar({"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["Qxf7#"], "mate_em": 2}]})
    assert not errado.ok and "avaliacao_errada" in tipos(errado)
    # avaliação numérica onde a engine dá mate: aviso, não erro
    numerica = checar({"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["Qxf7#"], "avaliacao_cp": 900}]})
    assert numerica.ok and "avaliacao_errada" in tipos(numerica)


def test_lance_solto_no_texto_e_aviso():
    v = checar({"texto": TEXTO_OK + " O lance Nc6 defende.", "linhas": [{"inicio": "inicial", "lances": ["Qxf7#"], "mate_em": 0}]})
    assert v.ok and "lance_sem_linha" in tipos(v)
    v2 = checar({"texto": TEXTO_OK + " O lance Qxf7# decide.", "linhas": [{"inicio": "inicial", "lances": ["Qxf7#"], "mate_em": 0}]})
    assert "lance_sem_linha" not in tipos(v2)


def test_citacoes():
    ok = checar({"texto": TEXTO_OK + " Veja [c:ab12] no estudo.", "linhas": [], "citacoes": ["ab12"]}, trechos_ids={"ab12"})
    assert ok.ok and "citacao_inexistente" not in tipos(ok) and "citacao_ausente" not in tipos(ok)
    falsa = checar({"texto": TEXTO_OK + " Veja [c:zz99].", "linhas": []}, trechos_ids={"ab12"})
    assert not falsa.ok and "citacao_inexistente" in tipos(falsa)
    sem = checar({"texto": TEXTO_OK + " Como aparece no capítulo três.", "linhas": []})
    assert sem.ok and "citacao_ausente" in tipos(sem)


def test_tamanho_do_texto():
    assert "tamanho" in tipos(checar({"texto": "curto demais", "linhas": []}))
    assert "tamanho" in tipos(checar({"texto": " ".join(["x"] * 401), "linhas": []}))
    assert "tamanho" not in tipos(checar({"texto": TEXTO_OK, "linhas": []}))


def test_engine_fora_do_ar_vira_erro_visivel():
    def quebrada(fen, multipv):
        raise RuntimeError("engine indisponível")
    v = verificar({"texto": TEXTO_OK, "linhas": [{"inicio": "inicial", "lances": ["Nf3"], "avaliacao_cp": 0}]},
                  fen_inicial=FEN, fen_erro=None, lances_permitidos=set(), trechos_ids=set(), analisar=quebrada)
    assert not v.ok and tipos(v) == {"engine_indisponivel"}
    assert v.to_dict()["ok"] is False and v.to_dict()["issues"][0]["tipo"] == "engine_indisponivel"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && uv run pytest tests/test_coach_verify.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 3: Implementar `verify.py`**

```python
"""Verificador da explicação do treinador.

Cada linha citada é reproduzida no tabuleiro a partir da posição declarada,
o primeiro lance é conferido com as três melhores da engine, a avaliação do
fim da linha é comparada com a da engine e cada citação de estudo tem de
existir entre os trechos recuperados. Puro: recebe a função de análise e não
toca em banco nem rede, o que permite reusá-lo na avaliação offline."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Callable

import chess

from chess_trainer.core.evals import MATE_SCORE, is_mate, mate_in

# (fen, multipv) -> dict no formato de `InteractiveAnalyzer.analyse`
Analisar = Callable[[str, int], dict]

# a mesma expressão do `moveText.ts` do frontend, sem o número do lance
SAN_RE = re.compile(
    r"(?<![A-Za-z0-9-])(?:O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x?[a-h]?[1-8](?:=[QRBN])?)[+#]?(?![A-Za-z0-9-])"
)
CITACAO_RE = re.compile(r"\[c:([^\]\s]+)\]")
MENCAO_ESTUDO_RE = re.compile(r"\b(?:no|na|nos|nas|do|da|dos|das)\s+(?:estudo|cap[ií]tulo|livro)s?\b", re.IGNORECASE)
TOLERANCIA_CP = 100
MIN_PALAVRAS, MAX_PALAVRAS = 60, 400


@dataclass(frozen=True)
class Issue:
    tipo: str
    gravidade: str  # "erro" | "aviso"
    detalhe: str
    linha_idx: int | None = None


@dataclass
class Verificacao:
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.gravidade == "erro" for i in self.issues)

    @property
    def erros(self) -> int:
        return sum(1 for i in self.issues if i.gravidade == "erro")

    @property
    def avisos(self) -> int:
        return sum(1 for i in self.issues if i.gravidade == "aviso")

    def to_dict(self) -> dict:
        return {"ok": self.ok, "issues": [asdict(i) for i in self.issues]}


def limpar_san(san: str) -> str:
    """Tira apreciação e xeque/mate: `Qxf7#!` -> `Qxf7`."""
    return san.strip().replace("!", "").replace("?", "").rstrip("+#")


def _fmt(score: int) -> str:
    n = mate_in(score)
    if n is not None:
        return f"mate em {n}" if score > 0 else f"mate em {n} contra"
    return f"{score / 100:+.2f}"


def _score_brancas(board: chess.Board, analise: dict) -> int | None:
    """Avaliação do ponto de vista das brancas; o analisador dá a do lado a mover."""
    if board.is_checkmate():
        stm = -MATE_SCORE
    elif board.is_game_over():
        stm = 0
    else:
        lines = analise.get("lines") or []
        if not lines:
            return None
        stm = int(lines[0]["score"])
    return stm if board.turn == chess.WHITE else -stm


def verificar(resposta: dict, *, fen_inicial: str, fen_erro: str | None, lances_permitidos: set[str],
              trechos_ids: set[str], analisar: Analisar) -> Verificacao:
    v = Verificacao()
    texto = str(resposta.get("texto") or "")
    linhas = resposta.get("linhas") or []
    lances_em_linhas: set[str] = set()

    for idx, linha in enumerate(linhas):
        inicio = linha.get("inicio", "inicial")
        fen = fen_erro if inicio == "erro" and fen_erro else fen_inicial
        lances = [str(l) for l in (linha.get("lances") or [])]
        lances_em_linhas.update(limpar_san(l) for l in lances)
        board = chess.Board(fen)

        # 1. legalidade: reproduz a linha inteira
        jogados: list[chess.Move] = []
        ilegal: str | None = None
        for san in lances:
            try:
                mv = board.parse_san(limpar_san(san))
            except ValueError:
                ilegal = san
                break
            jogados.append(mv)
            board.push(mv)
        if ilegal is not None:
            v.issues.append(Issue("lance_ilegal", "erro", f"'{ilegal}' não é legal na posição declarada", idx))
            continue
        if not jogados:
            continue

        # 2. aderência: o primeiro lance está entre as três melhores, ou é um lance do exercício
        try:
            analise = analisar(fen, 3)
        except Exception as exc:  # noqa: BLE001 - engine fora do ar vira issue, não exceção
            v.issues.append(Issue("engine_indisponivel", "erro", f"sem engine para conferir a linha: {exc}", idx))
            continue
        principais = [str(l.get("san", "")) for l in analise.get("lines") or []]
        if not any(limpar_san(lances[0]) == limpar_san(s) for s in principais) and jogados[0].uci() not in lances_permitidos:
            v.issues.append(Issue("lance_fora_das_principais", "aviso",
                                  f"'{lances[0]}' não está entre as três melhores da engine nem é um lance do exercício", idx))

        # 3. avaliação no fim da linha
        aval = linha.get("avaliacao_cp")
        mate = linha.get("mate_em")
        if aval is None and mate is None:
            continue
        try:
            final = analisar(board.fen(), 1)
        except Exception as exc:  # noqa: BLE001
            v.issues.append(Issue("engine_indisponivel", "erro", f"sem engine para conferir a avaliação: {exc}", idx))
            continue
        score = _score_brancas(board, final)
        if score is None:
            v.issues.append(Issue("engine_indisponivel", "erro", "a engine não devolveu avaliação para o fim da linha", idx))
        elif mate is not None:
            n = mate_in(score)
            if n is None or n != int(mate):
                v.issues.append(Issue("avaliacao_errada", "erro", f"a explicação diz mate em {mate}; a engine dá {_fmt(score)}", idx))
        elif is_mate(score):
            v.issues.append(Issue("avaliacao_errada", "aviso", f"a engine dá {_fmt(score)} onde a explicação dá {int(aval) / 100:+.2f}", idx))
        elif abs(score - int(aval)) > TOLERANCIA_CP:
            v.issues.append(Issue("avaliacao_errada", "erro", f"a explicação dá {int(aval) / 100:+.2f}; a engine dá {score / 100:+.2f}", idx))

    # 4. lances soltos no texto
    for m in SAN_RE.finditer(texto):
        if limpar_san(m.group(0)) not in lances_em_linhas:
            v.issues.append(Issue("lance_sem_linha", "aviso", f"'{m.group(0)}' aparece no texto sem estar em nenhuma linha"))

    # 5. citações
    citadas = set(CITACAO_RE.findall(texto)) | {str(c) for c in (resposta.get("citacoes") or [])}
    for cid in sorted(citadas):
        if cid not in trechos_ids:
            v.issues.append(Issue("citacao_inexistente", "erro", f"a citação '{cid}' não está entre os trechos recuperados"))
    if not citadas and MENCAO_ESTUDO_RE.search(texto):
        v.issues.append(Issue("citacao_ausente", "aviso", "o texto menciona um estudo sem citar o trecho"))

    # 6. tamanho
    n = len(texto.split())
    if n < MIN_PALAVRAS or n > MAX_PALAVRAS:
        v.issues.append(Issue("tamanho", "aviso", f"{n} palavras (esperado entre {MIN_PALAVRAS} e {MAX_PALAVRAS})"))
    return v
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && uv run pytest tests/test_coach_verify.py -q`
Expected: 11 passed. Se `test_lance_solto_no_texto_e_aviso` falhar por causa de "palavra" casando com a regex, não casa (não é SAN); se falhar por outro motivo, corrija a regex, não o teste.

- [ ] **Step 5: Commit**

```bash
git add backend/chess_trainer/coach/verify.py backend/tests/test_coach_verify.py
printf 'feat(treinador): verificador de lances, avaliações e citações\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n' > "$TEMP/msg.txt" && git commit -F "$TEMP/msg.txt"
```

---

### Task 3: Trechos dos capítulos (`retrieval/chunks.py`)

**Files:**
- Create: `backend/chess_trainer/coach/retrieval/__init__.py`, `backend/chess_trainer/coach/retrieval/chunks.py`
- Test: `backend/tests/test_coach_chunks.py`

**Interfaces:**
- Consumes: `core.studies.tree.move_of(board, node) -> chess.Move`.
- Produces: `Trecho(key: str, chapter_id: str, node_id: str | None, kind: str, text: str, comment: str, fen: str, path_san: str, ply: int, content_hash: str)` (frozen); `trechos_do_capitulo(chapter_id: str, estudo: str, capitulo: str, tree: dict) -> list[Trecho]`; constantes `MIN_CHARS = 40`, `MAX_CHARS = 1200`. `key` tem 10 caracteres hexadecimais e é estável para o mesmo (capítulo, nó, tipo, parte); `content_hash` são 16 hexadecimais do `text`.

- [ ] **Step 1: Testes (falhando)**

`backend/tests/test_coach_chunks.py`:

```python
import chess

from chess_trainer.coach.retrieval.chunks import MAX_CHARS, Trecho, trechos_do_capitulo

LONGO = " ".join(f"Frase número {i} sobre a cravada na coluna e." for i in range(80))  # > 2 * MAX_CHARS


def arvore():
    return {
        "fen": chess.STARTING_FEN, "orientation": "white",
        "intro": "Capítulo sintético sobre a abertura italiana.",
        "root": {"shapes": [], "children": [
            {"id": "n1", "uci": "e2e4", "san": "e4", "comment": "", "children": [
                {"id": "n2", "uci": "e7e5", "san": "e5", "comment": "A resposta clássica, simétrica e sólida.", "children": [
                    {"id": "n3", "uci": "g1f3", "san": "Nf3", "comment": "Ataca e5.", "children": []},
                    {"id": "n4", "uci": "f1c4", "san": "Bc4", "comment": "A variação do bispo mira f7 desde cedo, tema recorrente.", "children": []},
                ]},
            ]},
            {"id": "n5", "uci": "d2d4", "san": "d4", "comment": LONGO, "children": []},
        ]},
    }


def test_intro_e_comentarios_viram_trechos_com_caminho():
    ts = trechos_do_capitulo("cap-1", "Aberturas", "Italiana", arvore())
    por_no = {t.node_id: t for t in ts if t.kind == "comment" and t.node_id != "n5"}
    intro = [t for t in ts if t.kind == "intro"]
    assert len(intro) == 1 and intro[0].node_id is None and intro[0].ply == 0
    assert intro[0].text == "Aberturas — Italiana: Capítulo sintético sobre a abertura italiana."
    assert por_no["n2"].path_san == "1.e4 e5" and por_no["n2"].ply == 2
    assert por_no["n2"].fen == chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2").fen()
    assert por_no["n4"].path_san == "1.e4 e5 2.Bc4"
    assert por_no["n4"].text.startswith("Aberturas — Italiana — 1.e4 e5 2.Bc4: A variação do bispo")
    assert por_no["n4"].comment == "A variação do bispo mira f7 desde cedo, tema recorrente."


def test_comentario_curto_e_juntado_ao_anterior_do_mesmo_ramo():
    ts = trechos_do_capitulo("cap-1", "Aberturas", "Italiana", arvore())
    assert not any(t.node_id == "n3" for t in ts)          # "Ataca e5." tem menos de 40 caracteres
    n2 = next(t for t in ts if t.node_id == "n2")
    assert n2.comment == "A resposta clássica, simétrica e sólida. Ataca e5."


def test_comentario_longo_e_partido_em_frases():
    ts = [t for t in trechos_do_capitulo("cap-1", "Aberturas", "Italiana", arvore()) if t.node_id == "n5"]
    assert len(ts) >= 3 and all(len(t.text) <= MAX_CHARS + 60 for t in ts)
    assert all(t.path_san == "1.d4" for t in ts)
    assert len({t.key for t in ts}) == len(ts)


def test_chaves_e_hash_estaveis():
    a = trechos_do_capitulo("cap-1", "Aberturas", "Italiana", arvore())
    b = trechos_do_capitulo("cap-1", "Aberturas", "Italiana", arvore())
    assert [t.key for t in a] == [t.key for t in b] and [t.content_hash for t in a] == [t.content_hash for t in b]
    assert all(len(t.key) == 10 and len(t.content_hash) == 16 for t in a)
    outro = trechos_do_capitulo("cap-2", "Aberturas", "Italiana", arvore())
    assert {t.key for t in outro}.isdisjoint({t.key for t in a})


def test_arvore_sem_comentarios_nao_gera_nada():
    vazia = {"fen": chess.STARTING_FEN, "orientation": "white", "intro": "", "root": {"children": [{"id": "n1", "uci": "e2e4", "san": "e4", "comment": "", "children": []}]}}
    assert trechos_do_capitulo("c", "E", "C", vazia) == []


def test_lance_ilegal_na_arvore_interrompe_so_aquele_ramo():
    t = arvore()
    t["root"]["children"][0]["children"][0]["uci"] = "e7e4"  # ilegal
    ts = trechos_do_capitulo("cap-1", "Aberturas", "Italiana", t)
    assert {x.node_id for x in ts if x.kind == "comment"} == {"n5"}
    assert isinstance(ts[0], Trecho)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && uv run pytest tests/test_coach_chunks.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 3: Implementar**

`backend/chess_trainer/coach/retrieval/__init__.py`: vazio.

`backend/chess_trainer/coach/retrieval/chunks.py`:

```python
"""Árvore de um capítulo -> trechos indexáveis (spec §6.1).

Um trecho por enunciado e por comentário de nó, com a posição (FEN), o
caminho de lances desde a raiz e o texto indexado com um cabeçalho
"estudo — capítulo — caminho" (ajuda a busca por nome de abertura).
Comentários curtos são juntados ao trecho anterior do mesmo ramo; longos são
partidos em frases. Puro: só recebe a árvore."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import chess

from chess_trainer.core.studies.tree import move_of

MIN_CHARS = 40
MAX_CHARS = 1200
_FRASE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Trecho:
    key: str
    chapter_id: str
    node_id: str | None
    kind: str  # "intro" | "comment"
    text: str
    comment: str
    fen: str
    path_san: str
    ply: int
    content_hash: str


def _partir(texto: str) -> list[str]:
    if len(texto) <= MAX_CHARS:
        return [texto]
    partes: list[str] = []
    atual = ""
    for frase in _FRASE.split(texto):
        if atual and len(atual) + 1 + len(frase) > MAX_CHARS:
            partes.append(atual)
            atual = frase
        else:
            atual = f"{atual} {frase}".strip()
    if atual:
        partes.append(atual)
    return partes


def _chave(chapter_id: str, node_id: str | None, kind: str, parte: int) -> str:
    return hashlib.sha1(f"{chapter_id}|{node_id or ''}|{kind}|{parte}".encode()).hexdigest()[:10]


def trechos_do_capitulo(chapter_id: str, estudo: str, capitulo: str, tree: dict) -> list[Trecho]:
    cabecalho = f"{estudo} — {capitulo}"
    # rascunhos mutáveis: a junção de comentários curtos altera o anterior
    rascunhos: list[dict] = []
    intro = str(tree.get("intro") or "").strip()
    fen0 = str(tree.get("fen") or chess.STARTING_FEN)
    if intro:
        rascunhos.append({"node_id": None, "kind": "intro", "comment": intro, "fen": fen0, "path_san": "", "ply": 0})

    def percorrer(node: dict, board: chess.Board, caminho: list[str], anterior: int | None) -> None:
        for filho in node.get("children") or []:
            if not isinstance(filho, dict):
                continue
            b = board.copy()
            try:
                mv = move_of(b, filho)
            except ValueError:
                continue  # ramo com lance ilegal: fica de fora
            san = b.san(mv)
            numero = b.fullmove_number
            token = f"{numero}.{san}" if b.turn == chess.WHITE else (f"{numero}...{san}" if not caminho else san)
            b.push(mv)
            novo_caminho = caminho + [token]
            comentario = str(filho.get("comment") or "").strip()
            atual = anterior
            if comentario:
                if len(comentario) < MIN_CHARS and anterior is not None:
                    rascunhos[anterior]["comment"] = f"{rascunhos[anterior]['comment']} {comentario}"
                else:
                    rascunhos.append({"node_id": str(filho.get("id") or ""), "kind": "comment", "comment": comentario,
                                      "fen": b.fen(), "path_san": " ".join(novo_caminho), "ply": len(novo_caminho)})
                    atual = len(rascunhos) - 1
            percorrer(filho, b, novo_caminho, atual)

    percorrer(tree.get("root") or {}, chess.Board(fen0), [], None)

    out: list[Trecho] = []
    for r in rascunhos:
        prefixo = f"{cabecalho} — {r['path_san']}" if r["path_san"] else cabecalho
        for i, parte in enumerate(_partir(r["comment"])):
            text = f"{prefixo}: {parte}"
            out.append(Trecho(
                key=_chave(chapter_id, r["node_id"], r["kind"], i), chapter_id=chapter_id, node_id=r["node_id"],
                kind=r["kind"], text=text, comment=parte, fen=r["fen"], path_san=r["path_san"], ply=r["ply"],
                content_hash=hashlib.sha1(text.encode()).hexdigest()[:16],
            ))
    return out
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && uv run pytest tests/test_coach_chunks.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/chess_trainer/coach/retrieval backend/tests/test_coach_chunks.py
printf 'feat(treinador): trechos indexáveis a partir da árvore do capítulo\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n' > "$TEMP/msg.txt" && git commit -F "$TEMP/msg.txt"
```

---

### Task 4: Modelos de dados, sqlite-vec na conexão e `VectorStore`

**Files:**
- Modify: `backend/chess_trainer/core/models.py` (novos `CoachChunk`, `CoachIndexedChapter`, `CoachExplanation`)
- Modify: `backend/chess_trainer/core/db.py` (`_carregar_sqlite_vec`, `vec_disponivel`)
- Create: `backend/chess_trainer/coach/retrieval/store.py`
- Test: `backend/tests/test_coach_store.py`, `backend/tests/test_models.py` (acrescentar)

**Interfaces:**
- Produces: modelos abaixo; `core.db.vec_disponivel(engine) -> bool`; `VectorStore(engine, modelo: str, dim: int, forcar_numpy: bool = False)` com `.backend` (`"sqlite-vec"` | `"numpy"`), `.upsert(db, trechos: list[Trecho], vetores: list[list[float]]) -> None`, `.delete_chapter(db, chapter_id) -> None`, `.search(db, vetor: list[float], k: int) -> list[tuple[str, float]]` (key, distância; menor é melhor), `.count(db) -> int`, `.hashes_do_capitulo(db, chapter_id) -> dict[str, str]` (key → content_hash), `.purgar_orfaos(db)`.

- [ ] **Step 1: Modelos**

Em `core/models.py`, acrescentar `LargeBinary` ao import de `sqlalchemy` e, no fim do arquivo:

```python
class CoachChunk(Base):
    """Trecho de comentário de capítulo indexado para a busca do treinador; o vetor
    fica aqui (float32) e, quando a extensão está disponível, também na tabela
    virtual `coach_chunks_vec` (chave = este `id`)."""

    __tablename__ = "coach_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(16), unique=True)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("study_chapters.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[str | None] = mapped_column(String(32), default=None)
    kind: Mapped[str] = mapped_column(String(8))
    text: Mapped[str] = mapped_column(Text)
    comment: Mapped[str] = mapped_column(Text, default="")
    fen: Mapped[str] = mapped_column(String(100), default="")
    path_san: Mapped[str] = mapped_column(Text, default="")
    ply: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(80), index=True)
    dim: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[bytes] = mapped_column(LargeBinary)
    embedded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CoachIndexedChapter(Base):
    """Quando cada capítulo foi indexado pela última vez (para saber o que está desatualizado)."""

    __tablename__ = "coach_indexed_chapters"

    chapter_id: Mapped[str] = mapped_column(ForeignKey("study_chapters.id", ondelete="CASCADE"), primary_key=True)
    indexed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    n_chunks: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String(80))


class CoachExplanation(Base):
    """Explicação do treinador para um exercício (guarda-se só a última por puzzle)."""

    __tablename__ = "coach_explanations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    puzzle_id: Mapped[str] = mapped_column(ForeignKey("puzzles.id", ondelete="CASCADE"), index=True)
    review_id: Mapped[str | None] = mapped_column(ForeignKey("reviews.id", ondelete="SET NULL"), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    model: Mapped[str] = mapped_column(String(40))
    prompt_version: Mapped[str] = mapped_column(String(16))
    effort: Mapped[str] = mapped_column(String(8))
    variante: Mapped[str] = mapped_column(String(16), default="agente_rag")
    text: Mapped[str] = mapped_column(Text)
    lines_json: Mapped[str] = mapped_column(Text, default="[]")
    citations_json: Mapped[str] = mapped_column(Text, default="[]")
    verification_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(8))  # ok | warnings | errors
    repaired: Mapped[bool] = mapped_column(Boolean, default=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    trace_id: Mapped[str | None] = mapped_column(String(64), default=None)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
```

Teste em `tests/test_models.py` (acrescentar):

```python
def test_tabelas_do_treinador_existem(db_engine):
    from sqlalchemy import inspect
    nomes = set(inspect(db_engine).get_table_names())
    assert {"coach_chunks", "coach_indexed_chapters", "coach_explanations"} <= nomes
```

Run: `cd backend && uv run pytest tests/test_models.py -q` → passa (`create_all` cria as tabelas novas; `migrate` não precisa mudar).

- [ ] **Step 2: sqlite-vec na conexão** (`core/db.py`)

Logo antes de `make_engine`:

```python
def _carregar_sqlite_vec(dbapi_conn) -> None:
    """Carrega a extensão `sqlite-vec` na conexão; sem o pacote, sem suporte a
    extensões ou com erro de carga, a busca vetorial cai no numpy (ver
    `coach/retrieval/store.py`)."""
    try:
        import sqlite_vec
    except ImportError:
        return
    try:
        dbapi_conn.enable_load_extension(True)
        sqlite_vec.load(dbapi_conn)
    except Exception:  # noqa: BLE001 - AttributeError (sem extensões) ou OperationalError
        return
    finally:
        try:
            dbapi_conn.enable_load_extension(False)
        except AttributeError:
            pass


def vec_disponivel(engine: Engine) -> bool:
    with engine.connect() as conn:
        try:
            conn.exec_driver_sql("SELECT vec_version()").scalar()
            return True
        except Exception:  # noqa: BLE001
            return False
```

Dentro de `_pragmas`, como primeira linha do corpo: `_carregar_sqlite_vec(dbapi_conn)`.

Run: `cd backend && uv run python -c "from chess_trainer.core.db import make_engine, vec_disponivel; print(vec_disponivel(make_engine(':memory:')))"` → `True`.

- [ ] **Step 3: Testes do store (falhando)**

`backend/tests/test_coach_store.py`:

```python
import pytest

from chess_trainer.coach.retrieval.chunks import Trecho
from chess_trainer.coach.retrieval.store import VectorStore
from chess_trainer.core.db import make_engine, init_db, make_session_factory
from chess_trainer.core.models import Study, StudyChapter


def trecho(key: str, chapter_id: str, texto: str, h: str = "h") -> Trecho:
    return Trecho(key=key, chapter_id=chapter_id, node_id=None, kind="intro", text=texto, comment=texto,
                  fen="", path_san="1.e4", ply=1, content_hash=h)


@pytest.fixture(params=["sqlite-vec", "numpy"])
def ambiente(request):
    engine = make_engine(":memory:")
    init_db(engine)
    factory = make_session_factory(engine)
    with factory() as db:
        db.add(Study(id="s1", title="E"))
        db.add_all([StudyChapter(id="c1", study_id="s1", order=1, name="A"), StudyChapter(id="c2", study_id="s1", order=2, name="B")])
        db.commit()
    store = VectorStore(engine, modelo="falso", dim=3, forcar_numpy=(request.param == "numpy"))
    assert store.backend == request.param
    return store, factory


def test_upsert_busca_e_contagem(ambiente):
    store, factory = ambiente
    with factory() as db:
        store.upsert(db, [trecho("k1", "c1", "cravada"), trecho("k2", "c1", "garfo"), trecho("k3", "c2", "final")],
                     [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
        db.commit()
        assert store.count(db) == 3
        assert [k for k, _ in store.search(db, [0.9, 0.1, 0], 2)] == ["k1", "k2"]
        assert store.hashes_do_capitulo(db, "c1") == {"k1": "h", "k2": "h"}


def test_upsert_atualiza_e_delete_apaga_o_capitulo(ambiente):
    store, factory = ambiente
    with factory() as db:
        store.upsert(db, [trecho("k1", "c1", "a"), trecho("k3", "c2", "c")], [[1, 0, 0], [0, 0, 1]])
        store.upsert(db, [trecho("k1", "c1", "a2", "h2")], [[0, 1, 0]])
        db.commit()
        assert store.count(db) == 2 and store.hashes_do_capitulo(db, "c1") == {"k1": "h2"}
        assert store.search(db, [0, 1, 0], 1)[0][0] == "k1"
        store.delete_chapter(db, "c1")
        db.commit()
        assert store.count(db) == 1 and [k for k, _ in store.search(db, [0, 1, 0], 5)] == ["k3"]


def test_vetores_de_outro_modelo_ficam_fora(ambiente):
    store, factory = ambiente
    outro = VectorStore(store.engine, modelo="outro", dim=3, forcar_numpy=(store.backend == "numpy"))
    with factory() as db:
        store.upsert(db, [trecho("k1", "c1", "a")], [[1, 0, 0]])
        outro.upsert(db, [trecho("k9", "c2", "z")], [[1, 0, 0]])
        db.commit()
        assert store.count(db) == 1 and [k for k, _ in store.search(db, [1, 0, 0], 5)] == ["k1"]
        assert outro.count(db) == 1 and [k for k, _ in outro.search(db, [1, 0, 0], 5)] == ["k9"]


def test_purgar_orfaos_apos_cascade(ambiente):
    store, factory = ambiente
    with factory() as db:
        store.upsert(db, [trecho("k1", "c1", "a")], [[1, 0, 0]])
        db.commit()
        db.delete(db.get(StudyChapter, "c1"))  # FK ON DELETE CASCADE apaga coach_chunks, não a tabela virtual
        db.commit()
        store.purgar_orfaos(db)
        db.commit()
        assert store.count(db) == 0 and store.search(db, [1, 0, 0], 5) == []
```

- [ ] **Step 4: Rodar e ver falhar**

Run: `cd backend && uv run pytest tests/test_coach_store.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 5: Implementar `store.py`**

```python
"""Armazenamento e busca dos vetores dos trechos (spec §6.3).

Os vetores ficam sempre em `coach_chunks.embedding` (float32). Com a extensão
`sqlite-vec` carregada, uma tabela virtual `coach_chunks_vec` serve a busca
KNN; sem ela, a busca é cosseno por força bruta em numpy sobre os vetores da
tabela (alguns milhares de trechos: instantâneo). A interface é a mesma."""
from __future__ import annotations

import threading

import numpy as np
from sqlalchemy import Engine, delete, select, text
from sqlalchemy.orm import Session

from chess_trainer.coach.retrieval.chunks import Trecho
from chess_trainer.core.db import vec_disponivel
from chess_trainer.core.models import CoachChunk, utcnow


def _normalizar(v) -> np.ndarray:
    a = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(a))
    return a / n if n else a


def _blob(v) -> bytes:
    return _normalizar(v).tobytes()


class VectorStore:
    def __init__(self, engine: Engine, modelo: str, dim: int, forcar_numpy: bool = False):
        self.engine = engine
        self.modelo = modelo
        self.dim = dim
        self.backend = "numpy" if forcar_numpy or not vec_disponivel(engine) else "sqlite-vec"
        self._lock = threading.Lock()
        self._cache: tuple[np.ndarray, list[str]] | None = None
        if self.backend == "sqlite-vec":
            self._garantir_tabela_vec()

    # --- tabela virtual -------------------------------------------------

    def _garantir_tabela_vec(self) -> None:
        """A tabela virtual tem a dimensão fixa; se mudou (modelo novo), recria."""
        with self.engine.begin() as conn:
            existe = conn.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE name = 'coach_chunks_vec'").scalar()
            if existe and f"FLOAT[{self.dim}]" not in existe:
                conn.exec_driver_sql("DROP TABLE coach_chunks_vec")
                existe = None
            if not existe:
                conn.exec_driver_sql(
                    f"CREATE VIRTUAL TABLE coach_chunks_vec USING vec0(id INTEGER PRIMARY KEY, embedding FLOAT[{self.dim}])")

    def _vec_delete(self, db: Session, ids: list[int]) -> None:
        for i in ids:
            db.execute(text("DELETE FROM coach_chunks_vec WHERE id = :id"), {"id": i})

    def _vec_insert(self, db: Session, id_: int, vetor) -> None:
        db.execute(text("INSERT INTO coach_chunks_vec(id, embedding) VALUES (:id, :emb)"), {"id": id_, "emb": _blob(vetor)})

    # --- escrita ----------------------------------------------------------

    def upsert(self, db: Session, trechos: list[Trecho], vetores: list[list[float]]) -> None:
        assert len(trechos) == len(vetores)
        for t, v in zip(trechos, vetores):
            row = db.scalar(select(CoachChunk).where(CoachChunk.key == t.key))
            if row is None:
                row = CoachChunk(key=t.key)
                db.add(row)
            row.chapter_id, row.node_id, row.kind = t.chapter_id, t.node_id, t.kind
            row.text, row.comment, row.fen, row.path_san, row.ply = t.text, t.comment, t.fen, t.path_san, t.ply
            row.content_hash, row.model, row.dim = t.content_hash, self.modelo, self.dim
            row.embedding, row.embedded_at = _blob(v), utcnow()
            db.flush()
            if self.backend == "sqlite-vec":
                self._vec_delete(db, [row.id])
                self._vec_insert(db, row.id, v)
        self._cache = None

    def delete_chapter(self, db: Session, chapter_id: str) -> None:
        ids = list(db.scalars(select(CoachChunk.id).where(CoachChunk.chapter_id == chapter_id)))
        if self.backend == "sqlite-vec":
            self._vec_delete(db, ids)
        db.execute(delete(CoachChunk).where(CoachChunk.chapter_id == chapter_id))
        self._cache = None

    def purgar_orfaos(self, db: Session) -> None:
        """Linhas da tabela virtual cujo trecho sumiu (o CASCADE do capítulo não a alcança)."""
        if self.backend == "sqlite-vec":
            db.execute(text("DELETE FROM coach_chunks_vec WHERE id NOT IN (SELECT id FROM coach_chunks)"))
        self._cache = None

    # --- leitura ----------------------------------------------------------

    def count(self, db: Session) -> int:
        return len(list(db.scalars(select(CoachChunk.id).where(CoachChunk.model == self.modelo))))

    def hashes_do_capitulo(self, db: Session, chapter_id: str) -> dict[str, str]:
        rows = db.execute(select(CoachChunk.key, CoachChunk.content_hash)
                          .where(CoachChunk.chapter_id == chapter_id, CoachChunk.model == self.modelo)).all()
        return {k: h for k, h in rows}

    def search(self, db: Session, vetor: list[float], k: int) -> list[tuple[str, float]]:
        if k <= 0:
            return []
        if self.backend == "sqlite-vec":
            # os vetores são unitários: a distância L2 ordena igual ao cosseno
            hits = db.execute(text("SELECT id, distance FROM coach_chunks_vec WHERE embedding MATCH :q AND k = :k ORDER BY distance"),
                              {"q": _blob(vetor), "k": k}).all()
            if not hits:
                return []
            por_id = {i: d for i, d in hits}
            rows = db.execute(select(CoachChunk.id, CoachChunk.key)
                              .where(CoachChunk.id.in_(list(por_id)), CoachChunk.model == self.modelo)).all()
            return sorted(((key, float(por_id[i])) for i, key in rows), key=lambda x: x[1])
        matriz, chaves = self._matriz(db)
        if not chaves:
            return []
        sims = matriz @ _normalizar(vetor)
        ordem = np.argsort(-sims)[:k]
        return [(chaves[i], float(1.0 - sims[i])) for i in ordem]

    def _matriz(self, db: Session) -> tuple[np.ndarray, list[str]]:
        with self._lock:
            if self._cache is None:
                rows = db.execute(select(CoachChunk.key, CoachChunk.embedding).where(CoachChunk.model == self.modelo)).all()
                chaves = [k for k, _ in rows]
                matriz = (np.stack([np.frombuffer(e, dtype=np.float32) for _, e in rows])
                          if rows else np.zeros((0, self.dim), dtype=np.float32))
                self._cache = (matriz, chaves)
            return self._cache
```

- [ ] **Step 6: Rodar e ver passar**

Run: `cd backend && uv run pytest tests/test_coach_store.py tests/test_models.py -q`
Expected: tudo verde nos dois backends. Se o `MATCH ... AND k = :k` for recusado pela versão instalada do sqlite-vec, troque por `... WHERE embedding MATCH :q ORDER BY distance LIMIT :k` (as duas formas são documentadas; use a que a versão aceitar e deixe um comentário).

- [ ] **Step 7: Rodar a suíte inteira** — `cd backend && uv run pytest -q` → verde (a migração de bancos antigos com `test_migration.py` continua passando: só tabelas novas).

- [ ] **Step 8: Commit**

```bash
git add backend/chess_trainer/core/models.py backend/chess_trainer/core/db.py backend/chess_trainer/coach/retrieval/store.py backend/tests/test_coach_store.py backend/tests/test_models.py
printf 'feat(treinador): tabelas do treinador, sqlite-vec na conexão e armazenamento de vetores\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n' > "$TEMP/msg.txt" && git commit -F "$TEMP/msg.txt"
```

---

### Task 5: Embeddings, `Indexador` e ganchos nas rotas de estudos

**Files:**
- Create: `backend/chess_trainer/coach/retrieval/embeddings.py`, `backend/chess_trainer/coach/retrieval/index.py`
- Modify: `backend/tests/fakes.py` (`EmbeddingsFalso`), `backend/chess_trainer/api/app.py` (`embeddings_factory`, `app.state.coach_index`, `CHESS_TRAINER_DATA`), `backend/chess_trainer/api/routes/studies.py` (ganchos)
- Test: `backend/tests/test_coach_index.py`, `backend/tests/test_api_studies.py` (acrescentar)

**Interfaces:**
- Consumes: `VectorStore`, `trechos_do_capitulo`, `core.studies.tree.chapter_tree(chapter)`, `config.get_setting/set_setting`.
- Produces: `Embeddings` (Protocol: `modelo: str`, `dim: int`, `preparar() -> None`, `embed(textos: list[str]) -> list[list[float]]`); `FastembedEmbeddings(modelo=MODELO_PADRAO, cache_dir: Path)`; `MODELO_PADRAO`, `DIMENSOES`; `Indexador(engine, embeddings: Embeddings, forcar_numpy=False)` com `.store`, `.modelo_pronto(db) -> bool`, `.indexar_capitulo(db, chapter) -> int`, `.remover_capitulo(db, chapter_id)`, `.indexar_estudo(db, study) -> int`, `.recriar(db, progress) -> int`, `.status(db) -> dict`, `.buscar(db, consulta: str, k: int = 5, caminho_san: str | None = None) -> list[dict]` (cada dict: `chunk_id, study_id, estudo, chapter_id, capitulo, node_id, caminho_san, texto, url`). `app.state.coach_index: Indexador`; `create_app(..., embeddings_factory=None)`; `tests.fakes.EmbeddingsFalso(dim=8)`.
- Chave de configuração `coach_embeddings_ready` = nome do modelo já baixado.

- [ ] **Step 1: `EmbeddingsFalso` em `tests/fakes.py`** (acrescentar no fim)

```python
class EmbeddingsFalso:
    """Vetores determinísticos por saco de palavras: textos que compartilham palavras ficam perto."""

    def __init__(self, dim: int = 8, modelo: str = "falso"):
        self.dim = dim
        self.modelo = modelo
        self.preparado = False
        self.chamadas: list[list[str]] = []

    def preparar(self) -> None:
        self.preparado = True

    def embed(self, textos: list[str]) -> list[list[float]]:
        self.chamadas.append(list(textos))
        out = []
        for t in textos:
            v = [0.0] * self.dim
            for palavra in t.lower().split():
                v[hash(palavra) % self.dim] += 1.0  # `hash` de str varia por processo; dentro do processo é estável
            out.append(v)
        return out
```

Nota: `hash(str)` muda entre processos por causa do `PYTHONHASHSEED`, o que é aceitável (os testes comparam dentro do mesmo processo). Se preferir determinismo total, use `int(hashlib.md5(palavra.encode()).hexdigest(), 16) % self.dim`.

- [ ] **Step 2: Testes do indexador (falhando)**

`backend/tests/test_coach_index.py`:

```python
import json
from datetime import datetime, timedelta

import chess
import pytest

from chess_trainer.coach.retrieval.index import Indexador
from chess_trainer.config import get_setting, set_setting
from chess_trainer.core.db import init_db, make_engine, make_session_factory
from chess_trainer.core.models import Study, StudyChapter
from tests.fakes import EmbeddingsFalso


def arvore(comentario: str):
    return {"fen": chess.STARTING_FEN, "orientation": "white", "intro": "",
            "root": {"children": [{"id": "n1", "uci": "e2e4", "san": "e4", "comment": comentario, "children": []}]}}


@pytest.fixture
def ambiente():
    engine = make_engine(":memory:")
    init_db(engine)
    factory = make_session_factory(engine)
    emb = EmbeddingsFalso()
    idx = Indexador(engine, emb)
    with factory() as db:
        s = Study(id="s1", title="Táticas básicas")
        db.add(s)
        db.add(StudyChapter(id="c1", study_id="s1", order=1, name="Cravadas", updated_at=datetime(2026, 1, 1),
                            tree_json=json.dumps(arvore("A cravada absoluta prende a peça ao rei e decide a partida."))))
        db.add(StudyChapter(id="c2", study_id="s1", order=2, name="Garfos", updated_at=datetime(2026, 1, 1),
                            tree_json=json.dumps(arvore("O garfo de cavalo ataca duas peças ao mesmo tempo sem defesa."))))
        db.commit()
    return idx, factory, emb


def test_sem_modelo_pronto_nao_indexa_e_status_avisa(ambiente):
    idx, factory, emb = ambiente
    with factory() as db:
        assert idx.modelo_pronto(db) is False
        assert idx.indexar_capitulo(db, db.get(StudyChapter, "c1")) == 0
        st = idx.status(db)
        assert st["embeddings_ready"] is False and st["index_chunks"] == 0 and st["index_stale"] == 2
        assert idx.buscar(db, "cravada", 3) == []


def test_recriar_baixa_o_modelo_indexa_tudo_e_busca(ambiente):
    idx, factory, emb = ambiente
    progresso = []
    with factory() as db:
        n = idx.recriar(db, lambda *a: progresso.append(a))
        db.commit()
        assert emb.preparado and n == 2 and get_setting(db, "coach_embeddings_ready") == "falso"
        assert progresso[-1][:3] == ("coach_reindex", 2, 2)
        st = idx.status(db)
        assert st["index_chunks"] == 2 and st["index_stale"] == 0 and st["index_model"] == "falso"
        hits = idx.buscar(db, "cravada absoluta rei", 1)
        assert len(hits) == 1 and hits[0]["chapter_id"] == "c1" and hits[0]["capitulo"] == "Cravadas"
        assert hits[0]["url"] == "/estudos/s1/capitulos/c1?lance=n1" and hits[0]["caminho_san"] == "1.e4"
        assert hits[0]["texto"].startswith("A cravada absoluta") and len(hits[0]["chunk_id"]) == 10


def test_indexar_capitulo_pula_trechos_iguais_e_remove_os_que_sumiram(ambiente):
    idx, factory, emb = ambiente
    with factory() as db:
        idx.recriar(db, lambda *a: None)
        db.commit()
        chamadas_antes = len(emb.chamadas)
        c1 = db.get(StudyChapter, "c1")
        assert idx.indexar_capitulo(db, c1) == 1 and len(emb.chamadas) == chamadas_antes  # nada mudou: sem embed
        c1.tree_json = json.dumps(arvore(""))  # comentário apagado
        c1.updated_at = datetime(2026, 2, 1)
        db.flush()
        assert idx.indexar_capitulo(db, c1) == 0
        db.commit()
        assert idx.status(db)["index_chunks"] == 1 and idx.status(db)["index_stale"] == 0


def test_capitulo_editado_depois_do_indice_conta_como_desatualizado(ambiente):
    idx, factory, emb = ambiente
    with factory() as db:
        idx.recriar(db, lambda *a: None)
        c2 = db.get(StudyChapter, "c2")
        c2.updated_at = datetime.utcnow() + timedelta(minutes=5)
        db.commit()
        assert idx.status(db)["index_stale"] == 1
        idx.remover_capitulo(db, "c2")
        db.commit()
        assert idx.status(db)["index_chunks"] == 1


def test_busca_traz_tambem_a_mesma_abertura(ambiente):
    idx, factory, emb = ambiente
    with factory() as db:
        idx.recriar(db, lambda *a: None)
        db.commit()
        hits = idx.buscar(db, "garfo cavalo", 1, caminho_san="1.e4 e5 2.Nf3 Nc6 3.Bb5 a6")
        # k=1 pela busca vetorial (garfos) + o trecho com o mesmo começo de partida (1.e4), sem duplicar
        assert [h["chapter_id"] for h in hits] == ["c2", "c1"]


def test_troca_de_modelo_invalida_o_indice(ambiente):
    idx, factory, emb = ambiente
    with factory() as db:
        idx.recriar(db, lambda *a: None)
        db.commit()
        outro = Indexador(idx.store.engine, EmbeddingsFalso(modelo="falso-v2"))
        assert outro.modelo_pronto(db) is False and outro.status(db)["index_chunks"] == 0
        assert idx.modelo_pronto(db) is True  # o índice do modelo antigo continua íntegro
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `cd backend && uv run pytest tests/test_coach_index.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 4: Implementar `embeddings.py`**

```python
"""Embeddings locais com fastembed (ONNX, CPU): nada de PyTorch no backend (spec §6.2).

O download do modelo (~250 MB) acontece só em `preparar()`, chamado pelo
"Recriar índice"; a criação do objeto é barata e não toca a rede."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

# primeira opção do spec; a lista de modelos suportados sai de
# `TextEmbedding.list_supported_models()` — confira o nome exato ao implementar
MODELO_PADRAO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DIMENSOES: dict[str, int] = {MODELO_PADRAO: 384}


class Embeddings(Protocol):
    modelo: str
    dim: int

    def preparar(self) -> None: ...

    def embed(self, textos: list[str]) -> list[list[float]]: ...


class FastembedEmbeddings:
    def __init__(self, modelo: str = MODELO_PADRAO, cache_dir: Path | None = None):
        self.modelo = modelo
        self.dim = DIMENSOES.get(modelo, 384)
        self._cache_dir = cache_dir
        self._model = None

    def preparar(self) -> None:
        if self._model is None:
            from fastembed import TextEmbedding  # import tardio: o pacote é pesado

            kwargs = {"model_name": self.modelo}
            if self._cache_dir is not None:
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                kwargs["cache_dir"] = str(self._cache_dir)
            self._model = TextEmbedding(**kwargs)
            dim = len(next(iter(self._model.embed(["dimensão"]))))
            if dim != self.dim:
                raise RuntimeError(f"modelo {self.modelo}: dimensão {dim}, esperada {self.dim}")

    def embed(self, textos: list[str]) -> list[list[float]]:
        if not textos:
            return []
        self.preparar()
        return [list(map(float, v)) for v in self._model.embed(textos)]
```

- [ ] **Step 5: Implementar `index.py`**

```python
"""Índice dos trechos dos estudos: indexar capítulo a capítulo, recriar tudo,
estado e busca (spec §6.4). Precisa do modelo de embeddings já baixado
(`coach_embeddings_ready`); sem ele, os capítulos ficam marcados como
desatualizados e a busca devolve vazio."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from chess_trainer.api.jobs import ProgressFn
from chess_trainer.coach.retrieval.chunks import trechos_do_capitulo
from chess_trainer.coach.retrieval.embeddings import Embeddings
from chess_trainer.coach.retrieval.store import VectorStore
from chess_trainer.config import get_setting, set_setting
from chess_trainer.core.models import CoachChunk, CoachIndexedChapter, Study, StudyChapter, utcnow
from chess_trainer.core.studies.tree import chapter_tree

CHAVE_MODELO_PRONTO = "coach_embeddings_ready"
PLIES_MESMA_ABERTURA = 6
EXTRA_MESMA_ABERTURA = 3


class Indexador:
    def __init__(self, engine: Engine, embeddings: Embeddings, forcar_numpy: bool = False):
        self.embeddings = embeddings
        self.store = VectorStore(engine, embeddings.modelo, embeddings.dim, forcar_numpy=forcar_numpy)

    def modelo_pronto(self, db: Session) -> bool:
        return get_setting(db, CHAVE_MODELO_PRONTO) == self.embeddings.modelo

    # --- escrita ----------------------------------------------------------

    def indexar_capitulo(self, db: Session, chapter: StudyChapter) -> int:
        """Reindexa um capítulo; só embute os trechos novos ou alterados. Devolve quantos trechos ele tem no índice."""
        if not self.modelo_pronto(db):
            return 0
        estudo = chapter.study.title if chapter.study is not None else ""
        trechos = trechos_do_capitulo(chapter.id, estudo, chapter.name, chapter_tree(chapter))
        existentes = self.store.hashes_do_capitulo(db, chapter.id)
        novos = [t for t in trechos if existentes.get(t.key) != t.content_hash]
        chaves_atuais = {t.key for t in trechos}
        if set(existentes) - chaves_atuais:
            # algum trecho sumiu: recomeça o capítulo (poucas dezenas de linhas)
            self.store.delete_chapter(db, chapter.id)
            novos = trechos
        if novos:
            self.store.upsert(db, novos, self.embeddings.embed([t.text for t in novos]))
        marca = db.get(CoachIndexedChapter, chapter.id)
        if marca is None:
            marca = CoachIndexedChapter(chapter_id=chapter.id)
            db.add(marca)
        marca.indexed_at, marca.n_chunks, marca.model = utcnow(), len(trechos), self.embeddings.modelo
        db.flush()
        return len(trechos)

    def remover_capitulo(self, db: Session, chapter_id: str) -> None:
        self.store.delete_chapter(db, chapter_id)
        marca = db.get(CoachIndexedChapter, chapter_id)
        if marca is not None:
            db.delete(marca)
        db.flush()

    def indexar_estudo(self, db: Session, study: Study) -> int:
        return sum(self.indexar_capitulo(db, c) for c in study.chapters)

    def recriar(self, db: Session, progress: ProgressFn) -> int:
        """Baixa o modelo se preciso, apaga o índice e reindexa todos os capítulos."""
        progress("coach_reindex", 0, 0, "preparando o modelo de embeddings")
        self.embeddings.preparar()
        set_setting(db, CHAVE_MODELO_PRONTO, self.embeddings.modelo)
        capitulos = list(db.scalars(select(StudyChapter).order_by(StudyChapter.study_id, StudyChapter.order)))
        for c in capitulos:
            self.store.delete_chapter(db, c.id)
        self.store.purgar_orfaos(db)
        total = len(capitulos)
        for i, c in enumerate(capitulos, start=1):
            self.indexar_capitulo(db, c)
            progress("coach_reindex", i, total, f"{i}/{total} capítulos")
        db.commit()
        return total

    # --- leitura ----------------------------------------------------------

    def status(self, db: Session) -> dict:
        capitulos = db.execute(select(StudyChapter.id, StudyChapter.updated_at)).all()
        marcas = {m.chapter_id: m for m in db.scalars(select(CoachIndexedChapter))}
        desatualizados = 0
        for cid, updated_at in capitulos:
            m = marcas.get(cid)
            if m is None or m.model != self.embeddings.modelo or (updated_at is not None and updated_at > m.indexed_at):
                desatualizados += 1
        return {
            "embeddings_ready": self.modelo_pronto(db),
            "index_chunks": self.store.count(db),
            "index_model": self.embeddings.modelo,
            "index_stale": desatualizados,
            "vector_backend": self.store.backend,
        }

    def buscar(self, db: Session, consulta: str, k: int = 5, caminho_san: str | None = None) -> list[dict]:
        if not self.modelo_pronto(db) or not consulta.strip():
            return []
        vetor = self.embeddings.embed([consulta])[0]
        chaves = [key for key, _ in self.store.search(db, vetor, k)]
        if caminho_san:
            # "mesma abertura": o caminho do trecho é prefixo dos primeiros plies da partida
            # ou vice-versa (um comentário em 1.e4 vale para qualquer partida que começou assim)
            prefixo = " ".join(caminho_san.split()[:PLIES_MESMA_ABERTURA])
            candidatos = db.execute(select(CoachChunk.key, CoachChunk.path_san)
                                    .where(CoachChunk.model == self.embeddings.modelo, CoachChunk.path_san != "")).all()
            extras = 0
            for key, path in candidatos:
                if key in chaves or extras >= EXTRA_MESMA_ABERTURA:
                    continue
                if prefixo.startswith(path) or path.startswith(prefixo):
                    chaves.append(key)
                    extras += 1
        if not chaves:
            return []
        rows = {r.key: r for r in db.scalars(select(CoachChunk).where(CoachChunk.key.in_(chaves)))}
        out = []
        for key in chaves:
            r = rows.get(key)
            if r is None:
                continue
            capitulo = db.get(StudyChapter, r.chapter_id)
            estudo = capitulo.study if capitulo is not None else None
            url = f"/estudos/{capitulo.study_id}/capitulos/{capitulo.id}" if capitulo is not None else ""
            if r.node_id:
                url += f"?lance={r.node_id}"
            out.append({
                "chunk_id": r.key, "study_id": capitulo.study_id if capitulo else "", "estudo": estudo.title if estudo else "",
                "chapter_id": r.chapter_id, "capitulo": capitulo.name if capitulo else "", "node_id": r.node_id,
                "caminho_san": r.path_san, "texto": r.comment, "url": url,
            })
        return out
```

- [ ] **Step 6: Rodar e ver passar**

Run: `cd backend && uv run pytest tests/test_coach_index.py -q`
Expected: 6 passed.

- [ ] **Step 7: Ligar no app** (`api/app.py`)

- Assinatura: `create_app(..., embeddings_factory=None)`.
- Diretório de dados: no começo de `create_app`, `data_dir = Path(os.environ.get("CHESS_TRAINER_DATA", str(BACKEND_DIR / "data")))`; `db_path` padrão vira `os.environ.get("CHESS_TRAINER_DB", str(data_dir / "chess_trainer.db"))`; `app.state.tactics_dest = data_dir / "lichess_db_puzzle.csv.zst"`.
- Depois de `app.state.openings = ...`:

```python
    # busca nos estudos do treinador: embeddings locais (o download do modelo só
    # acontece no "Recriar índice"); nos testes entra um `EmbeddingsFalso`
    from chess_trainer.coach.retrieval.embeddings import FastembedEmbeddings
    from chess_trainer.coach.retrieval.index import Indexador

    embeddings = embeddings_factory() if embeddings_factory else FastembedEmbeddings(cache_dir=data_dir / "fastembed")
    app.state.coach_index = Indexador(db_engine, embeddings)
```

(Mova os imports para o topo do arquivo; ficam aqui só para mostrar de onde vêm.)

- [ ] **Step 8: Ganchos nas rotas de estudos** (`api/routes/studies.py`)

- `put_chapter`: depois de `save_chapter(...)` bem-sucedido: `request.app.state.coach_index.indexar_capitulo(db, chapter); db.commit()` (acrescente `request: Request` aos parâmetros).
- `post_chapter` e `post_duplicate`: idem com o capítulo criado.
- `del_chapter`: antes de `delete_chapter(...)`: `request.app.state.coach_index.remover_capitulo(db, chapter.id)`.
- `_submit` (job de importação): depois de `_, report = upsert_study(...)`, troque para `study, report = upsert_study(...)` e, antes do `progress(... report.message())`: `app.state.coach_index.indexar_estudo(db, study); db.commit()`. Se `upsert_study` já devolve o estudo como primeiro item da tupla (confira na assinatura), é só isso.

Teste em `tests/test_api_studies.py` (acrescentar; use as fixtures de app/cliente que o arquivo já tem e um estudo criado pela API):

```python
def test_salvar_capitulo_indexa_quando_o_modelo_esta_pronto(client, app):
    from chess_trainer.config import set_setting
    with app.state.session_factory() as db:
        set_setting(db, "coach_embeddings_ready", "falso")
    estudo = client.post("/api/studies", json={"title": "Sintético"}).json()
    cap = client.post(f"/api/studies/{estudo['id']}/chapters", json={"name": "Um"}).json()
    tree = cap["tree"]
    tree["intro"] = "Enunciado sintético longo o bastante para virar um trecho indexado."
    r = client.put(f"/api/studies/{estudo['id']}/chapters/{cap['id']}", json={"name": "Um", "mode": "read", "orientation": "white", "tree": tree})
    assert r.status_code == 200
    with app.state.session_factory() as db:
        st = app.state.coach_index.status(db)
        assert st["index_chunks"] == 1 and st["index_stale"] == 0
    client.delete(f"/api/studies/{estudo['id']}/chapters/{cap['id']}")
    with app.state.session_factory() as db:
        assert app.state.coach_index.status(db)["index_chunks"] == 0
```

A fixture de app desse arquivo precisa passar `embeddings_factory=EmbeddingsFalso` (importe de `tests.fakes`). Ajuste o corpo do `ChapterSaveIn` ao que a API espera (veja `schemas.ChapterSaveIn`).

- [ ] **Step 9: Rodar tudo**

Run: `cd backend && uv run pytest -q`
Expected: verde.

- [ ] **Step 10: Commit**

```bash
git add backend/chess_trainer/coach/retrieval backend/chess_trainer/api/app.py backend/chess_trainer/api/routes/studies.py backend/tests/fakes.py backend/tests/test_coach_index.py backend/tests/test_api_studies.py
printf 'feat(treinador): embeddings locais, indexador dos estudos e ganchos ao salvar capítulo\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n' > "$TEMP/msg.txt" && git commit -F "$TEMP/msg.txt"
```

---

### Task 6: Cliente LLM (`llm.py`) e `FakeLlm`

**Files:**
- Create: `backend/chess_trainer/coach/llm.py`
- Modify: `backend/tests/fakes.py` (`FakeLlm`)
- Test: `backend/tests/test_coach_llm.py`

**Interfaces:**
- Consumes: `coach.costs.Uso`.
- Produces: `ErroDoTreinador(codigo: str, mensagem: str)`; `Ferramenta(nome, descricao, schema: dict, fn: Callable[[dict], str])` com `.definicao() -> dict`; `ChamadaFerramenta(nome, entrada, resultado, erro=False)`; `ResultadoAgente(texto, estruturado: dict | None, uso: Uso, chamadas: list[ChamadaFerramenta], stop_reason: str, model: str, n_chamadas_api: int)`; `LlmClient` (Protocol: `model: str`; `run_agent(*, system: str, user: str, ferramentas: list[Ferramenta], esquema_final: dict, effort: str, max_tokens: int = 4096) -> ResultadoAgente`); `executar_ferramenta(ferramentas, nome, entrada) -> ChamadaFerramenta`; `AnthropicClient(api_key: str, model: str, client=None)`; constantes `FERRAMENTA_FINAL = "entregar_explicacao"`, `MAX_ITERACOES = 8`, `TETO_TOKENS_SAIDA = 12_000`.
- Códigos de erro: `chave_recusada`, `limite_de_uso`, `sem_conexao`, `requisicao_invalida`, `erro_da_api`, `recusa`, `custo_excedido`, `resposta_fora_do_esquema`, `coach_nao_configurado`, `engine_indisponivel`, `explicacao_em_andamento`.
- Desenho: a resposta final é uma **ferramenta** (`entregar_explicacao`, `strict: true`, esquema = `esquema_final`), chamada pelo modelo quando termina; o loop para ao recebê-la. Funciona igual em todos os modelos (não depende de `tool_choice` forçado).

- [ ] **Step 1: Testes (falhando)**

`backend/tests/test_coach_llm.py`:

```python
from types import SimpleNamespace

import httpx
import pytest

from chess_trainer.coach.costs import Uso
from chess_trainer.coach.llm import (FERRAMENTA_FINAL, TETO_TOKENS_SAIDA, AnthropicClient, ErroDoTreinador,
                                     Ferramenta, executar_ferramenta)
from tests.fakes import FakeLlm

ESQUEMA = {"type": "object", "properties": {"texto": {"type": "string"}}, "required": ["texto"], "additionalProperties": False}


def soma(entrada: dict) -> str:
    return str(entrada["a"] + entrada["b"])


FERR = Ferramenta("somar", "Soma dois números.", {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                                                  "required": ["a", "b"], "additionalProperties": False}, soma)


def bloco_texto(t):
    return SimpleNamespace(type="text", text=t)


def bloco_tool(id_, name, inp):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=inp)


def resposta(content, stop_reason="tool_use", inp=100, out=20, cr=0, cw=0):
    return SimpleNamespace(content=content, stop_reason=stop_reason, stop_details=None,
                           usage=SimpleNamespace(input_tokens=inp, output_tokens=out, cache_read_input_tokens=cr, cache_creation_input_tokens=cw))


class ClienteFalso:
    """Dublê do `anthropic.Anthropic`: devolve as respostas na ordem e guarda os pedidos."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.pedidos = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.pedidos.append(kwargs)
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_executar_ferramenta_captura_erros():
    ok = executar_ferramenta([FERR], "somar", {"a": 2, "b": 3})
    assert ok.resultado == "5" and not ok.erro
    ruim = executar_ferramenta([FERR], "somar", {"a": 2})
    assert ruim.erro and "b" in ruim.resultado
    inexistente = executar_ferramenta([FERR], "nada", {})
    assert inexistente.erro and "desconhecida" in inexistente.resultado


def test_loop_chama_ferramenta_e_para_na_entrega():
    cliente = ClienteFalso([
        resposta([bloco_texto("vou somar"), bloco_tool("t1", "somar", {"a": 1, "b": 2})]),
        resposta([bloco_tool("t2", FERRAMENTA_FINAL, {"texto": "três"})], cr=500, cw=0),
    ])
    llm = AnthropicClient("sk", "claude-opus-5", client=cliente)
    r = llm.run_agent(system="S", user="U", ferramentas=[FERR], esquema_final=ESQUEMA, effort="medium")
    assert r.estruturado == {"texto": "três"} and r.texto == "vou somar"
    assert [c.nome for c in r.chamadas] == ["somar"] and r.chamadas[0].resultado == "3"
    assert r.uso == Uso(200, 40, 500, 0) and r.n_chamadas_api == 2 and r.model == "claude-opus-5"
    p = cliente.pedidos[0]
    assert p["model"] == "claude-opus-5" and p["output_config"] == {"effort": "medium"} and p["thinking"] == {"type": "adaptive"}
    assert p["system"][0]["cache_control"] == {"type": "ephemeral"} and p["tools"][-1]["name"] == FERRAMENTA_FINAL
    assert p["tools"][-1]["strict"] is True and p["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    # o segundo pedido carrega a resposta do assistente e o resultado da ferramenta
    seg = cliente.pedidos[1]["messages"]
    assert seg[1]["role"] == "assistant" and seg[2]["content"][0] == {"type": "tool_result", "tool_use_id": "t1", "content": "3"}


def test_fim_sem_entrega_devolve_texto_e_estruturado_nulo():
    cliente = ClienteFalso([resposta([bloco_texto("não sei")], stop_reason="end_turn")])
    r = AnthropicClient("sk", "claude-opus-5", client=cliente).run_agent(system="S", user="U", ferramentas=[], esquema_final=ESQUEMA, effort="high")
    assert r.estruturado is None and r.texto == "não sei" and r.stop_reason == "end_turn"


def test_ferramenta_com_erro_volta_como_is_error():
    cliente = ClienteFalso([
        resposta([bloco_tool("t1", "somar", {"a": 1})]),
        resposta([bloco_tool("t2", FERRAMENTA_FINAL, {"texto": "x"})]),
    ])
    AnthropicClient("sk", "claude-opus-5", client=cliente).run_agent(system="S", user="U", ferramentas=[FERR], esquema_final=ESQUEMA, effort="high")
    assert cliente.pedidos[1]["messages"][2]["content"][0]["is_error"] is True


def test_recusa_e_teto_de_tokens():
    cliente = ClienteFalso([resposta([], stop_reason="refusal")])
    with pytest.raises(ErroDoTreinador) as exc:
        AnthropicClient("sk", "claude-opus-5", client=cliente).run_agent(system="S", user="U", ferramentas=[], esquema_final=ESQUEMA, effort="high")
    assert exc.value.codigo == "recusa"
    cliente = ClienteFalso([resposta([bloco_tool("t1", "somar", {"a": 1, "b": 1})], out=TETO_TOKENS_SAIDA + 1)])
    with pytest.raises(ErroDoTreinador) as exc:
        AnthropicClient("sk", "claude-opus-5", client=cliente).run_agent(system="S", user="U", ferramentas=[FERR], esquema_final=ESQUEMA, effort="high")
    assert exc.value.codigo == "custo_excedido"


def test_erros_do_sdk_viram_codigos():
    import anthropic
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    def status(cls, code):
        return cls("x", response=httpx.Response(code, request=req), body=None)

    casos = [
        (status(anthropic.AuthenticationError, 401), "chave_recusada"),
        (status(anthropic.RateLimitError, 429), "limite_de_uso"),
        (status(anthropic.BadRequestError, 400), "requisicao_invalida"),
        (status(anthropic.InternalServerError, 500), "erro_da_api"),
        (anthropic.APIConnectionError(request=req), "sem_conexao"),
    ]
    for erro, codigo in casos:
        cliente = ClienteFalso([erro])
        with pytest.raises(ErroDoTreinador) as exc:
            AnthropicClient("sk", "claude-opus-5", client=cliente).run_agent(system="S", user="U", ferramentas=[], esquema_final=ESQUEMA, effort="high")
        assert exc.value.codigo == codigo, codigo


def test_fake_llm_segue_o_roteiro_e_executa_as_ferramentas():
    fake = FakeLlm([[("ferramenta", "somar", {"a": 4, "b": 5}), ("texto", "pensando"), ("final", {"texto": "nove"})]])
    r = fake.run_agent(system="S", user="U", ferramentas=[FERR], esquema_final=ESQUEMA, effort="low")
    assert r.estruturado == {"texto": "nove"} and r.chamadas[0].resultado == "9" and r.texto == "pensando"
    assert fake.prompts[0]["ferramentas"] == ["somar"] and fake.prompts[0]["effort"] == "low"
    with pytest.raises(AssertionError):
        fake.run_agent(system="S", user="U", ferramentas=[], esquema_final=ESQUEMA, effort="low")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && uv run pytest tests/test_coach_llm.py -q`
Expected: FAIL com `ImportError`

- [ ] **Step 3: Implementar `llm.py`**

```python
"""Cliente LLM do treinador (spec §4.1).

`LlmClient` é a interface que o pipeline usa; `AnthropicClient` a implementa
com o SDK oficial e um loop de ferramentas explícito. A resposta final vem
por uma ferramenta (`entregar_explicacao`) com esquema estrito: o modelo a
chama quando termina, e o loop para. Erros do SDK viram `ErroDoTreinador`
com um código curto que a API traduz em mensagem."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from chess_trainer.coach.costs import Uso

FERRAMENTA_FINAL = "entregar_explicacao"
MAX_ITERACOES = 8
TETO_TOKENS_SAIDA = 12_000


class ErroDoTreinador(Exception):
    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


@dataclass(frozen=True)
class Ferramenta:
    nome: str
    descricao: str
    schema: dict
    fn: Callable[[dict], str]

    def definicao(self) -> dict:
        return {"name": self.nome, "description": self.descricao, "input_schema": self.schema}


@dataclass
class ChamadaFerramenta:
    nome: str
    entrada: dict
    resultado: str
    erro: bool = False


@dataclass
class ResultadoAgente:
    texto: str
    estruturado: dict | None
    uso: Uso
    chamadas: list[ChamadaFerramenta] = field(default_factory=list)
    stop_reason: str = "end_turn"
    model: str = ""
    n_chamadas_api: int = 0


class LlmClient(Protocol):
    model: str

    def run_agent(self, *, system: str, user: str, ferramentas: list[Ferramenta], esquema_final: dict,
                  effort: str, max_tokens: int = 4096) -> ResultadoAgente: ...


def executar_ferramenta(ferramentas: list[Ferramenta], nome: str, entrada: dict) -> ChamadaFerramenta:
    """Roda a ferramenta; qualquer exceção vira resultado de erro (o modelo lê e se ajusta)."""
    f = next((x for x in ferramentas if x.nome == nome), None)
    if f is None:
        return ChamadaFerramenta(nome, entrada, f"ferramenta desconhecida: {nome}", erro=True)
    try:
        return ChamadaFerramenta(nome, entrada, f.fn(entrada))
    except Exception as exc:  # noqa: BLE001 - o erro é devolvido ao modelo como texto
        return ChamadaFerramenta(nome, entrada, f"erro na ferramenta {nome}: {exc}", erro=True)


def _ferramenta_final(esquema: dict) -> dict:
    return {
        "name": FERRAMENTA_FINAL,
        "description": "Entrega a explicação final ao aluno. Chame exatamente uma vez, quando terminar.",
        "strict": True,
        "input_schema": esquema,
        "cache_control": {"type": "ephemeral"},
    }


class AnthropicClient:
    def __init__(self, api_key: str, model: str, client: Any = None):
        self.model = model
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
        self._client = client

    def _create(self, **kwargs):
        import anthropic

        try:
            return self._client.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise ErroDoTreinador("chave_recusada", "a chave da API foi recusada; confira em Configurações") from exc
        except anthropic.RateLimitError as exc:
            raise ErroDoTreinador("limite_de_uso", "limite de uso da API atingido; tente de novo em alguns minutos") from exc
        except anthropic.BadRequestError as exc:
            raise ErroDoTreinador("requisicao_invalida", f"a API recusou o pedido: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise ErroDoTreinador("erro_da_api", f"erro da API ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ErroDoTreinador("sem_conexao", "sem conexão com a API da Anthropic") from exc

    def run_agent(self, *, system: str, user: str, ferramentas: list[Ferramenta], esquema_final: dict,
                  effort: str, max_tokens: int = 4096) -> ResultadoAgente:
        tools = [f.definicao() for f in ferramentas] + [_ferramenta_final(esquema_final)]
        messages: list[dict] = [{"role": "user", "content": user}]
        uso = Uso()
        chamadas: list[ChamadaFerramenta] = []
        textos: list[str] = []
        estruturado: dict | None = None
        stop_reason = "end_turn"
        n = 0
        for _ in range(MAX_ITERACOES):
            resp = self._create(
                model=self.model, max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                tools=tools, thinking={"type": "adaptive"}, output_config={"effort": effort}, messages=messages,
            )
            n += 1
            u = resp.usage
            uso = uso + Uso(u.input_tokens, u.output_tokens, u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0)
            stop_reason = resp.stop_reason
            if uso.output_tokens > TETO_TOKENS_SAIDA:
                raise ErroDoTreinador("custo_excedido", "a explicação passou do teto de tokens e foi interrompida")
            if stop_reason == "refusal":
                raise ErroDoTreinador("recusa", "o modelo recusou responder a este pedido")
            textos.extend(b.text for b in resp.content if b.type == "text")
            usos = [b for b in resp.content if b.type == "tool_use"]
            if not usos:
                break
            messages.append({"role": "assistant", "content": resp.content})
            resultados = []
            for b in usos:
                entrada = dict(b.input) if isinstance(b.input, dict) else json.loads(b.input)
                if b.name == FERRAMENTA_FINAL:
                    estruturado = entrada
                    resultados.append({"type": "tool_result", "tool_use_id": b.id, "content": "ok"})
                    continue
                ch = executar_ferramenta(ferramentas, b.name, entrada)
                chamadas.append(ch)
                item = {"type": "tool_result", "tool_use_id": b.id, "content": ch.resultado}
                if ch.erro:
                    item["is_error"] = True
                resultados.append(item)
            messages.append({"role": "user", "content": resultados})
            if estruturado is not None:
                break
        return ResultadoAgente("\n".join(t for t in textos if t), estruturado, uso, chamadas, stop_reason, self.model, n)
```

- [ ] **Step 4: `FakeLlm` em `tests/fakes.py`** (acrescentar)

```python
from chess_trainer.coach.costs import Uso
from chess_trainer.coach.llm import ResultadoAgente, executar_ferramenta


class FakeLlm:
    """Roteiros por chamada: cada passo é ("ferramenta", nome, entrada), ("texto", str) ou ("final", dict).
    As ferramentas do roteiro são executadas de verdade (exercitam o código das ferramentas)."""

    model = "fake"

    def __init__(self, roteiros: list[list[tuple]], uso: Uso = Uso(1000, 200, 500, 0)):
        self.roteiros = [list(r) for r in roteiros]
        self.uso = uso
        self.prompts: list[dict] = []

    def run_agent(self, *, system, user, ferramentas, esquema_final, effort, max_tokens=4096) -> ResultadoAgente:
        self.prompts.append({"system": system, "user": user, "ferramentas": [f.nome for f in ferramentas], "effort": effort})
        assert self.roteiros, "FakeLlm sem roteiro para esta chamada"
        roteiro = self.roteiros.pop(0)
        chamadas, textos, estruturado = [], [], None
        for passo in roteiro:
            if passo[0] == "ferramenta":
                chamadas.append(executar_ferramenta(ferramentas, passo[1], passo[2]))
            elif passo[0] == "final":
                estruturado = dict(passo[1])
            else:
                textos.append(passo[1])
        return ResultadoAgente("\n".join(textos), estruturado, self.uso, chamadas, "end_turn", self.model, 1)
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd backend && uv run pytest tests/test_coach_llm.py -q`
Expected: 7 passed. Se as classes de erro do SDK exigirem outra assinatura no construtor, confira com `uv run python -c "import anthropic, inspect; print(inspect.signature(anthropic.APIStatusError.__init__))"` e ajuste o helper `status()` do teste (não o mapeamento).

- [ ] **Step 6: Commit**

```bash
git add backend/chess_trainer/coach/llm.py backend/tests/fakes.py backend/tests/test_coach_llm.py
printf 'feat(treinador): cliente LLM com loop de ferramentas e dublê para testes\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n' > "$TEMP/msg.txt" && git commit -F "$TEMP/msg.txt"
```

---

### Task 7: Contexto do exercício, ferramentas e prompts

**Files:**
- Create: `backend/chess_trainer/coach/tools.py`, `backend/chess_trainer/coach/prompts.py`
- Modify: `backend/tests/factories.py` (`make_puzzle(..., solution=None, kind=..., move_played=..., move_uci=...)`)
- Test: `backend/tests/test_coach_tools.py`, `backend/tests/test_coach_prompts.py`

**Interfaces:**
- Consumes: `Puzzle`, `Position`, `Game.pgn`, `core.stats.theme_stats`, `core.tactics.themes.THEME_LABELS, normalize_own_theme`, `coach.llm.Ferramenta`, `coach.verify.Analisar`.
- Produces: `ContextoExercicio` (dataclass) com `puzzle_id, tipo ("punir"|"evitar"|"estudo"|"lichess"), lado ("brancas"|"pretas"), fen_inicial, fen_erro: str | None, solucao_san: list[str], lance_errado: dict | None, minha_resposta: dict | None, partida: dict | None, tema: str, categoria: str, lances_permitidos: set[str]`, métodos `.to_dict()` e `.texto() -> str`; `contexto_do_exercicio(db, puzzle) -> ContextoExercicio`; `ferramentas_do_treinador(contexto, analisar: Analisar, estatisticas: Callable[[int], list[dict]] | None, buscar: Callable[[str, int], list[dict]] | None) -> list[Ferramenta]`; `prompts.PROMPT_VERSION = "v1"`, `prompts.SYSTEM_PROMPT`, `prompts.ESQUEMA_EXPLICACAO`, `prompts.mensagem_inicial(contexto_texto: str, trechos: list[dict]) -> str`, `prompts.mensagem_de_correcao(resposta_anterior: dict, verificacao: dict) -> str`.
- Avaliações nas ferramentas: sempre **ponto de vista das brancas**, em centipeões inteiros; a ferramenta converte o `score` (lado a mover) do analisador.

- [ ] **Step 1: Estender a factory** — em `tests/factories.py`, `make_puzzle` ganha os parâmetros `solution: dict | None = None`, `move_played: str = "x"`, `move_uci: str = "a2a3"`, `ply: int = 1`, `mistake_by: str = "opponent"`; use-os na `Position` e no `Puzzle` (`solution=json.dumps(solution) if solution else <o literal atual>`; `solver_moves` = quantidade de `by == "solver"` quando `solution` vier). Rode `uv run pytest -q` para garantir que nada quebrou.

- [ ] **Step 2: Testes das ferramentas (falhando)**

`backend/tests/test_coach_tools.py`:

```python
import json

import chess

from chess_trainer.coach.tools import ContextoExercicio, contexto_do_exercicio, ferramentas_do_treinador
from chess_trainer.core.evals import MATE_SCORE
from chess_trainer.core.models import Game, Position
from tests.factories import make_puzzle

FEN_ERRO = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3"   # pretas jogam Nf6??
FEN = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"        # exercício: Qxf7#
PGN = '[Event "x"]\n[White "eu"]\n[Black "ele"]\n[Result "1-0"]\n\n1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0'


def puzzle_punir(db):
    game = Game(source_id="g-1", pgn=PGN, white="eu", black="ele", result="1-0", time_control="600", category="rapid",
                played_at=__import__("datetime").datetime(2026, 8, 1), my_color="white")
    db.add(game)
    db.flush()
    pos = Position(game_id=game.id, ply=6, fen=FEN_ERRO, move_played="Nf6", move_uci="g8f6", eval_before=200, eval_after=MATE_SCORE - 1,
                   best_move="g7g6", best_eval=200, is_mistake=True, mistake_level="blunder", mistake_by="opponent")
    db.add(pos)
    db.flush()
    db.add(Position(game_id=game.id, ply=7, fen=FEN, move_played="Qxf7#", move_uci="h5f7", eval_before=MATE_SCORE - 1,
                    eval_after=MATE_SCORE, best_move="h5f7", best_eval=MATE_SCORE, is_mistake=False))
    from chess_trainer.core.models import Puzzle
    p = Puzzle(position_id=pos.id, game_id=game.id, kind="punish", fen_start=FEN, side_to_move="white",
               solution=json.dumps({"moves": [{"uci": "h5f7", "by": "solver", "alternatives": []}], "explanation_pv": []}),
               end_reason="mate", theme="mate_in_1", category="rapid", solver_moves=1)
    db.add(p)
    db.commit()
    return p


def test_contexto_de_um_punir_com_partida(db_session):
    p = puzzle_punir(db_session)
    ctx = contexto_do_exercicio(db_session, p)
    assert ctx.tipo == "punir" and ctx.lado == "brancas" and ctx.fen_inicial == FEN and ctx.fen_erro == FEN_ERRO
    assert ctx.solucao_san == ["Qxf7#"] and ctx.tema == "mate em 1"
    assert ctx.lance_errado == {"san": "Nf6", "uci": "g8f6", "de_quem": "adversário", "nivel": "blunder",
                                "aval_antes": 200, "aval_depois": MATE_SCORE - 1}
    assert ctx.minha_resposta == {"san": "Qxf7#", "uci": "h5f7", "achou": True, "aval_antes": MATE_SCORE - 1, "aval_depois": MATE_SCORE}
    assert ctx.partida["brancas"] == "eu" and ctx.partida["meu_lado"] == "brancas"
    assert ctx.partida["lances_em_volta"] == "1.e4 e5 2.Qh5 Nc6 3.Bc4 Nf6 4.Qxf7#"
    assert ctx.lances_permitidos == {"h5f7", "g8f6"}
    texto = ctx.texto()
    assert "Qxf7#" in texto and "Nf6" in texto and "FEN" in texto
    assert json.loads(json.dumps(ctx.to_dict()))["tipo"] == "punir"


def test_contexto_de_um_evitar_sem_resposta(db_session):
    p = make_puzzle(db_session, fen=FEN, kind="avoid", move_played="Qh5", move_uci="d1h5", mistake_by="me")
    ctx = contexto_do_exercicio(db_session, p)
    assert ctx.tipo == "evitar" and ctx.lance_errado["de_quem"] == "você" and ctx.minha_resposta is None
    assert "a2a4" in ctx.lances_permitidos and "d1h5" in ctx.lances_permitidos


def test_ferramentas_do_treinador(db_session):
    p = puzzle_punir(db_session)
    ctx = contexto_do_exercicio(db_session, p)

    def analisar(fen, multipv):
        return {"fen": fen, "turn": "white", "terminal": None,
                "lines": [{"move": "h5f7", "san": "Qxf7#", "score": MATE_SCORE - 1, "pv": ["h5f7"], "pv_san": ["Qxf7#"]}][:multipv]}

    buscas = []
    ferr = ferramentas_do_treinador(ctx, analisar, estatisticas=lambda dias: [{"theme": "fork", "label": "garfo", "attempts": 3, "accuracy": 0.5}],
                                    buscar=lambda consulta, k: buscas.append((consulta, k)) or [{"chunk_id": "ab12", "texto": "t"}])
    por_nome = {f.nome: f for f in ferr}
    assert set(por_nome) == {"analisar_posicao", "contexto_do_exercicio", "estatisticas_por_tema", "buscar_estudos"}
    linhas = json.loads(por_nome["analisar_posicao"].fn({"fen": FEN, "multipv": 1}))
    assert linhas["linhas"][0]["lance"] == "Qxf7#" and linhas["linhas"][0]["avaliacao_brancas_cp"] == MATE_SCORE - 1
    # com as pretas a mover, o score do lado a mover vira negativo para as brancas
    linhas2 = json.loads(por_nome["analisar_posicao"].fn({"fen": FEN_ERRO, "multipv": 1}))
    assert linhas2["linhas"][0]["avaliacao_brancas_cp"] == -(MATE_SCORE - 1)
    assert json.loads(por_nome["contexto_do_exercicio"].fn({}))["tipo"] == "punir"
    assert json.loads(por_nome["estatisticas_por_tema"].fn({"dias": 30}))[0]["label"] == "garfo"
    assert json.loads(por_nome["buscar_estudos"].fn({"consulta": "garfo", "k": 2}))[0]["chunk_id"] == "ab12" and buscas == [("garfo", 2)]
    # sem busca disponível, a ferramenta não existe
    assert "buscar_estudos" not in {f.nome for f in ferramentas_do_treinador(ctx, analisar, None, None)}
    # FEN inválida vira erro de ferramenta (o cliente empacota), não exceção sem tratamento
    import pytest
    with pytest.raises(ValueError):
        por_nome["analisar_posicao"].fn({"fen": "lixo", "multipv": 1})
```

- [ ] **Step 3: Testes dos prompts (falhando)**

`backend/tests/test_coach_prompts.py`:

```python
import jsonschema  # se não estiver instalado: `uv add --dev jsonschema`

from chess_trainer.coach.llm import FERRAMENTA_FINAL
from chess_trainer.coach.prompts import ESQUEMA_EXPLICACAO, PROMPT_VERSION, SYSTEM_PROMPT, mensagem_de_correcao, mensagem_inicial


def test_esquema_estrito_valida_uma_resposta_boa_e_recusa_uma_ruim():
    boa = {"texto": "x", "linhas": [{"inicio": "erro", "lances": ["Nf6", "Qxf7#"], "avaliacao_cp": None, "mate_em": 0}],
           "citacoes": [], "padrao": None, "treinar": ["mates com dama e bispo"]}
    jsonschema.validate(boa, ESQUEMA_EXPLICACAO)
    import pytest
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"texto": "x"}, ESQUEMA_EXPLICACAO)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**boa, "linhas": [{"inicio": "meio", "lances": []}]}, ESQUEMA_EXPLICACAO)
    assert ESQUEMA_EXPLICACAO["additionalProperties"] is False


def test_prompt_de_sistema_tem_as_regras_duras():
    assert PROMPT_VERSION == "v1"
    for trecho in ("analisar_posicao", "ponto de vista das brancas", "[c:", "inicial", "erro", FERRAMENTA_FINAL, "português"):
        assert trecho in SYSTEM_PROMPT, trecho


def test_mensagens():
    m = mensagem_inicial("## Exercício\nFEN: x", [{"chunk_id": "ab12", "estudo": "E", "capitulo": "C", "caminho_san": "1.e4", "texto": "Comentário sintético."}])
    assert "## Exercício" in m and "[c:ab12]" in m and "Comentário sintético." in m and "E — C — 1.e4" in m
    vazio = mensagem_inicial("ctx", [])
    assert "nenhum trecho" in vazio.lower()
    c = mensagem_de_correcao({"texto": "antes"}, {"ok": False, "issues": [{"tipo": "lance_ilegal", "gravidade": "erro", "detalhe": "'Qxf8' não é legal", "linha_idx": 0}]})
    assert "lance_ilegal" in c and "Qxf8" in c and "antes" in c
```

- [ ] **Step 4: Rodar e ver falhar**

Run: `cd backend && uv run pytest tests/test_coach_tools.py tests/test_coach_prompts.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 5: Implementar `prompts.py`**

```python
"""Prompt do treinador e esquema da resposta (spec §4.3, §4.4). Versionado:
`PROMPT_VERSION` vai gravado em cada explicação e no relatório da avaliação."""
from __future__ import annotations

import json

from chess_trainer.coach.llm import FERRAMENTA_FINAL

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = f"""Você é o treinador de xadrez do aluno dentro do app dele. O aluno acabou de fazer um
exercício criado a partir de um erro (dele ou do adversário) numa partida dele, ou de um estudo, e
quer entender o que aconteceu. Escreva em português do Brasil, direto, sem elogio vazio, entre 120 e
250 palavras.

Regras que você não pode quebrar:
1. Só cite lances que vieram do contexto do exercício ou da ferramenta `analisar_posicao`. Nunca
   invente um lance nem uma continuação. Se tiver dúvida sobre uma linha, analise a posição antes.
2. Escreva os lances em notação inglesa (K, Q, R, B, N; ex.: Nf3, Bxf7+, O-O), como o app mostra.
3. Toda sequência de lances do texto tem de aparecer também em `linhas`, declarando de onde parte:
   `inicial` (a posição do exercício) ou `erro` (a posição imediatamente antes do lance errado).
4. Avaliações sempre da engine, sempre do ponto de vista das brancas, em peões no texto (`+1,5`, `-0,4`,
   `mate em 2`) e em `avaliacao_cp` (centipeões inteiros) ou `mate_em` na linha. Os dois descrevem a
   posição no FIM da linha; `mate_em: 0` quer dizer que a linha termina em mate.
5. Cite um estudo só quando o trecho recebido for pertinente, escrevendo o marcador `[c:ID]` no texto
   logo após a frase que se apoia nele, com o ID exato do trecho. Sem trecho pertinente, não fale de estudos.
6. Não invente nome de abertura nem de padrão tático sem apoio no contexto ou nos trechos.
7. Quando terminar, chame a ferramenta `{FERRAMENTA_FINAL}` exatamente uma vez com a resposta completa.

Estrutura sugerida do texto: o que aconteceu na partida; por que o lance perde (a ideia, não só a
linha); o padrão por trás; onde isso aparece nos estudos do aluno, se aparecer; o que treinar.
`treinar` traz de uma a três ações concretas e curtas. `padrao` é um nome curto do padrão tático em
inglês, no estilo dos temas do Lichess (ex.: `hangingPiece`, `fork`, `backRankMate`), ou nulo.
"""

ESQUEMA_EXPLICACAO: dict = {
    "type": "object",
    "properties": {
        "texto": {"type": "string", "description": "A explicação em português, com os lances e os marcadores [c:ID]."},
        "linhas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "inicio": {"type": "string", "enum": ["inicial", "erro"]},
                    "lances": {"type": "array", "items": {"type": "string"}},
                    "avaliacao_cp": {"type": ["integer", "null"], "description": "Avaliação no fim da linha, ponto de vista das brancas."},
                    "mate_em": {"type": ["integer", "null"], "description": "Mate em N no fim da linha; 0 = a linha termina em mate."},
                },
                "required": ["inicio", "lances", "avaliacao_cp", "mate_em"],
                "additionalProperties": False,
            },
        },
        "citacoes": {"type": "array", "items": {"type": "string"}},
        "padrao": {"type": ["string", "null"]},
        "treinar": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["texto", "linhas", "citacoes", "padrao", "treinar"],
    "additionalProperties": False,
}


def mensagem_inicial(contexto_texto: str, trechos: list[dict]) -> str:
    partes = [contexto_texto, "", "## Trechos dos estudos do aluno"]
    if not trechos:
        partes.append("Nenhum trecho recuperado: não cite estudos nesta explicação.")
    for t in trechos:
        cabecalho = " — ".join(x for x in (t.get("estudo", ""), t.get("capitulo", ""), t.get("caminho_san", "")) if x)
        partes.append(f"- [c:{t['chunk_id']}] {cabecalho}: {t.get('texto', '')}")
    partes += ["", "Explique o erro deste exercício para o aluno e entregue a resposta pela ferramenta."]
    return "\n".join(partes)


def mensagem_de_correcao(resposta_anterior: dict, verificacao: dict) -> str:
    problemas = "\n".join(
        f"- [{i.get('gravidade')}] {i.get('tipo')}"
        + (f" (linha {i['linha_idx']})" if i.get("linha_idx") is not None else "")
        + f": {i.get('detalhe', '')}"
        for i in verificacao.get("issues", [])
    )
    return (
        "\n\n## Sua resposta anterior\n```json\n" + json.dumps(resposta_anterior, ensure_ascii=False) + "\n```\n\n"
        "## Relatório de verificação\nO verificador reproduziu suas linhas no tabuleiro e conferiu com a engine. Problemas:\n"
        + problemas
        + "\n\nCorrija a resposta: reanalise as posições com `analisar_posicao` se preciso, remova ou conserte cada "
        "linha apontada, mantenha só citações que existem, e entregue a versão corrigida pela ferramenta."
    )
```

- [ ] **Step 6: Implementar `tools.py`**

```python
"""Contexto do exercício e ferramentas do agente (spec §4.2). O contexto é um
dado puro (serve ao pipeline, ao verificador e à avaliação offline); as
ferramentas são funções finas sobre o que o app já tem."""
from __future__ import annotations

import io
import json
from dataclasses import asdict, dataclass, field
from typing import Callable

import chess
import chess.pgn
from sqlalchemy import select
from sqlalchemy.orm import Session

from chess_trainer.coach.llm import Ferramenta
from chess_trainer.coach.verify import Analisar
from chess_trainer.core.models import Position, Puzzle
from chess_trainer.core.tactics.themes import THEME_LABELS, normalize_own_theme

JANELA_PLIES = 6


@dataclass
class ContextoExercicio:
    puzzle_id: str
    tipo: str  # punir | evitar | estudo | lichess
    lado: str  # brancas | pretas
    fen_inicial: str
    fen_erro: str | None
    solucao_san: list[str]
    lance_errado: dict | None
    minha_resposta: dict | None
    partida: dict | None
    tema: str
    categoria: str
    lances_permitidos: set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["lances_permitidos"] = sorted(self.lances_permitidos)
        return d

    def texto(self) -> str:
        linhas = ["## Exercício", f"Tipo: {self.tipo}. O aluno joga de {self.lado}. Tema: {self.tema}. Categoria: {self.categoria}.",
                  f"FEN da posição do exercício (inicial): {self.fen_inicial}",
                  f"Solução do exercício: {' '.join(self.solucao_san) or '(sem lances)'}"]
        if self.fen_erro:
            linhas.append(f"FEN da posição antes do lance errado (erro): {self.fen_erro}")
        if self.lance_errado:
            e = self.lance_errado
            linhas.append(f"Lance errado ({e['de_quem']}, {e.get('nivel') or 'erro'}): {e['san']}; avaliação como o app mostra: "
                          f"{e['aval_antes']} → {e['aval_depois']} (use `analisar_posicao` para números confiáveis).")
        if self.minha_resposta:
            r = self.minha_resposta
            linhas.append(("Na partida o aluno achou a solução: " if r["achou"] else "Na partida o aluno respondeu ") + r["san"]
                          + ("" if r["achou"] else f" ({r['aval_antes']} → {r['aval_depois']}) e deixou passar a solução."))
        if self.partida:
            p = self.partida
            linhas.append(f"Partida: {p['brancas']} x {p['pretas']} ({p['resultado']}, {p['data']}); o aluno era {p['meu_lado']}.")
            linhas.append(f"Lances em volta do erro: {p['lances_em_volta']}")
        return "\n".join(linhas)


def _san_da_solucao(fen: str, moves: list[dict]) -> list[str]:
    board = chess.Board(fen)
    out = []
    for m in moves:
        try:
            mv = chess.Move.from_uci(m["uci"])
            out.append(board.san(mv))
            board.push(mv)
        except (ValueError, KeyError):
            break
    return out


def _lances_em_volta(pgn: str, ply: int) -> str:
    """Janela de ±6 plies em volta do lance de número `ply` (1 = primeiro lance), em SAN numerado."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return ""
    board = game.board()
    tokens: list[tuple[int, bool, str]] = []
    for mv in game.mainline_moves():
        tokens.append((board.fullmove_number, board.turn == chess.WHITE, board.san(mv)))
        board.push(mv)
    ini, fim = max(0, ply - 1 - JANELA_PLIES), min(len(tokens), ply + JANELA_PLIES)
    out = []
    for i, (numero, brancas, san) in enumerate(tokens[ini:fim]):
        if brancas:
            out.append(f"{numero}.{san}")
        elif i == 0:
            out.append(f"{numero}...{san}")  # a janela começa num lance das pretas
        else:
            out.append(san)
    return " ".join(out)


def _tema(theme: str) -> str:
    return THEME_LABELS.get(normalize_own_theme(theme), theme)


def contexto_do_exercicio(db: Session, puzzle: Puzzle) -> ContextoExercicio:
    sol = puzzle.solution_data.get("moves", [])
    lado = "brancas" if puzzle.side_to_move == "white" else "pretas"
    if puzzle.source == "study":
        tipo = "estudo"
    elif puzzle.source == "lichess":
        tipo = "lichess"
    else:
        tipo = "evitar" if puzzle.kind == "avoid" else "punir"
    permitidos: set[str] = set()
    if sol:
        permitidos.add(sol[0]["uci"])
        permitidos.update(sol[0].get("alternatives", []))
    pos = puzzle.position
    lance_errado = minha_resposta = partida = None
    fen_erro = puzzle.fen_before
    if pos is not None:
        fen_erro = pos.fen
        de_quem = "você" if (pos.mistake_by == "me" or (pos.mistake_by is None and tipo == "evitar")) else "adversário"
        lance_errado = {"san": pos.move_played, "uci": pos.move_uci, "de_quem": de_quem, "nivel": pos.mistake_level,
                        "aval_antes": pos.eval_before, "aval_depois": pos.eval_after}
        permitidos.add(pos.move_uci)
        if tipo == "punir":
            seguinte = db.scalar(select(Position).where(Position.game_id == pos.game_id, Position.ply == pos.ply + 1))
            if seguinte is not None:
                achou = bool(sol) and (seguinte.move_uci == sol[0]["uci"] or seguinte.move_uci in sol[0].get("alternatives", []))
                minha_resposta = {"san": seguinte.move_played, "uci": seguinte.move_uci, "achou": achou,
                                  "aval_antes": seguinte.eval_before, "aval_depois": seguinte.eval_after}
                permitidos.add(seguinte.move_uci)
    game = puzzle.game
    if game is not None and pos is not None:
        partida = {"brancas": game.white, "pretas": game.black, "resultado": game.result,
                   "data": game.played_at.date().isoformat(), "meu_lado": "brancas" if game.my_color == "white" else "pretas",
                   "lances_em_volta": _lances_em_volta(game.pgn, pos.ply)}
    elif puzzle.last_move and puzzle.fen_before:
        # táticas e estudos: o "erro" é o último lance do adversário
        b = chess.Board(puzzle.fen_before)
        try:
            mv = chess.Move.from_uci(puzzle.last_move)
            lance_errado = {"san": b.san(mv), "uci": puzzle.last_move, "de_quem": "adversário", "nivel": None, "aval_antes": None, "aval_depois": None}
            permitidos.add(puzzle.last_move)
        except ValueError:
            pass
    return ContextoExercicio(
        puzzle_id=puzzle.id, tipo=tipo, lado=lado, fen_inicial=puzzle.fen_start, fen_erro=fen_erro,
        solucao_san=_san_da_solucao(puzzle.fen_start, sol), lance_errado=lance_errado, minha_resposta=minha_resposta,
        partida=partida, tema=_tema(puzzle.theme), categoria=puzzle.category, lances_permitidos=permitidos,
    )


def _analisar_posicao(analisar: Analisar) -> Callable[[dict], str]:
    def fn(entrada: dict) -> str:
        fen = str(entrada.get("fen", ""))
        board = chess.Board(fen)  # ValueError em FEN inválida: vira erro de ferramenta
        multipv = max(1, min(3, int(entrada.get("multipv", 3))))
        a = analisar(board.fen(), multipv)
        sinal = 1 if board.turn == chess.WHITE else -1
        linhas = [{"lance": l["san"], "avaliacao_brancas_cp": sinal * int(l["score"]), "continuacao": list(l.get("pv_san", []))[:8]}
                  for l in a.get("lines", [])]
        return json.dumps({"fen": board.fen(), "lado_a_mover": "brancas" if board.turn else "pretas",
                           "terminal": a.get("terminal"), "linhas": linhas}, ensure_ascii=False)
    return fn


def ferramentas_do_treinador(contexto: ContextoExercicio, analisar: Analisar,
                             estatisticas: Callable[[int], list[dict]] | None,
                             buscar: Callable[[str, int], list[dict]] | None) -> list[Ferramenta]:
    ferr = [
        Ferramenta("analisar_posicao", "Analisa uma posição com o Stockfish: melhores lances, avaliação (ponto de vista das brancas, centipeões) e continuação.",
                   {"type": "object", "properties": {"fen": {"type": "string"}, "multipv": {"type": "integer", "minimum": 1, "maximum": 3}},
                    "required": ["fen"], "additionalProperties": False}, _analisar_posicao(analisar)),
        Ferramenta("contexto_do_exercicio", "Devolve de novo o contexto completo do exercício (posições, solução, lance errado, partida).",
                   {"type": "object", "properties": {}, "additionalProperties": False},
                   lambda _e: json.dumps(contexto.to_dict(), ensure_ascii=False)),
    ]
    if estatisticas is not None:
        ferr.append(Ferramenta("estatisticas_por_tema", "Acerto do aluno por tema tático nos últimos N dias (padrão 90).",
                               {"type": "object", "properties": {"dias": {"type": "integer", "minimum": 1, "maximum": 3650}}, "additionalProperties": False},
                               lambda e: json.dumps(estatisticas(int(e.get("dias", 90)))[:10], ensure_ascii=False)))
    if buscar is not None:
        ferr.append(Ferramenta("buscar_estudos", "Busca trechos nos estudos e livros que o aluno está lendo. Devolve chunk_id para citar com [c:ID].",
                               {"type": "object", "properties": {"consulta": {"type": "string"}, "k": {"type": "integer", "minimum": 1, "maximum": 10}},
                                "required": ["consulta"], "additionalProperties": False},
                               lambda e: json.dumps(buscar(str(e["consulta"]), int(e.get("k", 5))), ensure_ascii=False)))
    return ferr
```

- [ ] **Step 7: Rodar e ver passar**

Run: `cd backend && uv run pytest tests/test_coach_tools.py tests/test_coach_prompts.py -q`
Expected: 6 passed.

- [ ] **Step 8: Commit**

```bash
git add backend/chess_trainer/coach/tools.py backend/chess_trainer/coach/prompts.py backend/tests/factories.py backend/tests/test_coach_tools.py backend/tests/test_coach_prompts.py backend/pyproject.toml backend/uv.lock
printf 'feat(treinador): contexto do exercício, ferramentas do agente e prompt versionado\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n' > "$TEMP/msg.txt" && git commit -F "$TEMP/msg.txt"
```

---

### Task 8: Pipeline `explicar` e `gravar`

**Files:**
- Create: `backend/chess_trainer/coach/explain.py`, `backend/chess_trainer/coach/observability.py` (só `Tracer` + `NoopTracer` nesta tarefa)
- Modify: `backend/tests/fakes.py` (`FakeTracer`)
- Test: `backend/tests/test_coach_explain.py`

**Interfaces:**
- Consumes: tudo das tarefas 2, 6, 7; `CoachExplanation`.
- Produces: `observability.Tracer` (Protocol: `span(nome: str, **meta)` context manager; `geracao(nome: str, model: str, uso: Uso, custo: float, **meta) -> None`; `trace_id() -> str | None`; `url(trace_id) -> str | None`; `flush() -> None`), `observability.NoopTracer`; `explain.OpcoesExplicacao(variante="agente_rag", effort="high", k_trechos=5)`; `explain.ResultadoExplicacao` (dataclass: `contexto: ContextoExercicio, model, prompt_version, effort, variante, texto, estruturado: dict | None, linhas: list[dict], citacoes: list[dict], verificacao: Verificacao, status: str, repaired: bool, uso: Uso, custo_usd: float, duration_ms: int, trace_id: str | None, n_chamadas_api: int, trechos: list[dict]`); `explain.explicar(*, contexto, llm, analisar, estatisticas, buscar, opcoes, tracer=None) -> ResultadoExplicacao`; `explain.consulta_de_busca(contexto) -> str`; `explain.gravar(db, resultado, review_id: str | None) -> CoachExplanation`; `tests.fakes.FakeTracer` (guarda `spans: list[tuple[str, dict]]`, `geracoes: list[dict]`, `trace_id() == "trace-falso"`).
- `status`: `"ok"` (sem issues), `"warnings"` (só avisos), `"errors"`.

- [ ] **Step 1: `observability.py` (mínimo) e `FakeTracer`**

```python
"""Rastreio das etapas do treinador (spec §8.3). `NoopTracer` quando o LangFuse
não está configurado; `LangfuseTracer` entra na tarefa seguinte."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Protocol

from chess_trainer.coach.costs import Uso


class Tracer(Protocol):
    def span(self, nome: str, **meta) -> Iterator[None]: ...

    def geracao(self, nome: str, model: str, uso: Uso, custo: float, **meta) -> None: ...

    def trace_id(self) -> str | None: ...

    def url(self, trace_id: str | None) -> str | None: ...

    def flush(self) -> None: ...


class NoopTracer:
    @contextmanager
    def span(self, nome: str, **meta):
        yield

    def geracao(self, nome: str, model: str, uso: Uso, custo: float, **meta) -> None:
        pass

    def trace_id(self) -> str | None:
        return None

    def url(self, trace_id: str | None) -> str | None:
        return None

    def flush(self) -> None:
        pass
```

Em `tests/fakes.py`:

```python
from contextlib import contextmanager


class FakeTracer:
    def __init__(self):
        self.spans: list[tuple[str, dict]] = []
        self.geracoes: list[dict] = []
        self.flushed = False

    @contextmanager
    def span(self, nome, **meta):
        self.spans.append((nome, meta))
        yield

    def geracao(self, nome, model, uso, custo, **meta):
        self.geracoes.append({"nome": nome, "model": model, "uso": uso, "custo": custo, **meta})

    def trace_id(self):
        return "trace-falso"

    def url(self, trace_id):
        return f"http://langfuse.local/trace/{trace_id}" if trace_id else None

    def flush(self):
        self.flushed = True
```

- [ ] **Step 2: Testes (falhando)**

`backend/tests/test_coach_explain.py`:

```python
import json

from chess_trainer.coach.costs import Uso
from chess_trainer.coach.explain import OpcoesExplicacao, consulta_de_busca, explicar, gravar
from chess_trainer.coach.llm import ErroDoTreinador
from chess_trainer.coach.prompts import PROMPT_VERSION
from chess_trainer.coach.tools import contexto_do_exercicio
from chess_trainer.core.evals import MATE_SCORE
from chess_trainer.core.models import CoachExplanation
from tests.fakes import FakeLlm, FakeTracer
from tests.test_coach_tools import FEN, FEN_ERRO, puzzle_punir

TEXTO = " ".join(["explicação"] * 70)


def analisar(fen, multipv):
    import chess
    b = chess.Board(fen)
    if b.is_game_over():
        return {"fen": fen, "turn": "white", "terminal": "checkmate", "lines": []}
    if b.fen() == FEN:
        return {"fen": fen, "turn": "white", "terminal": None, "lines": [{"move": "h5f7", "san": "Qxf7#", "score": MATE_SCORE - 1, "pv": ["h5f7"], "pv_san": ["Qxf7#"]}][:multipv]}
    mv = next(iter(b.legal_moves))
    return {"fen": fen, "turn": "white" if b.turn else "black", "terminal": None, "lines": [{"move": mv.uci(), "san": b.san(mv), "score": 0, "pv": [mv.uci()], "pv_san": [b.san(mv)]}]}


TRECHOS = [{"chunk_id": "ab12", "study_id": "s1", "estudo": "E", "chapter_id": "c1", "capitulo": "C", "node_id": "n1",
            "caminho_san": "1.e4", "texto": "Trecho sintético sobre mate com dama e bispo.", "url": "/estudos/s1/capitulos/c1?lance=n1"}]
BOA = {"texto": TEXTO + " A linha Qxf7# fecha. [c:ab12]", "linhas": [{"inicio": "inicial", "lances": ["Qxf7#"], "avaliacao_cp": None, "mate_em": 0}],
       "citacoes": ["ab12"], "padrao": "mateIn1", "treinar": ["mates com dama e bispo"]}


def rodar(db, llm, tracer=None, buscar=lambda consulta, k: TRECHOS, opcoes=None):
    ctx = contexto_do_exercicio(db, puzzle_punir(db))
    return explicar(contexto=ctx, llm=llm, analisar=analisar, estatisticas=lambda dias: [], buscar=buscar,
                    opcoes=opcoes or OpcoesExplicacao(), tracer=tracer)


def test_caminho_feliz_com_rag_e_citacao(db_session):
    llm = FakeLlm([[("ferramenta", "analisar_posicao", {"fen": FEN, "multipv": 1}), ("final", BOA)]])
    tracer = FakeTracer()
    r = rodar(db_session, llm, tracer)
    assert r.status == "ok" and r.verificacao.ok and not r.repaired and r.n_chamadas_api == 1
    assert r.citacoes == TRECHOS and r.linhas == BOA["linhas"] and r.prompt_version == PROMPT_VERSION
    assert r.uso == Uso(1000, 200, 500, 0) and r.custo_usd == 0.0 and r.trace_id == "trace-falso"
    assert "[c:ab12]" in llm.prompts[0]["user"] and "buscar_estudos" in llm.prompts[0]["ferramentas"]
    assert [s[0] for s in tracer.spans][:2] == ["coach.explain", "contexto"] and tracer.geracoes[0]["model"] == "fake"
    assert "Qxf7#" in consulta_de_busca(r.contexto) and "mate em 1" in consulta_de_busca(r.contexto)


def test_erro_de_verificacao_dispara_uma_correcao(db_session):
    ruim = {**BOA, "linhas": [{"inicio": "inicial", "lances": ["Qxf8"], "avaliacao_cp": None, "mate_em": None}]}
    llm = FakeLlm([[("final", ruim)], [("final", BOA)]])
    r = rodar(db_session, llm)
    assert r.repaired and r.status == "ok" and r.n_chamadas_api == 2 and r.uso == Uso(2000, 400, 1000, 0)
    assert "lance_ilegal" in llm.prompts[1]["user"] and "Qxf8" in llm.prompts[1]["user"]


def test_correcao_que_nao_melhora_mantem_a_primeira(db_session):
    ruim = {**BOA, "linhas": [{"inicio": "inicial", "lances": ["Qxf8"], "avaliacao_cp": None, "mate_em": None}]}
    pior = {**ruim, "citacoes": ["zzzz"], "texto": ruim["texto"] + " [c:zzzz]"}
    r = rodar(db_session, FakeLlm([[("final", ruim)], [("final", pior)]]))
    assert not r.repaired and r.status == "errors" and r.verificacao.erros == 1


def test_variantes_sem_busca_e_sem_ferramentas(db_session):
    llm = FakeLlm([[("final", {**BOA, "citacoes": [], "texto": TEXTO + " Qxf7#"})]])
    r = rodar(db_session, llm, opcoes=OpcoesExplicacao(variante="agente"))
    assert llm.prompts[0]["ferramentas"] == ["analisar_posicao", "contexto_do_exercicio", "estatisticas_por_tema"] and r.citacoes == []
    llm2 = FakeLlm([[("final", {**BOA, "citacoes": [], "texto": TEXTO + " Qxf7#"})]])
    rodar(db_session, llm2, opcoes=OpcoesExplicacao(variante="prompt"))
    assert llm2.prompts[0]["ferramentas"] == [] and "nenhum trecho" in llm2.prompts[0]["user"].lower()


def test_resposta_fora_do_esquema_tenta_de_novo_e_depois_falha(db_session):
    llm = FakeLlm([[("texto", "sem entrega")], [("final", BOA)]])
    assert rodar(db_session, llm).status == "ok"
    import pytest
    with pytest.raises(ErroDoTreinador) as exc:
        rodar(db_session, FakeLlm([[("texto", "x")], [("texto", "y")]]))
    assert exc.value.codigo == "resposta_fora_do_esquema"


def test_gravar_guarda_so_a_ultima(db_session):
    r = rodar(db_session, FakeLlm([[("final", BOA)]]))
    a = gravar(db_session, r, review_id=None)
    b = gravar(db_session, r, review_id=None)
    rows = db_session.query(CoachExplanation).filter_by(puzzle_id=r.contexto.puzzle_id).all()
    assert [x.id for x in rows] == [b.id] and a.id != b.id
    assert json.loads(b.verification_json)["ok"] and json.loads(b.citations_json)[0]["chunk_id"] == "ab12"
    assert b.status == "ok" and b.model == "fake" and b.input_tokens == 1000 and b.text.startswith("explicação")
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `cd backend && uv run pytest tests/test_coach_explain.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Step 4: Implementar `explain.py`**

```python
"""Pipeline da explicação (spec §7): contexto -> recuperação -> agente ->
verificação -> uma correção -> resultado. Não toca em banco: quem persiste é
`gravar`, o que permite rodar o mesmo pipeline na avaliação offline."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable

from chess_trainer.coach.costs import Uso, custo_usd
from chess_trainer.coach.llm import ErroDoTreinador, LlmClient
from chess_trainer.coach.observability import NoopTracer, Tracer
from chess_trainer.coach.prompts import ESQUEMA_EXPLICACAO, PROMPT_VERSION, SYSTEM_PROMPT, mensagem_de_correcao, mensagem_inicial
from chess_trainer.coach.tools import ContextoExercicio, ferramentas_do_treinador
from chess_trainer.coach.verify import Analisar, Verificacao, verificar
from chess_trainer.core.models import CoachExplanation

VARIANTES = ("prompt", "agente", "agente_rag")


@dataclass(frozen=True)
class OpcoesExplicacao:
    variante: str = "agente_rag"
    effort: str = "high"
    k_trechos: int = 5


@dataclass
class ResultadoExplicacao:
    contexto: ContextoExercicio
    model: str
    prompt_version: str
    effort: str
    variante: str
    texto: str
    estruturado: dict | None
    linhas: list[dict]
    citacoes: list[dict]
    verificacao: Verificacao
    status: str
    repaired: bool
    uso: Uso
    custo_usd: float
    duration_ms: int
    trace_id: str | None
    n_chamadas_api: int
    trechos: list[dict] = field(default_factory=list)


def consulta_de_busca(ctx: ContextoExercicio) -> str:
    partes = [ctx.tema, " ".join(ctx.solucao_san[:2])]
    if ctx.lance_errado:
        partes.append(f"erro {ctx.lance_errado['san']}")
    if ctx.partida:
        partes.append(ctx.partida.get("lances_em_volta", ""))
    return " ".join(p for p in partes if p).strip()


def _status(v: Verificacao) -> str:
    if not v.ok:
        return "errors"
    return "warnings" if v.issues else "ok"


def _verificar(estruturado: dict, ctx: ContextoExercicio, trechos: list[dict], analisar: Analisar) -> Verificacao:
    return verificar(estruturado, fen_inicial=ctx.fen_inicial, fen_erro=ctx.fen_erro,
                     lances_permitidos=set(ctx.lances_permitidos), trechos_ids={t["chunk_id"] for t in trechos}, analisar=analisar)


def explicar(*, contexto: ContextoExercicio, llm: LlmClient, analisar: Analisar,
             estatisticas: Callable[[int], list[dict]] | None, buscar: Callable[[str, int], list[dict]] | None,
             opcoes: OpcoesExplicacao, tracer: Tracer | None = None) -> ResultadoExplicacao:
    tracer = tracer or NoopTracer()
    if opcoes.variante not in VARIANTES:
        raise ValueError(f"variante desconhecida: {opcoes.variante}")
    inicio = time.monotonic()
    with tracer.span("coach.explain", puzzle_id=contexto.puzzle_id, variante=opcoes.variante, prompt_version=PROMPT_VERSION, model=llm.model):
        trace_id = tracer.trace_id()
        with tracer.span("contexto"):
            texto_ctx = contexto.texto()
        trechos: list[dict] = []
        if opcoes.variante == "agente_rag" and buscar is not None:
            with tracer.span("recuperacao"):
                trechos = buscar(consulta_de_busca(contexto), opcoes.k_trechos)
        if opcoes.variante == "prompt":
            ferramentas = []
        else:
            ferramentas = ferramentas_do_treinador(contexto, analisar, estatisticas,
                                                   buscar if opcoes.variante == "agente_rag" else None)
        user = mensagem_inicial(texto_ctx, trechos)
        uso = Uso()
        n_api = 0

        def chamar(nome: str, mensagem: str):
            nonlocal uso, n_api
            with tracer.span(nome):
                r = llm.run_agent(system=SYSTEM_PROMPT, user=mensagem, ferramentas=ferramentas,
                                  esquema_final=ESQUEMA_EXPLICACAO, effort=opcoes.effort)
            uso = uso + r.uso
            n_api += r.n_chamadas_api
            tracer.geracao(nome, llm.model, r.uso, custo_usd(llm.model, r.uso), chamadas=[c.nome for c in r.chamadas])
            return r

        r1 = chamar("llm", user)
        if r1.estruturado is None:
            r1 = chamar("llm_retentativa", user)
            if r1.estruturado is None:
                raise ErroDoTreinador("resposta_fora_do_esquema", "o modelo não entregou a explicação no formato esperado")
        with tracer.span("verificacao"):
            v1 = _verificar(r1.estruturado, contexto, trechos, analisar)
        escolhido, v, repaired = r1, v1, False
        if not v1.ok:
            r2 = chamar("correcao", user + mensagem_de_correcao(r1.estruturado, v1.to_dict()))
            if r2.estruturado is not None:
                with tracer.span("verificacao_correcao"):
                    v2 = _verificar(r2.estruturado, contexto, trechos, analisar)
                if v2.erros < v1.erros:
                    escolhido, v, repaired = r2, v2, True
        est = escolhido.estruturado or {}
        citadas = {str(c) for c in est.get("citacoes", [])}
        citacoes = [t for t in trechos if t["chunk_id"] in citadas]
        resultado = ResultadoExplicacao(
            contexto=contexto, model=llm.model, prompt_version=PROMPT_VERSION, effort=opcoes.effort, variante=opcoes.variante,
            texto=str(est.get("texto", "")), estruturado=est, linhas=list(est.get("linhas", [])), citacoes=citacoes,
            verificacao=v, status=_status(v), repaired=repaired, uso=uso, custo_usd=custo_usd(llm.model, uso),
            duration_ms=int((time.monotonic() - inicio) * 1000), trace_id=trace_id, n_chamadas_api=n_api, trechos=trechos,
        )
    tracer.flush()
    return resultado


def gravar(db, resultado: ResultadoExplicacao, review_id: str | None) -> CoachExplanation:
    """Guarda a explicação e apaga as anteriores do mesmo exercício (só a última fica)."""
    for antiga in db.query(CoachExplanation).filter_by(puzzle_id=resultado.contexto.puzzle_id).all():
        db.delete(antiga)
    row = CoachExplanation(
        puzzle_id=resultado.contexto.puzzle_id, review_id=review_id, model=resultado.model,
        prompt_version=resultado.prompt_version, effort=resultado.effort, variante=resultado.variante,
        text=resultado.texto, lines_json=json.dumps(resultado.linhas, ensure_ascii=False),
        citations_json=json.dumps(resultado.citacoes, ensure_ascii=False),
        verification_json=json.dumps(resultado.verificacao.to_dict(), ensure_ascii=False),
        status=resultado.status, repaired=resultado.repaired,
        input_tokens=resultado.uso.input_tokens, output_tokens=resultado.uso.output_tokens,
        cache_read_tokens=resultado.uso.cache_read_tokens, cache_write_tokens=resultado.uso.cache_write_tokens,
        cost_usd=resultado.custo_usd, trace_id=resultado.trace_id, duration_ms=resultado.duration_ms,
    )
    db.add(row)
    db.commit()
    return row
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd backend && uv run pytest tests/test_coach_explain.py -q`
Expected: 6 passed. Em `test_caminho_feliz`, se o verificador acusar `lance_sem_linha` ou `tamanho`, o `texto` de `BOA` precisa ter entre 60 e 400 palavras e só o lance `Qxf7#` fora das linhas... ele já está na linha; se ainda assim falhar, imprima `r.verificacao.to_dict()` e corrija o pipeline (não afrouxe o teste).

- [ ] **Step 6: Commit**

```bash
git add backend/chess_trainer/coach/explain.py backend/chess_trainer/coach/observability.py backend/tests/fakes.py backend/tests/test_coach_explain.py
printf 'feat(treinador): pipeline de explicação com verificação, correção e gravação\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n' > "$TEMP/msg.txt" && git commit -F "$TEMP/msg.txt"
```

---

### Task 9: `LangfuseTracer`

**Files:**
- Modify: `backend/chess_trainer/coach/observability.py`
- Test: `backend/tests/test_coach_observability.py`

**Interfaces:**
- Produces: `LangfuseTracer(public_key, secret_key, host, client=None)`; `tracer_de(settings: AppSettings, cache: dict | None = None) -> Tracer` (devolve `NoopTracer` sem host ou chaves; reaproveita a instância do `cache` pela tupla `(public_key, secret_key, host)`).
- O SDK do LangFuse v4 é OpenTelemetry: `Langfuse(public_key=..., secret_key=..., host=...)`, `start_as_current_observation(as_type="span"|"generation", name=...)` (context manager cujo objeto tem `.update(...)`), `get_current_trace_id()`, `flush()`. **Confira as assinaturas no pacote instalado** (`uv run python -c "import langfuse, inspect; print(inspect.signature(langfuse.Langfuse.start_as_current_observation))"`) antes de escrever; se algum nome divergir, adapte o wrapper, nunca o pipeline.

- [ ] **Step 1: Teste (falhando)** — `backend/tests/test_coach_observability.py`:

```python
from contextlib import contextmanager
from types import SimpleNamespace

from chess_trainer.coach.costs import Uso
from chess_trainer.coach.observability import LangfuseTracer, NoopTracer, tracer_de
from chess_trainer.config import AppSettings


class LangfuseFalso:
    def __init__(self):
        self.obs = []
        self.flushed = False

    @contextmanager
    def start_as_current_observation(self, **kw):
        registro = {"kw": kw, "updates": []}
        self.obs.append(registro)
        yield SimpleNamespace(update=lambda **u: registro["updates"].append(u))

    def get_current_trace_id(self):
        return "abc123"

    def flush(self):
        self.flushed = True


def test_tracer_de_sem_configuracao_e_noop():
    assert isinstance(tracer_de(AppSettings()), NoopTracer)
    assert isinstance(tracer_de(AppSettings(langfuse_host="http://x", langfuse_public_key="pk")), NoopTracer)  # sem secret


def test_tracer_de_reaproveita_a_instancia():
    cache = {}
    s = AppSettings(langfuse_host="http://x", langfuse_public_key="pk", langfuse_secret_key="sk")
    a = tracer_de(s, cache, fabrica=lambda pk, sk, host: LangfuseTracer(pk, sk, host, client=LangfuseFalso()))
    b = tracer_de(s, cache, fabrica=lambda pk, sk, host: LangfuseTracer(pk, sk, host, client=LangfuseFalso()))
    assert a is b and isinstance(a, LangfuseTracer)


def test_langfuse_tracer_registra_spans_geracoes_e_url():
    lf = LangfuseFalso()
    t = LangfuseTracer("pk", "sk", "http://localhost:3000", client=lf)
    with t.span("coach.explain", puzzle_id="p1"):
        assert t.trace_id() == "abc123"
        t.geracao("llm", "claude-opus-5", Uso(10, 5, 3, 1), 0.01, chamadas=["analisar_posicao"])
    t.flush()
    assert lf.obs[0]["kw"]["name"] == "coach.explain" and lf.obs[0]["kw"]["as_type"] == "span"
    assert lf.obs[0]["updates"][0]["metadata"] == {"puzzle_id": "p1"}
    g = lf.obs[1]
    assert g["kw"]["as_type"] == "generation" and g["kw"]["name"] == "llm"
    u = g["updates"][-1]
    assert u["model"] == "claude-opus-5" and u["usage_details"]["input"] == 10 and u["cost_details"]["total"] == 0.01
    assert t.url("abc123") == "http://localhost:3000/trace/abc123" and lf.flushed
```

- [ ] **Step 2: Rodar e ver falhar** — `cd backend && uv run pytest tests/test_coach_observability.py -q` → `ImportError`.

- [ ] **Step 3: Implementar** (acrescentar em `observability.py`)

```python
from typing import Any, Callable

from chess_trainer.config import AppSettings


class LangfuseTracer:
    def __init__(self, public_key: str, secret_key: str, host: str, client: Any = None):
        self.host = host.rstrip("/")
        if client is None:
            from langfuse import Langfuse

            client = Langfuse(public_key=public_key, secret_key=secret_key, host=self.host)
        self._lf = client

    @contextmanager
    def span(self, nome: str, **meta):
        with self._lf.start_as_current_observation(as_type="span", name=nome) as obs:
            if meta:
                obs.update(metadata=meta)
            yield

    def geracao(self, nome: str, model: str, uso: Uso, custo: float, **meta) -> None:
        with self._lf.start_as_current_observation(as_type="generation", name=nome) as gen:
            gen.update(model=model, usage_details=uso.to_dict(), cost_details={"total": custo}, metadata=meta)

    def trace_id(self) -> str | None:
        return self._lf.get_current_trace_id()

    def url(self, trace_id: str | None) -> str | None:
        return f"{self.host}/trace/{trace_id}" if trace_id else None

    def flush(self) -> None:
        self._lf.flush()


def tracer_de(settings: AppSettings, cache: dict | None = None,
              fabrica: Callable[[str, str, str], Tracer] | None = None) -> Tracer:
    pk, sk, host = settings.langfuse_public_key, settings.langfuse_secret_key, settings.langfuse_host
    if not (pk and sk and host):
        return NoopTracer()
    chave = (pk, sk, host)
    if cache is not None and chave in cache:
        return cache[chave]
    tracer = (fabrica or LangfuseTracer)(pk, sk, host)
    if cache is not None:
        cache[chave] = tracer
    return tracer
```

Se o SDK instalado usar chaves de `usage_details` diferentes (ex.: `input`, `output`, `cache_read_input_tokens`), mapeie aqui a partir de `Uso.to_dict()`; o pipeline não muda.

- [ ] **Step 4: Rodar e ver passar** — `cd backend && uv run pytest tests/test_coach_observability.py -q` → 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/chess_trainer/coach/observability.py backend/tests/test_coach_observability.py
printf 'feat(treinador): rastreio das etapas no LangFuse\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n' > "$TEMP/msg.txt" && git commit -F "$TEMP/msg.txt"
```

---

### Task 10: API do treinador (`/api/coach/*`) e ligação no app

**Files:**
- Create: `backend/chess_trainer/api/routes/coach.py`
- Modify: `backend/chess_trainer/api/schemas.py` (esquemas do treinador), `backend/chess_trainer/api/app.py` (`coach_llm_factory`, `app.state.coach_lock`, `app.state.coach_tracers`, `include_router`)
- Test: `backend/tests/test_api_coach.py`

**Interfaces:**
- Consumes: `explicar`, `gravar`, `contexto_do_exercicio`, `Indexador`, `AnthropicClient`, `tracer_de`, `theme_stats`, `_get_puzzle`-equivalente local.
- Produces: `create_app(..., coach_llm_factory=None)` onde `coach_llm_factory(settings) -> LlmClient | None` (padrão: `AnthropicClient(settings.anthropic_api_key, settings.coach_model)` se houver chave, senão `None`); rotas de §9: `GET /api/coach/status`, `POST /api/coach/explain`, `GET /api/coach/explanations/{puzzle_id}`, `POST /api/coach/reindex`; esquemas `CoachStatusOut`, `CoachExplainIn`, `IssueOut`, `VerificacaoOut`, `CitacaoOut`, `TokensOut`, `CoachExplanationOut`.
- Mapeamento de erro: `coach_nao_configurado` → 409; `explicacao_em_andamento` → 409; `engine_indisponivel` → 503; demais `ErroDoTreinador` → 502 com `detail = mensagem`; puzzle inexistente → 404.

- [ ] **Step 1: Esquemas** (acrescentar em `schemas.py`)

```python
class CoachStatusOut(BaseModel):
    configured: bool
    model: str
    effort: str
    embeddings_ready: bool
    index_chunks: int
    index_model: str
    index_stale: int
    vector_backend: str
    langfuse_configured: bool


class CoachExplainIn(BaseModel):
    puzzle_id: str
    review_id: str | None = None


class IssueOut(BaseModel):
    tipo: str
    gravidade: str
    detalhe: str
    linha_idx: int | None = None


class VerificacaoOut(BaseModel):
    ok: bool
    issues: list[IssueOut]


class CitacaoOut(BaseModel):
    chunk_id: str
    study_id: str
    estudo: str
    chapter_id: str
    capitulo: str
    node_id: str | None
    caminho_san: str
    texto: str
    url: str


class TokensOut(BaseModel):
    input: int
    output: int
    cache_read: int
    cache_write: int


class CoachExplanationOut(BaseModel):
    id: str
    puzzle_id: str
    created_at: datetime
    model: str
    prompt_version: str
    text: str
    lines: list[dict]
    citations: list[CitacaoOut]
    verification: VerificacaoOut
    status: str
    repaired: bool
    cost_usd: float
    tokens: TokensOut
    duration_ms: int
    trace_url: str | None = None
```

- [ ] **Step 2: Testes (falhando)** — `backend/tests/test_api_coach.py`:

```python
import pytest
from fastapi.testclient import TestClient

from chess_trainer.api.app import create_app
from chess_trainer.coach.llm import ErroDoTreinador
from chess_trainer.config import set_setting
from tests.fakes import EmbeddingsFalso, FakeEngine, FakeLlm, first_legal_default
from tests.test_api_system import chesscom_factory
from tests.test_api_training import engine_factory

TEXTO = " ".join(["explicação"] * 70)
FINAL = {"texto": TEXTO, "linhas": [], "citacoes": [], "padrao": None, "treinar": ["revisar mates simples"]}


def montar(llm):
    app = create_app(db_path=":memory:", engine_factory=engine_factory, chesscom_factory=chesscom_factory,
                     analysis_engine_factory=lambda: FakeEngine(default=first_legal_default(0)),
                     embeddings_factory=EmbeddingsFalso, coach_llm_factory=lambda s: llm if s.anthropic_api_key else None)
    client = TestClient(app)
    client.put("/api/settings", json={"chesscom_username": "therealzibs", "analysis_depth": 4})
    client.post("/api/import"); app.state.jobs.wait()
    client.post("/api/analyze"); app.state.jobs.wait()
    puzzle_id = client.get("/api/queue", params={"mode": "new"}).json()["items"][0]["id"]
    return app, client, puzzle_id


def test_status_e_409_sem_chave():
    app, client, pid = montar(FakeLlm([]))
    st = client.get("/api/coach/status").json()
    assert st["configured"] is False and st["model"] == "claude-opus-5" and st["index_chunks"] == 0 and st["embeddings_ready"] is False
    assert st["vector_backend"] in ("sqlite-vec", "numpy") and st["langfuse_configured"] is False
    r = client.post("/api/coach/explain", json={"puzzle_id": pid})
    assert r.status_code == 409 and "Configurações" in r.json()["detail"]


def test_explain_feliz_reabrir_e_404():
    llm = FakeLlm([[("final", FINAL)]])
    app, client, pid = montar(llm)
    client.put("/api/settings", json={"anthropic_api_key": "sk-ant-x", "coach_effort": "low"})
    assert client.get("/api/coach/status").json()["configured"] is True
    r = client.post("/api/coach/explain", json={"puzzle_id": pid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok" and body["text"] == TEXTO and body["verification"]["ok"] and body["tokens"]["input"] == 1000
    assert body["citations"] == [] and body["trace_url"] is None and body["model"] == "fake" and llm.prompts[0]["effort"] == "low"
    assert client.get(f"/api/coach/explanations/{pid}").json()["id"] == body["id"]
    assert client.get("/api/coach/explanations/nao-existe").status_code == 404
    assert client.post("/api/coach/explain", json={"puzzle_id": "nao-existe"}).status_code == 404


def test_erros_do_treinador_viram_502_ou_503():
    class Quebrado:
        model = "fake"

        def __init__(self, codigo):
            self.codigo = codigo

        def run_agent(self, **kw):
            raise ErroDoTreinador(self.codigo, "mensagem legível")

    for codigo, status in (("limite_de_uso", 502), ("engine_indisponivel", 503), ("recusa", 502)):
        app, client, pid = montar(Quebrado(codigo))
        client.put("/api/settings", json={"anthropic_api_key": "sk-ant-x"})
        r = client.post("/api/coach/explain", json={"puzzle_id": pid})
        assert r.status_code == status and r.json()["detail"] == "mensagem legível", codigo


def test_uma_explicacao_por_vez():
    app, client, pid = montar(FakeLlm([[("final", FINAL)]]))
    client.put("/api/settings", json={"anthropic_api_key": "sk-ant-x"})
    assert app.state.coach_lock.acquire(blocking=False)
    try:
        r = client.post("/api/coach/explain", json={"puzzle_id": pid})
        assert r.status_code == 409 and "andamento" in r.json()["detail"]
    finally:
        app.state.coach_lock.release()


def test_reindex_via_job():
    app, client, pid = montar(FakeLlm([]))
    r = client.post("/api/coach/reindex")
    assert r.status_code == 202 and r.json() == {"queued": True, "job": "coach_reindex"}
    app.state.jobs.wait()
    assert app.state.jobs.snapshot()["state"] == "idle"
    assert client.get("/api/coach/status").json()["embeddings_ready"] is True
```

- [ ] **Step 3: Rodar e ver falhar** — `cd backend && uv run pytest tests/test_api_coach.py -q` → `TypeError: create_app() got an unexpected keyword argument 'coach_llm_factory'`.

- [ ] **Step 4: Implementar `routes/coach.py`**

```python
"""Rotas do treinador com IA (spec §9)."""
from __future__ import annotations

import json
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from chess_trainer.api.deps import get_db
from chess_trainer.api.schemas import CoachExplainIn, CoachExplanationOut, CoachStatusOut
from chess_trainer.coach.explain import OpcoesExplicacao, explicar, gravar
from chess_trainer.coach.llm import ErroDoTreinador
from chess_trainer.coach.observability import tracer_de
from chess_trainer.coach.tools import contexto_do_exercicio
from chess_trainer.config import load_settings
from chess_trainer.core.models import CoachExplanation, Puzzle, utcnow
from chess_trainer.core.stats import theme_stats

router = APIRouter(prefix="/api/coach")

STATUS_POR_CODIGO = {"engine_indisponivel": 503}


def _out(row: CoachExplanation, trace_url: str | None) -> CoachExplanationOut:
    return CoachExplanationOut(
        id=row.id, puzzle_id=row.puzzle_id, created_at=row.created_at, model=row.model, prompt_version=row.prompt_version,
        text=row.text, lines=json.loads(row.lines_json), citations=json.loads(row.citations_json),
        verification=json.loads(row.verification_json), status=row.status, repaired=row.repaired, cost_usd=row.cost_usd,
        tokens={"input": row.input_tokens, "output": row.output_tokens, "cache_read": row.cache_read_tokens, "cache_write": row.cache_write_tokens},
        duration_ms=row.duration_ms, trace_url=trace_url,
    )


@router.get("/status", response_model=CoachStatusOut)
def coach_status(request: Request, db: Session = Depends(get_db)):
    s = load_settings(db)
    idx = request.app.state.coach_index.status(db)
    return CoachStatusOut(configured=bool(s.anthropic_api_key), model=s.coach_model, effort=s.coach_effort,
                          langfuse_configured=bool(s.langfuse_host and s.langfuse_public_key and s.langfuse_secret_key), **idx)


@router.post("/explain", response_model=CoachExplanationOut)
def coach_explain(body: CoachExplainIn, request: Request, db: Session = Depends(get_db)):
    app = request.app
    settings = load_settings(db)
    llm = app.state.coach_llm_factory(settings)
    if llm is None:
        raise HTTPException(409, "o treinador não está configurado: informe a chave da API em Configurações")
    puzzle = db.get(Puzzle, body.puzzle_id)
    if puzzle is None:
        raise HTTPException(404, "puzzle não encontrado")
    if not app.state.coach_lock.acquire(blocking=False):
        raise HTTPException(409, "já há uma explicação em andamento; espere ela terminar")
    try:
        contexto = contexto_do_exercicio(db, puzzle)
        caminho = contexto.partida["lances_em_volta"] if contexto.partida else None
        index = app.state.coach_index
        tracer = tracer_de(settings, app.state.coach_tracers)
        resultado = explicar(
            contexto=contexto, llm=llm, analisar=app.state.analyzer.analyse,
            estatisticas=lambda dias: theme_stats(db, utcnow() - timedelta(days=dias)),
            buscar=lambda consulta, k: index.buscar(db, consulta, k, caminho_san=caminho),
            opcoes=OpcoesExplicacao(effort=settings.coach_effort), tracer=tracer,
        )
    except ErroDoTreinador as exc:
        raise HTTPException(STATUS_POR_CODIGO.get(exc.codigo, 502), exc.mensagem) from exc
    finally:
        app.state.coach_lock.release()
    row = gravar(db, resultado, body.review_id)
    return _out(row, tracer.url(row.trace_id))


@router.get("/explanations/{puzzle_id}", response_model=CoachExplanationOut)
def coach_explanation(puzzle_id: str, request: Request, db: Session = Depends(get_db)):
    row = db.scalar(select(CoachExplanation).where(CoachExplanation.puzzle_id == puzzle_id)
                    .order_by(CoachExplanation.created_at.desc()))
    if row is None:
        raise HTTPException(404, "sem explicação para este exercício")
    tracer = tracer_de(load_settings(db), request.app.state.coach_tracers)
    return _out(row, tracer.url(row.trace_id))


@router.post("/reindex", status_code=202)
def coach_reindex(request: Request):
    app = request.app

    def job(progress):
        db = app.state.session_factory()
        try:
            app.state.coach_index.recriar(db, progress)
        finally:
            db.close()

    if not app.state.jobs.submit("coach_reindex", job):
        raise HTTPException(409, "já existe uma tarefa em andamento")
    return {"queued": True, "job": "coach_reindex"}
```

Em `app.py`: parâmetro `coach_llm_factory=None`; depois de `app.state.coach_index = ...`:

```python
    def _default_llm_factory(settings: AppSettings):
        if not settings.anthropic_api_key:
            return None
        return AnthropicClient(settings.anthropic_api_key, settings.coach_model)

    app.state.coach_llm_factory = coach_llm_factory or _default_llm_factory
    app.state.coach_lock = threading.Lock()   # uma explicação por vez: a engine interativa é compartilhada
    app.state.coach_tracers = {}              # instâncias do LangFuse por (chaves, host)
```

e `app.include_router(coach.router)` junto dos outros (importe `coach` de `chess_trainer.api.routes` e `AnthropicClient` de `chess_trainer.coach.llm`; `import threading`).

- [ ] **Step 5: Rodar e ver passar** — `cd backend && uv run pytest tests/test_api_coach.py -q` → 5 passed; depois `uv run pytest -q` inteiro.

- [ ] **Step 6: Commit**

```bash
git add backend/chess_trainer/api/routes/coach.py backend/chess_trainer/api/schemas.py backend/chess_trainer/api/app.py backend/tests/test_api_coach.py
printf 'feat(treinador): rotas de estado, explicação, releitura e recriação do índice\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n' > "$TEMP/msg.txt" && git commit -F "$TEMP/msg.txt"
```

---

### Task 11: Frontend — cartão "Treinador" na tela de resultado

**Files:**
- Modify: `frontend/src/api/types.ts`, `frontend/src/api/client.ts`, `frontend/src/api/queries.ts`, `frontend/src/train/ResultPanel.tsx`, `frontend/tests/resultPanel.test.tsx` (mock do status)
- Create: `frontend/src/train/CoachCard.tsx`
- Test: `frontend/tests/coachCard.test.tsx`

**Interfaces:**
- Produces (types): `CoachStatus { configured; model; effort; embeddings_ready; index_chunks; index_model; index_stale; vector_backend; langfuse_configured }`, `Citacao { chunk_id; study_id; estudo; chapter_id; capitulo; node_id: string | null; caminho_san; texto; url }`, `IssueOut { tipo; gravidade: "erro" | "aviso"; detalhe; linha_idx: number | null }`, `CoachExplanation { id; puzzle_id; created_at; model; prompt_version; text; lines: unknown[]; citations: Citacao[]; verification: { ok: boolean; issues: IssueOut[] }; status: "ok" | "warnings" | "errors"; repaired; cost_usd; tokens: { input; output; cache_read; cache_write }; duration_ms; trace_url: string | null }`.
- Produces (client): `api.coachStatus()`, `api.coachExplain({ puzzle_id, review_id? })`, `api.coachExplanation(puzzleId) -> CoachExplanation | null` (404 vira `null`), `api.coachReindex()`.
- Produces (queries): `keys.coachStatus`, `keys.coachExplanation(id)`, `useCoachStatus()`, `useCoachExplanation(puzzleId, enabled)`, `useExplain()` (mutation; no sucesso grava em `keys.coachExplanation(puzzle_id)`); `useStartJob` aceita `kind: "coach_reindex"`.
- Componente `CoachCard({ puzzle, reviewId })`: `null` quando o treinador não está configurado; botão **Explicar**; estados carregando / erro / pronto; "Explicar de novo" quando já existe; texto com lances clicáveis via `TextoComLances` (prévia do `PreviaContext`), marcadores `[c:ID]` viram links numerados para `citation.url`; selo por `verification`; rodapé com modelo, custo, tempo e link do trace.

- [ ] **Step 1: Tipos, cliente e queries**

`types.ts` (acrescentar as interfaces acima). `client.ts`:

```ts
  coachStatus: () => request<CoachStatus>("/coach/status"),
  coachExplain: (body: { puzzle_id: string; review_id?: string }) => request<CoachExplanation>("/coach/explain", post(body)),
  coachExplanation: async (puzzleId: string): Promise<CoachExplanation | null> => {
    try {
      return await request<CoachExplanation>(`/coach/explanations/${puzzleId}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }
  },
  coachReindex: () => request<JobQueued>("/coach/reindex", post()),
```

`queries.ts`:

```ts
  coachStatus: ["coach", "status"] as const,
  coachExplanation: (id: string) => ["coach", "explanation", id] as const,
// ...
export const useCoachStatus = () => useQuery({ queryKey: keys.coachStatus, queryFn: api.coachStatus, staleTime: 30_000 });
export const useCoachExplanation = (puzzleId: string, enabled: boolean) =>
  useQuery({ queryKey: keys.coachExplanation(puzzleId), queryFn: () => api.coachExplanation(puzzleId), enabled });
export function useExplain() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { puzzle_id: string; review_id?: string }) => api.coachExplain(body),
    onSuccess: (exp) => qc.setQueryData(keys.coachExplanation(exp.puzzle_id), exp),
  });
}
```

Em `useStartJob`, acrescente `"coach_reindex"` ao `kind` e o ramo `: p.kind === "coach_reindex" ? api.coachReindex()`; em `JobCard.tsx`, acrescente `coach_reindex: "Recriação do índice dos estudos"`, a descrição `"baixa o modelo de embeddings na primeira vez (~250 MB) e indexa os comentários dos capítulos"` e o par de rótulos de cancelamento como nos outros jobs. Rode `npm run build` para o tipo fechar.

- [ ] **Step 2: Teste do cartão (falhando)** — `frontend/tests/coachCard.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { CoachExplanation, CoachStatus, PuzzleOut } from "../src/api/types";
import { api } from "../src/api/client";
import { ApiError } from "../src/api/client";
import { CoachCard } from "../src/train/CoachCard";
import { PreviaContext } from "../src/analysis/previaContext";

const FEN = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4";
const puzzle: PuzzleOut = {
  id: "p1", kind: "punish", fen_start: FEN, side_to_move: "white",
  solution: { moves: [{ uci: "h5f7", by: "solver", alternatives: [] }], explanation_pv: [] },
  end_reason: "mate", theme: "mate_in_1", category: "rapid", solver_moves: 1, is_leech: false,
  srs: { ease: 2.5, interval_days: 0, lapses: 0, due_at: null, last_reviewed_at: null },
  source: "own", in_queue: true, fen_before: null, last_move: null, game: null, ply: null, move_played: null, mistake: null, study: null, siblings: [],
};
const status = (over: Partial<CoachStatus> = {}): CoachStatus => ({
  configured: true, model: "claude-opus-5", effort: "high", embeddings_ready: true, index_chunks: 3, index_model: "m",
  index_stale: 0, vector_backend: "sqlite-vec", langfuse_configured: false, ...over,
});
const explicacao = (over: Partial<CoachExplanation> = {}): CoachExplanation => ({
  id: "e1", puzzle_id: "p1", created_at: "2026-09-11T10:00:00", model: "claude-opus-5", prompt_version: "v1",
  text: "A dama e o bispo miram f7: Qxf7# encerra. [c:ab12] Treine mates rápidos.",
  lines: [], citations: [{ chunk_id: "ab12", study_id: "s1", estudo: "Táticas", chapter_id: "c1", capitulo: "Mates", node_id: "n1", caminho_san: "1.e4", texto: "t", url: "/estudos/s1/capitulos/c1?lance=n1" }],
  verification: { ok: true, issues: [] }, status: "ok", repaired: false, cost_usd: 0.0421,
  tokens: { input: 5000, output: 400, cache_read: 3000, cache_write: 0 }, duration_ms: 12000, trace_url: "http://localhost:3000/trace/x", ...over,
});

function renderCard(previa = vi.fn()) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <MemoryRouter>
        <PreviaContext.Provider value={previa}><CoachCard puzzle={puzzle} reviewId="r1" /></PreviaContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return previa;
}

beforeEach(() => {
  vi.spyOn(api, "coachStatus").mockResolvedValue(status());
  vi.spyOn(api, "coachExplanation").mockResolvedValue(null);
  vi.spyOn(api, "coachExplain").mockResolvedValue(explicacao());
});
afterEach(() => vi.restoreAllMocks());

test("sem treinador configurado o cartão não aparece", async () => {
  vi.spyOn(api, "coachStatus").mockResolvedValue(status({ configured: false }));
  renderCard();
  await waitFor(() => expect(api.coachStatus).toHaveBeenCalled());
  expect(screen.queryByRole("button", { name: "Explicar" })).toBeNull();
});

test("Explicar chama a API com o exercício e mostra o texto com lance clicável, citação e selo", async () => {
  const previa = renderCard();
  fireEvent.click(await screen.findByRole("button", { name: "Explicar" }));
  expect(await screen.findByText(/leva de 10 a 40 s/)).toBeTruthy();
  await waitFor(() => expect(api.coachExplain).toHaveBeenCalledWith({ puzzle_id: "p1", review_id: "r1" }));
  expect(await screen.findByText(/A dama e o bispo miram f7/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Qxf7#" }));
  expect(previa).toHaveBeenCalled();
  const link = screen.getByRole("link", { name: /Táticas › Mates/ });
  expect(link.getAttribute("href")).toBe("/estudos/s1/capitulos/c1?lance=n1");
  expect(screen.queryByText("[c:ab12]")).toBeNull();
  expect(screen.getByText("verificado pela engine")).toBeTruthy();
  expect(screen.getByText(/claude-opus-5 · US\$ 0,04 · 12 s/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "trace" }).getAttribute("href")).toBe("http://localhost:3000/trace/x");
  expect(screen.getByRole("button", { name: "Explicar de novo" })).toBeTruthy();
});

test("explicação já existente abre direto", async () => {
  vi.spyOn(api, "coachExplanation").mockResolvedValue(explicacao({ status: "warnings", verification: { ok: true, issues: [{ tipo: "lance_fora_das_principais", gravidade: "aviso", detalhe: "'a3' não está entre as três melhores", linha_idx: 0 }] } }));
  renderCard();
  expect(await screen.findByText(/A dama e o bispo/)).toBeTruthy();
  expect(screen.getByText("com ressalvas")).toBeTruthy();
  expect(screen.getByText(/'a3' não está entre as três melhores/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Explicar de novo" })).toBeTruthy();
});

test("erro da API aparece e o botão volta", async () => {
  vi.spyOn(api, "coachExplain").mockRejectedValue(new ApiError(502, "limite de uso da API atingido"));
  renderCard();
  fireEvent.click(await screen.findByRole("button", { name: "Explicar" }));
  expect(await screen.findByText(/limite de uso da API atingido/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Explicar" })).toBeTruthy();
});

test("status errors mostra 'não verificado' com os erros", async () => {
  vi.spyOn(api, "coachExplanation").mockResolvedValue(explicacao({ status: "errors", verification: { ok: false, issues: [{ tipo: "lance_ilegal", gravidade: "erro", detalhe: "'Qxf8' não é legal", linha_idx: 0 }] } }));
  renderCard();
  expect(await screen.findByText("não verificado")).toBeTruthy();
  expect(screen.getByText(/'Qxf8' não é legal/)).toBeTruthy();
});
```

- [ ] **Step 3: Rodar e ver falhar** — `cd frontend && npx vitest run tests/coachCard.test.tsx` → falha na importação.

- [ ] **Step 4: Implementar `CoachCard.tsx`**

```tsx
import { Fragment, useContext } from "react";
import { Link } from "react-router-dom";
import type { CoachExplanation, PuzzleOut } from "../api/types";
import { useCoachExplanation, useCoachStatus, useExplain } from "../api/queries";
import { PreviaContext } from "../analysis/previaContext";
import { TextoComLances } from "../analysis/TextoComLances";
import { ErrorBox } from "../components/ErrorBox";

const CITACAO = /\[c:([^\]\s]+)\]/g;

/** Quebra o texto em prosa e marcadores de citação, na ordem. */
export function segmentarCitacoes(texto: string): ({ kind: "texto"; text: string } | { kind: "citacao"; id: string })[] {
  const out: ({ kind: "texto"; text: string } | { kind: "citacao"; id: string })[] = [];
  let ultimo = 0;
  for (const m of texto.matchAll(CITACAO)) {
    const i = m.index ?? 0;
    if (i > ultimo) out.push({ kind: "texto", text: texto.slice(ultimo, i) });
    out.push({ kind: "citacao", id: m[1] });
    ultimo = i + m[0].length;
  }
  if (ultimo < texto.length) out.push({ kind: "texto", text: texto.slice(ultimo) });
  return out;
}

function Selo({ exp }: { exp: CoachExplanation }) {
  const { issues } = exp.verification;
  const rotulo = exp.status === "ok" ? "verificado pela engine" : exp.status === "warnings" ? "com ressalvas" : "não verificado";
  const classe = exp.status === "ok" ? "ok" : exp.status === "warnings" ? "warn" : "bad";
  return (
    <div>
      <span className={`msg ${classe}`}>{rotulo}</span>
      {issues.length > 0 && (
        <ul className="muted" style={{ margin: "6px 0 0 18px", padding: 0 }}>
          {issues.map((i, n) => <li key={n}>{i.detalhe}</li>)}
        </ul>
      )}
    </div>
  );
}

const usd = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/**
 * Cartão "Treinador": pede a explicação do erro ao backend e a mostra com os lances
 * clicáveis (prévia no tabuleiro grande), as citações dos estudos como links e o
 * selo do verificador. Sem chave da API configurada, não aparece.
 */
export function CoachCard({ puzzle, reviewId }: { puzzle: PuzzleOut; reviewId?: string }) {
  const { data: status } = useCoachStatus();
  const configurado = !!status?.configured;
  const { data: existente } = useCoachExplanation(puzzle.id, configurado);
  const explicar = useExplain();
  const previa = useContext(PreviaContext);
  if (!configurado) return null;
  const exp = explicar.data ?? existente ?? null;
  const pedir = () => explicar.mutate({ puzzle_id: puzzle.id, review_id: reviewId });
  const porId = new Map((exp?.citations ?? []).map((c, i) => [c.chunk_id, { ...c, n: i + 1 }]));
  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>Treinador</h3>
        {!explicar.isPending && (
          <button className={exp ? undefined : "primary"} onClick={pedir}>{exp ? "Explicar de novo" : "Explicar"}</button>
        )}
      </div>
      {status && status.index_chunks === 0 && (
        <div className="muted">Sem estudos indexados: a explicação não vai citar estudos (Configurações → Recriar índice).</div>
      )}
      {explicar.isPending && <p className="muted">Pensando… leva de 10 a 40 s.</p>}
      {!!explicar.error && <ErrorBox error={explicar.error} />}
      {exp && !explicar.isPending && (
        <>
          <Selo exp={exp} />
          <p style={{ whiteSpace: "pre-wrap" }}>
            {segmentarCitacoes(exp.text).map((s, i) =>
              s.kind === "texto" ? (
                <TextoComLances key={i} texto={s.text} fen={puzzle.fen_start} onPrevia={previa ?? (() => undefined)} />
              ) : (
                <Fragment key={i}>
                  {porId.has(s.id)
                    ? <Link to={porId.get(s.id)!.url} className="citacao" title={porId.get(s.id)!.caminho_san}>[{porId.get(s.id)!.estudo} › {porId.get(s.id)!.capitulo}]</Link>
                    : null}
                </Fragment>
              ),
            )}
          </p>
          <div className="muted">
            {exp.model} · US$ {usd.format(exp.cost_usd)} · {Math.round(exp.duration_ms / 1000)} s
            {exp.repaired ? " · corrigida uma vez" : ""}
            {exp.trace_url && <> · <a href={exp.trace_url} target="_blank" rel="noopener noreferrer">trace</a></>}
          </div>
        </>
      )}
    </div>
  );
}
```

Em `ResultPanel.tsx`, depois de `{comErro && <MistakeCard puzzle={comErro} />}`: `<CoachCard puzzle={puzzle} reviewId={review?.id} />` (import de `./CoachCard`). Em `tests/resultPanel.test.tsx`, no `beforeEach`: `vi.spyOn(api, "coachStatus").mockResolvedValue({ configured: false, model: "", effort: "high", embeddings_ready: false, index_chunks: 0, index_model: "", index_stale: 0, vector_backend: "numpy", langfuse_configured: false });`. Acrescente `.msg.warn` e `.citacao` ao CSS global (`src/styles`) seguindo as cores dos temas claro e escuro já definidas para `.msg.ok`/`.msg.bad`.

- [ ] **Step 5: Rodar e ver passar** — `cd frontend && npx vitest run tests/coachCard.test.tsx tests/resultPanel.test.tsx` → verde; depois `npm test` e `npm run build`.

Se o teste do custo (`US$ 0,04`) falhar pelo espaço não separável do `Intl`, compare com uma regex tolerante `/US\$\s?0,04/` no teste.

- [ ] **Step 6: Commit**

```bash
git add frontend/src frontend/tests/coachCard.test.tsx frontend/tests/resultPanel.test.tsx
printf 'feat(treinador): cartão "Treinador" na tela de resultado com lances clicáveis, citações e selo\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n' > "$TEMP/msg.txt" && git commit -F "$TEMP/msg.txt"
```

---

### Task 12: Frontend — seção "Treinador (IA)" em Configurações

**Files:**
- Modify: `frontend/src/api/types.ts` (`Settings`, `SettingsIn`), `frontend/src/pages/SettingsPage.tsx`, `frontend/tests/settings.test.ts` (fixture), `frontend/tests/settingsPage.test.tsx`

**Interfaces:**
- `Settings` ganha `anthropic_api_key_set: boolean; coach_model: "claude-opus-5" | "claude-sonnet-5"; coach_effort: "low" | "medium" | "high"; langfuse_public_key: string; langfuse_secret_key_set: boolean; langfuse_host: string`; `SettingsIn` ganha os mesmos como opcionais mais `anthropic_api_key?: string` e `langfuse_secret_key?: string`.
- Rascunhos separados para os dois segredos (`apiKeyDraft`, `lfSecretDraft`), no mesmo padrão do token: vazio não é enviado; "Remover" manda `""`.

- [ ] **Step 1: Testes (falhando)** — em `tests/settings.test.ts`, acrescente ao objeto `ok`: `anthropic_api_key_set: false, coach_model: "claude-opus-5" as const, coach_effort: "high" as const, langfuse_public_key: "", langfuse_secret_key_set: false, langfuse_host: ""`. Em `tests/settingsPage.test.tsx`, o mesmo no `SETTINGS`, `vi.spyOn(api, "coachStatus").mockResolvedValue({...})` no `beforeEach` (configured false, embeddings_ready false, index_chunks 0, index_stale 2, vector_backend "sqlite-vec", ...) e `vi.spyOn(api, "coachReindex").mockResolvedValue({ queued: true, job: "coach_reindex" })`, e os testes:

```tsx
test("a seção do treinador tem chave em campo de senha, modelo, esforço e LangFuse", async () => {
  renderPage();
  const chave = (await screen.findByLabelText("Chave da API da Anthropic")) as HTMLInputElement;
  expect(chave.type).toBe("password");
  expect(chave.placeholder).toBe("cole a chave aqui");
  expect((screen.getByLabelText("Modelo") as HTMLSelectElement).value).toBe("claude-opus-5");
  expect((screen.getByLabelText("Esforço") as HTMLSelectElement).value).toBe("high");
  expect((screen.getByLabelText("Chave secreta do LangFuse") as HTMLInputElement).type).toBe("password");
  expect(screen.getByText(/modelo de embeddings ainda não baixado/)).toBeTruthy();
  expect(screen.getByText(/2 capítulos desatualizados/)).toBeTruthy();
});

test("salvar manda a chave só quando digitada e nunca os campos _set", async () => {
  vi.spyOn(api, "settings").mockResolvedValue({ ...SETTINGS, anthropic_api_key_set: true });
  renderPage();
  expect((await screen.findByLabelText("Chave da API da Anthropic")).getAttribute("placeholder")).toBe("guardada; digite para trocar");
  fireEvent.change(screen.getByLabelText("Modelo"), { target: { value: "claude-sonnet-5" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(api.saveSettings).toHaveBeenCalled());
  const body = vi.mocked(api.saveSettings).mock.calls[0][0];
  expect(body.coach_model).toBe("claude-sonnet-5");
  expect("anthropic_api_key" in body).toBe(false);
  expect("anthropic_api_key_set" in body).toBe(false);
  expect("langfuse_secret_key_set" in body).toBe(false);
});

test("a chave digitada vai no PUT e o campo esvazia; Remover manda vazio", async () => {
  vi.spyOn(api, "settings").mockResolvedValue({ ...SETTINGS, anthropic_api_key_set: true });
  renderPage();
  const campo = await screen.findByLabelText("Chave da API da Anthropic");
  fireEvent.change(campo, { target: { value: "sk-ant-nova" } });
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(vi.mocked(api.saveSettings).mock.calls[0][0].anthropic_api_key).toBe("sk-ant-nova"));
  await waitFor(() => expect((campo as HTMLInputElement).value).toBe(""));
  fireEvent.click(screen.getByRole("button", { name: "Remover chave" }));
  await waitFor(() => expect(vi.mocked(api.saveSettings).mock.calls.at(-1)![0]).toEqual({ anthropic_api_key: "" }));
});

test("Recriar índice dispara o job", async () => {
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: "Recriar índice" }));
  await waitFor(() => expect(api.coachReindex).toHaveBeenCalled());
});
```

- [ ] **Step 2: Rodar e ver falhar** — `cd frontend && npx vitest run tests/settingsPage.test.tsx tests/settings.test.ts` → falha (tipos e elementos ausentes).

- [ ] **Step 3: Implementar** — em `SettingsPage.tsx`:

- Estados: `const [apiKeyDraft, setApiKeyDraft] = useState(""); const [lfSecretDraft, setLfSecretDraft] = useState("");` e `const { data: coach } = useCoachStatus();`.
- O botão **Salvar** passa a montar o corpo tirando todos os `_set`:

```tsx
const { lichess_token_set: _a, anthropic_api_key_set: _b, langfuse_secret_key_set: _c, ...corpo } = form;
const body: SettingsIn = { ...corpo };
if (tokenDraft.trim()) body.lichess_token = tokenDraft.trim();
if (apiKeyDraft.trim()) body.anthropic_api_key = apiKeyDraft.trim();
if (lfSecretDraft.trim()) body.langfuse_secret_key = lfSecretDraft.trim();
salvar(body);
```

e o `onSuccess` de `salvar` também zera `apiKeyDraft` e `lfSecretDraft`.

- Nova seção, antes do bloco do botão Salvar:

```tsx
<div className="card">
  <h3 style={{ marginTop: 0 }}>Treinador (IA)</h3>
  <label className="row" style={{ justifyContent: "space-between" }}>
    Chave da API da Anthropic
    <input type="password" autoComplete="off" value={apiKeyDraft} onChange={(e) => setApiKeyDraft(e.target.value)}
      placeholder={form.anthropic_api_key_set ? "guardada; digite para trocar" : "cole a chave aqui"} style={{ flex: 1 }} />
  </label>
  <div className="muted">
    Crie a chave no Console da Anthropic e defina lá um teto de gasto mensal. Cada explicação custa alguns centavos de dólar. Fica só no seu banco.
  </div>
  {form.anthropic_api_key_set && (
    <div className="row" style={{ marginTop: 8 }}>
      <span className="msg ok">chave configurada</span>
      <button onClick={() => salvar({ anthropic_api_key: "" }, { soToken: true })} disabled={save.isPending}>Remover chave</button>
    </div>
  )}
  <label className="row" style={{ justifyContent: "space-between" }}>
    Modelo
    <select aria-label="Modelo" value={form.coach_model} onChange={(e) => setForm({ ...form, coach_model: e.target.value as Settings["coach_model"] })}>
      <option value="claude-opus-5">Claude Opus 5 (melhor raciocínio)</option>
      <option value="claude-sonnet-5">Claude Sonnet 5 (mais barato)</option>
    </select>
  </label>
  <label className="row" style={{ justifyContent: "space-between" }}>
    Esforço
    <select aria-label="Esforço" value={form.coach_effort} onChange={(e) => setForm({ ...form, coach_effort: e.target.value as Settings["coach_effort"] })}>
      <option value="low">baixo</option><option value="medium">médio</option><option value="high">alto</option>
    </select>
  </label>
  <h4>Busca nos estudos</h4>
  <div className="muted">
    {coach?.embeddings_ready
      ? `${nf.format(coach.index_chunks)} trechos indexados (${coach.index_model}, ${coach.vector_backend})`
      : "modelo de embeddings ainda não baixado: o primeiro Recriar índice baixa cerca de 250 MB"}
    {coach && coach.index_stale > 0 ? ` · ${coach.index_stale} capítulos desatualizados` : ""}
  </div>
  <button onClick={() => start.mutate({ kind: "coach_reindex" })} disabled={status?.job.state === "running"}>Recriar índice</button>
  <h4>LangFuse (observabilidade)</h4>
  <label className="row" style={{ justifyContent: "space-between" }}>Host<input value={form.langfuse_host} placeholder="http://localhost:3000" onChange={(e) => setForm({ ...form, langfuse_host: e.target.value })} style={{ flex: 1 }} /></label>
  <label className="row" style={{ justifyContent: "space-between" }}>Chave pública do LangFuse<input value={form.langfuse_public_key} onChange={(e) => setForm({ ...form, langfuse_public_key: e.target.value })} style={{ flex: 1 }} /></label>
  <label className="row" style={{ justifyContent: "space-between" }}>
    Chave secreta do LangFuse
    <input type="password" autoComplete="off" value={lfSecretDraft} onChange={(e) => setLfSecretDraft(e.target.value)}
      placeholder={form.langfuse_secret_key_set ? "guardada; digite para trocar" : "cole a chave aqui"} style={{ flex: 1 }} />
  </label>
  <div className="muted">Opcional. Com o Docker Compose do projeto, o LangFuse roda em http://localhost:3000; crie um projeto lá e cole as chaves.</div>
</div>
```

Renomeie a opção `soToken` de `salvar` para `soSegredo` e, no `onSuccess`, com `soSegredo` mescle no formulário os três campos de estado: `{ ...f, lichess_token_set: s.lichess_token_set, anthropic_api_key_set: s.anthropic_api_key_set, langfuse_secret_key_set: s.langfuse_secret_key_set }` (atualize os usos existentes de `soToken`).

- [ ] **Step 4: Rodar e ver passar** — `cd frontend && npm test && npm run build`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src frontend/tests/settings.test.ts frontend/tests/settingsPage.test.tsx
printf 'feat(treinador): seção "Treinador (IA)" em Configurações\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n' > "$TEMP/msg.txt" && git commit -F "$TEMP/msg.txt"
```

---

### Task 13: Avaliação offline (`backend/evals/coach/`)

**Files:**
- Create: `backend/evals/__init__.py`, `backend/evals/coach/__init__.py`, `backend/evals/coach/dataset.py`, `backend/evals/coach/run.py`, `backend/evals/coach/metrics.py`, `backend/evals/coach/judge.py`, `backend/evals/coach/report.py`
- Modify: `.gitignore` (`backend/evals/coach/runs/`), `backend/pyproject.toml` (marker `network`)
- Test: `backend/tests/test_coach_eval.py`

**Interfaces:**
- Consumes: `ContextoExercicio`, `explicar`, `OpcoesExplicacao`, `AnthropicClient`, `to_tactic`, `THEME_LABELS`, `verify`.
- Produces: `dataset.ItemAvaliacao` (dataclass: `id, origem ("own"|"lichess"), contexto: dict, rating: int | None, gabarito: dict`), `dataset.contexto_de_item(item) -> ContextoExercicio`, `dataset.montar(db, analisar, n_lichess=120, seed=7) -> list[ItemAvaliacao]`, `dataset.salvar(items, path)`, `dataset.carregar(path) -> list[ItemAvaliacao]`, `dataset.TEMAS_GENERICOS`; `run.rodar(items, llm, analisar, buscar, opcoes, juiz=None) -> list[dict]` (uma linha por item: `id, origem, status, ok, erros, avisos, issues, repaired, custo_usd, duration_ms, tokens, n_chamadas_api, texto, estruturado, nota, justificativa`), `run.main(argv)`; `metrics.resumir(linhas) -> dict`, `metrics.spearman(a, b) -> float`; `judge.julgar(llm, contexto_texto, explicacao) -> dict(nota: int, justificativa: str)`, `judge.RUBRICA`; `report.escrever_relatorio(resumos: list[dict], path, meta: dict) -> str`.
- **O conjunto `dataset/v1.json` é gerado pelo usuário** contra o banco real (`uv run python -m evals.coach.dataset`); o agente só escreve e testa o código com bancos em memória. As rodadas gravam em `backend/evals/coach/runs/` (ignorado pelo git: os textos podem citar trechos de estudos).

- [ ] **Step 1: Testes (falhando)** — `backend/tests/test_coach_eval.py`:

```python
import json

import chess

from evals.coach import dataset, judge, metrics, report, run
from chess_trainer.coach.explain import OpcoesExplicacao
from chess_trainer.core.evals import MATE_SCORE
from chess_trainer.core.models import LichessPuzzle, LichessPuzzleTheme
from tests.fakes import FakeLlm
from tests.test_coach_explain import BOA, TEXTO, analisar
from tests.test_coach_tools import puzzle_punir


def lichess(db, id_, fen, moves, rating, temas):
    db.add(LichessPuzzle(id=id_, fen=fen, moves=moves, rating=rating, rating_deviation=50, popularity=95, nb_plays=5000, themes=" ".join(temas)))
    for t in temas:
        db.add(LichessPuzzleTheme(theme=t, puzzle_id=id_))


def test_montar_salvar_e_carregar(db_session, tmp_path):
    puzzle_punir(db_session)
    # dois puzzles sintéticos do Lichess: mate do pastor de cada lado (o FEN é antes do lance do adversário)
    lichess(db_session, "L1", "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3", "g8f6 h5f7", 1100, ["mateIn1", "short", "mate"])
    lichess(db_session, "L2", "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3", "g8f6 h5f7", 1700, ["mateIn1", "short", "mate"])
    db_session.commit()
    items = dataset.montar(db_session, analisar, n_lichess=2, seed=1)
    assert [i.origem for i in items] == ["own", "lichess", "lichess"]
    proprio = items[0]
    assert proprio.contexto["tipo"] == "punir" and proprio.gabarito["inicial"]["lines"][0]["san"] == "Qxf7#"
    tatico = items[1]
    ctx = dataset.contexto_de_item(tatico)
    assert ctx.tipo == "lichess" and ctx.solucao_san == ["Qxf7#"] and ctx.tema in ("mate em 1", "mate") and tatico.rating in (1100, 1700)
    assert "g8f6" in ctx.lances_permitidos and "h5f7" in ctx.lances_permitidos
    caminho = tmp_path / "v1.json"
    dataset.salvar(items, caminho)
    de_volta = dataset.carregar(caminho)
    assert [i.id for i in de_volta] == [i.id for i in items] and de_volta[1].gabarito == items[1].gabarito
    assert "short" in dataset.TEMAS_GENERICOS


def test_rodar_resumir_e_relatorio(db_session, tmp_path):
    puzzle_punir(db_session)
    items = dataset.montar(db_session, analisar, n_lichess=0, seed=1)
    ruim = {**BOA, "linhas": [{"inicio": "inicial", "lances": ["Qxf8"], "avaliacao_cp": None, "mate_em": None}], "citacoes": [], "texto": TEXTO}
    llm = FakeLlm([[("final", ruim)], [("final", ruim)]])
    juiz = FakeLlm([[("final", {"nota": 4, "justificativa": "clara"})]])
    linhas = run.rodar(items, llm, analisar, buscar=None, opcoes=OpcoesExplicacao(variante="agente"), juiz=juiz)
    assert len(linhas) == 1 and linhas[0]["status"] == "errors" and linhas[0]["nota"] == 4 and linhas[0]["erros"] == 1
    r = metrics.resumir(linhas)
    assert r["n"] == 1 and r["taxa_erros"] == 1.0 and r["por_tipo"]["lance_ilegal"] == 100.0 and r["nota_media"] == 4.0
    assert r["custo_total_usd"] == 0.0 and r["latencia_p50_ms"] >= 0
    md = report.escrever_relatorio([{"variante": "agente", "modelo": "fake", **r}], tmp_path / "rel.md",
                                   {"dataset": "v1", "prompt_version": "v1", "data": "2026-09-11"})
    assert "| agente | fake |" in md and (tmp_path / "rel.md").read_text(encoding="utf-8").startswith("# Avaliação do treinador")


def test_spearman_e_julgar():
    assert metrics.spearman([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0
    assert metrics.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    juiz = FakeLlm([[("final", {"nota": 2, "justificativa": "vaga"})]])
    nota = judge.julgar(juiz, "contexto", "explicação")
    assert nota == {"nota": 2, "justificativa": "vaga"} and "1 a 5" in judge.RUBRICA and juiz.prompts[0]["ferramentas"] == []


def test_main_le_o_dataset_e_escreve_a_rodada(db_session, tmp_path, monkeypatch):
    puzzle_punir(db_session)
    items = dataset.montar(db_session, analisar, n_lichess=0, seed=1)
    dataset.salvar(items, tmp_path / "v1.json")
    monkeypatch.setattr(run, "_llm", lambda modelo: FakeLlm([[("final", {**BOA, "citacoes": [], "texto": TEXTO + " Qxf7#"})]]))
    monkeypatch.setattr(run, "_analisar", lambda: analisar)
    monkeypatch.setattr(run, "_buscar", lambda: None)
    run.main(["--dataset", str(tmp_path / "v1.json"), "--variante", "agente", "--modelo", "opus", "--saida", str(tmp_path / "runs"), "--sem-juiz"])
    arquivos = list((tmp_path / "runs").glob("*.jsonl"))
    assert len(arquivos) == 1 and json.loads(arquivos[0].read_text(encoding="utf-8").splitlines()[0])["status"] == "ok"
    resumo = json.loads(arquivos[0].with_suffix(".resumo.json").read_text(encoding="utf-8"))
    assert resumo["variante"] == "agente" and resumo["modelo"] == "claude-opus-5" and resumo["n"] == 1
```

- [ ] **Step 2: Rodar e ver falhar** — `cd backend && uv run pytest tests/test_coach_eval.py -q` → `ModuleNotFoundError: evals`. Crie `backend/evals/__init__.py` e `backend/evals/coach/__init__.py` vazios (o `rootdir` do pytest é `backend`, então `evals` importa).

- [ ] **Step 3: Implementar `dataset.py`**

```python
"""Conjunto de avaliação do treinador (spec §8.1): os puzzles próprios do
banco mais uma amostra estratificada do Lichess, cada um com o gabarito da
engine nas posições inicial e do erro. Sem texto de terceiros.

Gerar (só o usuário, contra o banco real):
    cd backend && uv run python -m evals.coach.dataset --saida evals/coach/dataset/v1.json
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import chess
from sqlalchemy import select
from sqlalchemy.orm import Session

from chess_trainer.coach.tools import ContextoExercicio, contexto_do_exercicio
from chess_trainer.coach.verify import Analisar
from chess_trainer.core.models import LichessPuzzle, LichessPuzzleTheme, Puzzle
from chess_trainer.core.tactics.convert import to_tactic
from chess_trainer.core.tactics.themes import THEME_LABELS

TEMAS_GENERICOS = {"short", "long", "veryLong", "oneMove", "middlegame", "endgame", "opening", "crushing", "advantage",
                   "equality", "mate", "master", "masterVsMaster", "superGM"}
FAIXAS = ((0, 1399), (1400, 1799), (1800, 9999))
N_TEMAS = 10


@dataclass
class ItemAvaliacao:
    id: str
    origem: str
    contexto: dict
    rating: int | None
    gabarito: dict


def contexto_de_item(item: ItemAvaliacao) -> ContextoExercicio:
    d = dict(item.contexto)
    d["lances_permitidos"] = set(d.get("lances_permitidos", []))
    return ContextoExercicio(**d)


def _gabarito(ctx: ContextoExercicio, analisar: Analisar) -> dict:
    g = {"inicial": analisar(ctx.fen_inicial, 3), "erro": None}
    if ctx.fen_erro:
        g["erro"] = analisar(ctx.fen_erro, 3)
    return g


def _contexto_lichess(row: LichessPuzzle) -> ContextoExercicio:
    t = to_tactic(row)
    board = chess.Board(t.fen_start)
    solucao = []
    for m in t.solution["moves"]:
        mv = chess.Move.from_uci(m["uci"])
        solucao.append(board.san(mv))
        board.push(mv)
    antes = chess.Board(t.fen_before)
    ultimo = chess.Move.from_uci(t.last_move)
    return ContextoExercicio(
        puzzle_id=f"lichess:{row.id}", tipo="lichess", lado="brancas" if t.side_to_move == "white" else "pretas",
        fen_inicial=t.fen_start, fen_erro=t.fen_before, solucao_san=solucao,
        lance_errado={"san": antes.san(ultimo), "uci": t.last_move, "de_quem": "adversário", "nivel": None, "aval_antes": None, "aval_depois": None},
        minha_resposta=None, partida=None, tema=THEME_LABELS.get(t.theme, t.theme), categoria="lichess",
        lances_permitidos={t.solution["moves"][0]["uci"], t.last_move},
    )


def _amostra_lichess(db: Session, n: int, seed: int) -> list[LichessPuzzle]:
    if n <= 0:
        return []
    rnd = random.Random(seed)
    contagem = Counter(t for (t,) in db.execute(select(LichessPuzzleTheme.theme)).all() if t not in TEMAS_GENERICOS)
    temas = [t for t, _ in contagem.most_common(N_TEMAS)]
    por_celula = max(1, n // max(1, len(temas) * len(FAIXAS)))
    escolhidos: dict[str, LichessPuzzle] = {}
    for tema in temas:
        for lo, hi in FAIXAS:
            ids = list(db.scalars(select(LichessPuzzleTheme.puzzle_id).join(LichessPuzzle, LichessPuzzle.id == LichessPuzzleTheme.puzzle_id)
                                  .where(LichessPuzzleTheme.theme == tema, LichessPuzzle.rating >= lo, LichessPuzzle.rating <= hi)))
            rnd.shuffle(ids)
            for pid in ids[:por_celula]:
                if pid not in escolhidos:
                    escolhidos[pid] = db.get(LichessPuzzle, pid)
            if len(escolhidos) >= n:
                break
    return list(escolhidos.values())[:n]


def montar(db: Session, analisar: Analisar, n_lichess: int = 120, seed: int = 7) -> list[ItemAvaliacao]:
    items: list[ItemAvaliacao] = []
    for p in db.scalars(select(Puzzle).where(Puzzle.source == "own").order_by(Puzzle.created_at)):
        ctx = contexto_do_exercicio(db, p)
        items.append(ItemAvaliacao(id=f"own:{p.id}", origem="own", contexto=ctx.to_dict(), rating=None, gabarito=_gabarito(ctx, analisar)))
    for row in _amostra_lichess(db, n_lichess, seed):
        try:
            ctx = _contexto_lichess(row)
        except ValueError:
            continue
        items.append(ItemAvaliacao(id=f"lichess:{row.id}", origem="lichess", contexto=ctx.to_dict(), rating=row.rating, gabarito=_gabarito(ctx, analisar)))
    return items


def salvar(items: list[ItemAvaliacao], path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps([asdict(i) for i in items], ensure_ascii=False, indent=1), encoding="utf-8")


def carregar(path: Path) -> list[ItemAvaliacao]:
    return [ItemAvaliacao(**d) for d in json.loads(Path(path).read_text(encoding="utf-8"))]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Gera o conjunto de avaliação do treinador a partir do banco do app.")
    ap.add_argument("--saida", default="evals/coach/dataset/v1.json")
    ap.add_argument("--n-lichess", type=int, default=120)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)
    from evals.coach.run import _analisar, _db
    db = _db()
    try:
        items = montar(db, _analisar(), args.n_lichess, args.seed)
    finally:
        db.close()
    salvar(items, Path(args.saida))
    print(f"{len(items)} itens em {args.saida}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Implementar `judge.py` e `metrics.py`**

`judge.py`:

```python
"""Nota pedagógica por LLM-as-judge (spec §8.2), com rubrica fixa em português."""
from __future__ import annotations

from chess_trainer.coach.llm import LlmClient

RUBRICA = """Você avalia a explicação de um treinador de xadrez para um aluno, sobre um erro dele.
Dê uma nota de 1 a 5 considerando, em ordem: (1) correção: os lances e avaliações batem com o
contexto e a engine; (2) clareza: um jogador de clube entende sem esforço; (3) foco: fala do erro
deste aluno nesta posição, não de generalidades; (4) ação: termina com o que treinar, concreto.
5 = tudo isso; 3 = correta mas genérica ou confusa; 1 = errada ou inútil. Entregue nota e uma
justificativa de uma frase pela ferramenta."""

ESQUEMA_NOTA = {"type": "object", "properties": {"nota": {"type": "integer", "minimum": 1, "maximum": 5}, "justificativa": {"type": "string"}},
                "required": ["nota", "justificativa"], "additionalProperties": False}


def julgar(llm: LlmClient, contexto_texto: str, explicacao: str) -> dict:
    r = llm.run_agent(system=RUBRICA, user=f"## Contexto do exercício\n{contexto_texto}\n\n## Explicação do treinador\n{explicacao}",
                      ferramentas=[], esquema_final=ESQUEMA_NOTA, effort="medium", max_tokens=1024)
    est = r.estruturado or {"nota": 0, "justificativa": "o juiz não devolveu nota"}
    return {"nota": int(est.get("nota", 0)), "justificativa": str(est.get("justificativa", ""))}
```

`metrics.py`:

```python
"""Métricas de uma rodada (spec §8.2): tudo sai do verificador e dos custos; a nota do juiz é opcional."""
from __future__ import annotations

from collections import Counter

import numpy as np


def _p(valores: list[float], q: float) -> float:
    return float(np.percentile(valores, q)) if valores else 0.0


def resumir(linhas: list[dict]) -> dict:
    n = len(linhas)
    if n == 0:
        return {"n": 0}
    tipos = Counter(i["tipo"] for l in linhas for i in l["issues"])
    notas = [l["nota"] for l in linhas if l.get("nota")]
    lat = [l["duration_ms"] for l in linhas]
    return {
        "n": n,
        "taxa_erros": sum(1 for l in linhas if l["status"] == "errors") / n,
        "taxa_avisos": sum(1 for l in linhas if l["status"] == "warnings") / n,
        "taxa_ok": sum(1 for l in linhas if l["status"] == "ok") / n,
        "taxa_corrigidas": sum(1 for l in linhas if l["repaired"]) / n,
        "por_tipo": {t: round(100.0 * c / n, 1) for t, c in sorted(tipos.items())},  # ocorrências por 100 explicações
        "custo_medio_usd": round(sum(l["custo_usd"] for l in linhas) / n, 4),
        "custo_total_usd": round(sum(l["custo_usd"] for l in linhas), 4),
        "latencia_p50_ms": _p(lat, 50), "latencia_p95_ms": _p(lat, 95),
        "tokens_medios": {k: round(sum(l["tokens"][k] for l in linhas) / n) for k in ("input", "output", "cache_read", "cache_write")},
        "chamadas_api_medias": round(sum(l["n_chamadas_api"] for l in linhas) / n, 2),
        "nota_media": round(sum(notas) / len(notas), 2) if notas else None,
    }


def _ranks(v: list[float]) -> np.ndarray:
    a = np.asarray(v, dtype=float)
    ordem = a.argsort()
    r = np.empty(len(a))
    r[ordem] = np.arange(1, len(a) + 1)
    # empates: média das posições
    for valor in np.unique(a):
        m = a == valor
        if m.sum() > 1:
            r[m] = r[m].mean()
    return r


def spearman(a: list[float], b: list[float]) -> float:
    """Correlação de Spearman entre duas listas (para calibrar o juiz contra as notas do usuário)."""
    if len(a) != len(b) or len(a) < 2:
        return 0.0
    ra, rb = _ranks(a), _ranks(b)
    if ra.std() == 0 or rb.std() == 0:
        return 0.0
    return float(np.corrcoef(ra, rb)[0, 1])
```

- [ ] **Step 5: Implementar `run.py`**

```python
"""Roda uma variante do treinador sobre o conjunto de avaliação e grava a rodada.

    cd backend && ANTHROPIC_API_KEY=... uv run python -m evals.coach.run --variante agente_rag --modelo opus --n 30

Precisa do Stockfish (verificação) e, para `agente_rag`, do banco do app com o
índice criado (`CHESS_TRAINER_DB`). A chave vem do ambiente, não do banco."""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

from chess_trainer.coach.explain import OpcoesExplicacao, explicar
from chess_trainer.coach.llm import AnthropicClient, ErroDoTreinador, LlmClient
from chess_trainer.coach.prompts import PROMPT_VERSION
from chess_trainer.coach.verify import Analisar
from evals.coach import metrics
from evals.coach.dataset import ItemAvaliacao, carregar, contexto_de_item
from evals.coach.judge import julgar

MODELOS = {"opus": "claude-opus-5", "sonnet": "claude-sonnet-5"}


def rodar(items: list[ItemAvaliacao], llm: LlmClient, analisar: Analisar, buscar, opcoes: OpcoesExplicacao,
          juiz: LlmClient | None = None) -> list[dict]:
    linhas = []
    for item in items:
        ctx = contexto_de_item(item)
        inicio = time.monotonic()
        try:
            r = explicar(contexto=ctx, llm=llm, analisar=analisar, estatisticas=None, buscar=buscar, opcoes=opcoes)
        except ErroDoTreinador as exc:
            linhas.append({"id": item.id, "origem": item.origem, "status": "errors", "ok": False, "erros": 1, "avisos": 0,
                           "issues": [{"tipo": exc.codigo, "gravidade": "erro", "detalhe": exc.mensagem, "linha_idx": None}],
                           "repaired": False, "custo_usd": 0.0, "duration_ms": int((time.monotonic() - inicio) * 1000),
                           "tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}, "n_chamadas_api": 0,
                           "texto": "", "estruturado": None, "nota": None, "justificativa": None})
            continue
        nota = julgar(juiz, ctx.texto(), r.texto) if juiz is not None else {"nota": None, "justificativa": None}
        linhas.append({
            "id": item.id, "origem": item.origem, "status": r.status, "ok": r.verificacao.ok,
            "erros": r.verificacao.erros, "avisos": r.verificacao.avisos, "issues": r.verificacao.to_dict()["issues"],
            "repaired": r.repaired, "custo_usd": r.custo_usd, "duration_ms": r.duration_ms, "tokens": r.uso.to_dict(),
            "n_chamadas_api": r.n_chamadas_api, "texto": r.texto, "estruturado": r.estruturado, **nota,
        })
    return linhas


# --- ligações com o ambiente real (substituídas nos testes) ------------------

def _db():
    from chess_trainer.core.db import init_db, make_engine, make_session_factory
    engine = make_engine(os.environ.get("CHESS_TRAINER_DB", str(Path(__file__).resolve().parents[2] / "data" / "chess_trainer.db")))
    init_db(engine)
    return make_session_factory(engine)()


def _analisar() -> Analisar:
    from chess_trainer.config import load_settings
    from chess_trainer.core.analysis.engine import StockfishEngine, find_stockfish
    from chess_trainer.core.analysis.interactive import InteractiveAnalyzer
    db = _db()
    try:
        path = find_stockfish(load_settings(db).stockfish_path)
    finally:
        db.close()
    if not path:
        raise SystemExit("Stockfish não encontrado: a verificação precisa da engine")
    return InteractiveAnalyzer(lambda: StockfishEngine(path, threads=2, hash_mb=64)).analyse


def _buscar():
    from chess_trainer.coach.retrieval.embeddings import FastembedEmbeddings
    from chess_trainer.coach.retrieval.index import Indexador
    db = _db()
    idx = Indexador(db.get_bind(), FastembedEmbeddings(cache_dir=Path(__file__).resolve().parents[2] / "data" / "fastembed"))
    return lambda consulta, k: idx.buscar(db, consulta, k)


def _llm(modelo: str) -> LlmClient:
    chave = os.environ.get("ANTHROPIC_API_KEY", "")
    if not chave:
        raise SystemExit("defina ANTHROPIC_API_KEY no ambiente para rodar a avaliação")
    return AnthropicClient(chave, modelo)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Roda a avaliação offline do treinador.")
    ap.add_argument("--dataset", default="evals/coach/dataset/v1.json")
    ap.add_argument("--variante", choices=("prompt", "agente", "agente_rag"), default="agente_rag")
    ap.add_argument("--modelo", choices=tuple(MODELOS), default="opus")
    ap.add_argument("--effort", choices=("low", "medium", "high"), default="high")
    ap.add_argument("--n", type=int, default=0, help="limita aos N primeiros itens (0 = todos)")
    ap.add_argument("--saida", default="evals/coach/runs")
    ap.add_argument("--sem-juiz", action="store_true")
    ap.add_argument("--juiz", choices=tuple(MODELOS), default="opus")
    args = ap.parse_args(argv)

    items = carregar(Path(args.dataset))
    if args.n:
        items = items[: args.n]
    modelo = MODELOS[args.modelo]
    llm = _llm(modelo)
    juiz = None if args.sem_juiz else _llm(MODELOS[args.juiz])
    buscar = _buscar() if args.variante == "agente_rag" else None
    opcoes = OpcoesExplicacao(variante=args.variante, effort=args.effort)
    linhas = rodar(items, llm, _analisar(), buscar, opcoes, juiz)

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    nome = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{args.variante}-{args.modelo}"
    (saida / f"{nome}.jsonl").write_text("\n".join(json.dumps(l, ensure_ascii=False) for l in linhas) + "\n", encoding="utf-8")
    resumo = {"variante": args.variante, "modelo": modelo, "effort": args.effort, "prompt_version": PROMPT_VERSION,
              "dataset": str(args.dataset), "data": datetime.now().date().isoformat(), **metrics.resumir(linhas)}
    (saida / f"{nome}.resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resumo, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Implementar `report.py`**

```python
"""Relatório em markdown a partir dos resumos das rodadas (spec §8.2).

    cd backend && uv run python -m evals.coach.report evals/coach/runs/*.resumo.json --saida ../docs/coach-eval.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

COLUNAS = (("variante", "variante"), ("modelo", "modelo"), ("n", "n"), ("taxa_ok", "ok"), ("taxa_avisos", "com ressalvas"),
           ("taxa_erros", "com erros"), ("taxa_corrigidas", "corrigidas"), ("nota_media", "nota do juiz"),
           ("custo_medio_usd", "custo médio (US$)"), ("latencia_p50_ms", "p50 (ms)"), ("latencia_p95_ms", "p95 (ms)"))


def _fmt(chave: str, v) -> str:
    if v is None:
        return "–"
    if chave.startswith("taxa_"):
        return f"{100 * v:.0f}%"
    if isinstance(v, float):
        return f"{v:.3f}" if "usd" in chave else f"{v:.2f}"
    return str(v)


def escrever_relatorio(resumos: list[dict], path: Path, meta: dict) -> str:
    linhas = ["# Avaliação do treinador", "",
              f"Conjunto: `{meta.get('dataset', '?')}` · prompt `{meta.get('prompt_version', '?')}` · {meta.get('data', '')}", "",
              "| " + " | ".join(r for _, r in COLUNAS) + " |", "|" + "---|" * len(COLUNAS)]
    for r in resumos:
        linhas.append("| " + " | ".join(_fmt(c, r.get(c)) for c, _ in COLUNAS) + " |")
    tipos = sorted({t for r in resumos for t in r.get("por_tipo", {})})
    if tipos:
        linhas += ["", "## Problemas por 100 explicações", "", "| variante | modelo | " + " | ".join(tipos) + " |", "|---|---|" + "---|" * len(tipos)]
        for r in resumos:
            linhas.append(f"| {r['variante']} | {r['modelo']} | " + " | ".join(str(r.get("por_tipo", {}).get(t, 0)) for t in tipos) + " |")
    total = sum(r.get("custo_total_usd", 0) or 0 for r in resumos)
    linhas += ["", f"Custo total das rodadas: US$ {total:.2f}.", "",
               "Métricas: `ok` = nenhuma ressalva do verificador; `com erros` = lance ilegal, avaliação errada ou citação inexistente; "
               "a nota do juiz é de 1 a 5 pela rubrica em `evals/coach/judge.py`."]
    texto = "\n".join(linhas) + "\n"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(texto, encoding="utf-8")
    return texto


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("resumos", nargs="+")
    ap.add_argument("--saida", default="../docs/coach-eval.md")
    args = ap.parse_args(argv)
    resumos = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.resumos]
    meta = {"dataset": resumos[0].get("dataset"), "prompt_version": resumos[0].get("prompt_version"), "data": resumos[0].get("data")}
    print(escrever_relatorio(resumos, Path(args.saida), meta))


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: `.gitignore` e marker** — acrescente `backend/evals/coach/runs/`, `.env` e `.smoke-data/` ao `.gitignore`; em `backend/pyproject.toml`, `markers = ["slow: precisa do Stockfish real", "network: chama a API de verdade (precisa de ANTHROPIC_API_KEY)"]` e `addopts = "-m 'not slow and not network'"` só se a suíte já não filtrar `slow` de outro jeito (confira `conftest.py`/CI; se já houver filtro, acrescente `network` a ele).

- [ ] **Step 8: Rodar e ver passar** — `cd backend && uv run pytest tests/test_coach_eval.py -q` → 4 passed; depois a suíte inteira.

- [ ] **Step 9: Commit**

```bash
git add backend/evals backend/tests/test_coach_eval.py backend/pyproject.toml .gitignore
printf 'feat(treinador): avaliação offline — conjunto, rodadas, métricas, juiz e relatório\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n' > "$TEMP/msg.txt" && git commit -F "$TEMP/msg.txt"
```

---

### Task 14: Docker (app + LangFuse)

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `docker/langfuse.compose.yml`, `docker/compose.smoke.yml`, `.env.example`
- Modify: `backend/chess_trainer/core/analysis/engine.py` (`STOCKFISH_PATH`)
- Test: `backend/tests/test_engine.py` (acrescentar), verificação manual do Compose

**Interfaces:**
- Variáveis de ambiente do contêiner: `CHESS_TRAINER_DATA=/data`, `CHESS_TRAINER_DB=/data/chess_trainer.db`, `STOCKFISH_PATH=/usr/games/stockfish`, `CHESS_TRAINER_HOST=0.0.0.0`.
- `find_stockfish(configured)` passa a olhar `STOCKFISH_PATH` antes do `PATH`.

- [ ] **Step 1: Teste do `STOCKFISH_PATH` (falhando)** — em `tests/test_engine.py`:

```python
def test_find_stockfish_respeita_a_variavel_de_ambiente(tmp_path, monkeypatch):
    from chess_trainer.core.analysis.engine import find_stockfish
    binario = tmp_path / "stockfish"
    binario.write_bytes(b"")
    monkeypatch.setenv("STOCKFISH_PATH", str(binario))
    assert find_stockfish("") == str(binario)
    monkeypatch.setenv("STOCKFISH_PATH", str(tmp_path / "nao-existe"))
    monkeypatch.setattr("shutil.which", lambda _n: None)
    assert find_stockfish("") is None or not find_stockfish("").endswith("nao-existe")
```

Implementação em `find_stockfish`, logo depois do `configured`:

```python
    env = os.environ.get("STOCKFISH_PATH", "")
    if env and Path(env).is_file():
        return env
```

Run: `cd backend && uv run pytest tests/test_engine.py -q -k variavel` → passa.

- [ ] **Step 2: `Dockerfile` e `.dockerignore`**

`.dockerignore`:

```
.git
.superpowers
.venv
**/__pycache__
backend/.venv
backend/data
backend/engines
backend/evals/coach/runs
frontend/node_modules
frontend/dist
docs
.smoke-data
```

`Dockerfile`:

```dockerfile
# estágio 1: frontend
FROM node:22-alpine AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# estágio 2: backend + Stockfish + frontend compilado
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends stockfish && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --frozen --no-dev
COPY --from=frontend /src/frontend/dist /app/frontend/dist
ENV CHESS_TRAINER_DATA=/data \
    CHESS_TRAINER_DB=/data/chess_trainer.db \
    STOCKFISH_PATH=/usr/games/stockfish \
    CHESS_TRAINER_HOST=0.0.0.0
VOLUME ["/data"]
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "python", "-m", "chess_trainer"]
```

- [ ] **Step 3: Compose**

Baixe o compose oficial do LangFuse (arquivo de texto, ~10 KB) para `docker/langfuse.compose.yml`:

```bash
curl -fsSL https://raw.githubusercontent.com/langfuse/langfuse/main/docker-compose.yml -o docker/langfuse.compose.yml
```

e edite: cada valor marcado `# CHANGEME` vira uma variável (`${LANGFUSE_POSTGRES_PASSWORD}`, `${LANGFUSE_SALT}`, `${LANGFUSE_ENCRYPTION_KEY}`, `${LANGFUSE_NEXTAUTH_SECRET}`, `${LANGFUSE_CLICKHOUSE_PASSWORD}`, `${LANGFUSE_MINIO_SECRET}`, `${LANGFUSE_REDIS_AUTH}`), mantendo os nomes de serviço e as portas (web em 3000). Não commite valores reais.

`.env.example` (copiado para `.env`, que é ignorado pelo git):

```
# LangFuse local (docker compose). Gere valores com: openssl rand -hex 32
LANGFUSE_POSTGRES_PASSWORD=troque
LANGFUSE_SALT=troque
LANGFUSE_ENCRYPTION_KEY=0000000000000000000000000000000000000000000000000000000000000000
LANGFUSE_NEXTAUTH_SECRET=troque
LANGFUSE_CLICKHOUSE_PASSWORD=troque
LANGFUSE_MINIO_SECRET=troque
LANGFUSE_REDIS_AUTH=troque
```

`docker-compose.yml` (raiz):

```yaml
include:
  - docker/langfuse.compose.yml

services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./backend/data:/data
    environment:
      CHESS_TRAINER_HOST: "0.0.0.0"
    restart: unless-stopped
```

`docker/compose.smoke.yml` (para verificar sem tocar em `backend/data`):

```yaml
services:
  app:
    volumes:
      - ./.smoke-data:/data
```

- [ ] **Step 4: Verificar** (o download das imagens é de ~2,5 GB: **combine com o usuário antes de rodar `build`/`up`**)

```bash
docker compose config > /dev/null && echo "compose ok"
docker compose build app
docker compose -f docker-compose.yml -f docker/compose.smoke.yml up -d
curl -s http://127.0.0.1:8000/api/status | head -c 200
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3000
docker compose -f docker-compose.yml -f docker/compose.smoke.yml down
```

Esperado: `compose ok`; status com `"engine": {"available": true, "path": "/usr/games/stockfish"}`; LangFuse responde 200 ou 307 na porta 3000. Se a porta 8000 já estiver ocupada pelo servidor local (tarefa agendada "ChessTrainer"), mapeie `8001:8000` no arquivo de smoke.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore docker-compose.yml docker .env.example backend/chess_trainer/core/analysis/engine.py backend/tests/test_engine.py
printf 'feat: Dockerfile do app (Stockfish incluso) e Compose com LangFuse local\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n' > "$TEMP/msg.txt" && git commit -F "$TEMP/msg.txt"
```

---

### Task 15: Documentação e teste com a API real

**Files:**
- Modify: `docs/manual.pt-BR.md` (seção "Treinador (IA)" e "Rodar com Docker"), `README.md` (bullet em "What it does", "AI coach" no guia, Docker em "Running it")
- Create: `backend/tests/test_coach_real.py`

- [ ] **Step 1: Manual** — antes de `## Fontes de exercício`, inserir:

```markdown
## Treinador (IA)

Na tela de resultado de um exercício, o botão **Explicar** pede a um treinador com IA que escreva,
em português, o que aconteceu na partida, por que o lance perde, qual é o padrão, onde ele aparece
nos seus estudos e o que treinar. O treinador é um agente: consulta o Stockfish, o contexto da
partida, as suas estatísticas por tema e busca nos comentários dos capítulos dos seus estudos.

Antes de mostrar o texto, um **verificador** reproduz cada linha citada no tabuleiro, confere se o
primeiro lance está entre os três melhores da engine, compara as avaliações e confirma que cada
citação existe. O selo **verificado pela engine** quer dizer que nada foi apontado; **com ressalvas**
lista avisos; **não verificado** lista erros que nem a correção automática resolveu. Nunca há lance
escondido: o que não bateu aparece no cartão.

Os lances do texto são links (prévia no tabuleiro) e as citações abrem o capítulo no modo livro, no
lance certo. O rodapé mostra o modelo, o custo em dólares e o tempo.

### Configurar

Em **Configurações → Treinador (IA)**: cole a chave da API da Anthropic (crie no Console e defina lá
um teto de gasto; cada explicação custa alguns centavos de dólar), escolha o modelo (Opus 5 ou
Sonnet 5) e o esforço. A chave fica só no seu banco e nunca sai pela API do app.

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
```

Em `## Rodar`, acrescentar:

```markdown
### Rodar com Docker

`docker compose up -d` sobe o app em http://localhost:8000 (com o Stockfish dentro da imagem e o
banco em `backend/data`) e o LangFuse em http://localhost:3000. Copie `.env.example` para `.env` e
troque os segredos antes. Para desenvolvimento, `uv run` e `npm run dev` continuam valendo.
```

- [ ] **Step 2: README** — em "What it does", um bullet: `- **AI coach.** After an exercise, "Explain" asks an LLM agent (engine, game context, your stats and a search over your own studies) to explain the mistake in Portuguese. Every line it cites is replayed on the board and checked against Stockfish before you see it; what does not check out is shown, never hidden. Measured offline against a baseline (see \`docs/coach-eval.md\` once a run exists).`; em "Running it", `docker compose up -d` como alternativa; no guia, uma seção "### AI coach" traduzindo os dois primeiros parágrafos da seção do manual. Sem relatório ainda, não linke `docs/coach-eval.md` como existente: diga "generated by the evaluation scripts".

- [ ] **Step 3: Teste com a API real** — `backend/tests/test_coach_real.py`:

```python
"""Uma explicação de verdade contra a API (custa alguns centavos). Só roda com
`ANTHROPIC_API_KEY` no ambiente e `-m network`; fora do CI."""
import os

import pytest

from chess_trainer.coach.explain import OpcoesExplicacao, explicar
from chess_trainer.coach.llm import AnthropicClient
from chess_trainer.coach.tools import contexto_do_exercicio
from tests.test_coach_explain import analisar
from tests.test_coach_tools import puzzle_punir

pytestmark = pytest.mark.network


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="sem ANTHROPIC_API_KEY")
def test_explicacao_real_passa_no_verificador(db_session):
    ctx = contexto_do_exercicio(db_session, puzzle_punir(db_session))
    llm = AnthropicClient(os.environ["ANTHROPIC_API_KEY"], os.environ.get("COACH_MODEL", "claude-sonnet-5"))
    r = explicar(contexto=ctx, llm=llm, analisar=analisar, estatisticas=None, buscar=None,
                 opcoes=OpcoesExplicacao(variante="agente", effort="low"))
    print(r.texto, r.verificacao.to_dict(), r.custo_usd)
    assert r.estruturado is not None and 60 <= len(r.texto.split()) <= 400
    assert r.verificacao.erros == 0, r.verificacao.to_dict()
```

Run: `cd backend && uv run pytest -q` (o teste fica de fora pelo marker); com chave: `ANTHROPIC_API_KEY=... uv run pytest tests/test_coach_real.py -m network -s`. Quem roda com a chave é o usuário.

- [ ] **Step 4: Commit**

```bash
git add docs/manual.pt-BR.md README.md backend/tests/test_coach_real.py
printf 'docs(treinador): manual, README e teste opcional contra a API real\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n' > "$TEMP/msg.txt" && git commit -F "$TEMP/msg.txt"
```

---

## Depois das tarefas (o usuário)

1. Criar a chave no Console da Anthropic com teto mensal; colar em Configurações; clicar **Recriar índice** (baixa o modelo de embeddings).
2. `docker compose up -d`; criar o projeto no LangFuse; colar host e chaves.
3. Gerar o conjunto (`evals.coach.dataset`), rodar as seis combinações (3 variantes × 2 modelos), avaliar 20 itens à mão para calibrar o juiz, gerar `docs/coach-eval.md` e linká-lo no README.
4. Decidir, com o relatório, o modelo padrão e o esforço.
