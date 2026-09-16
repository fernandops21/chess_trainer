# Golpes, fase A — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a partir da solução de cada puzzle, calcular a assinatura do golpe, achar no milhão do Lichess os irmãos de um erro, mostrar o golpe desenhado, treinar um bloco de irmãos e mandá-los para a repetição espaçada; mais a tela de rotulagem (dev) que produz o conjunto de ouro.

**Architecture:** pacote puro `core/golpes/` (assinatura por regras com python-chess, três níveis, hashes de 64 bits) + tabelas de assinatura preenchidas por uma tarefa do `JobRunner` + serviço de busca em cascata (mesmo golpe → espelho → esqueleto na mesma zona) + rotas `/api/golpes/*` + cartão "Repetir o golpe" nos dois painéis de resultado + sessão de táticas com lista fixa que salva cada irmão com `sibling_of`. Rotulagem atrás de `CHESS_TRAINER_ROTULAGEM=1`. Sem modelo nesta fase.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 (SQLite, sem Alembic), python-chess 1.11 (`chess.svg`), pytest; React 19/TypeScript/Vite/Vitest/Testing Library, TanStack Query, chessground.

**Spec:** `docs/superpowers/specs/2026-09-16-golpes-design.md` (fase A = §3–§6, §8, §10, passos 1–4 de §11).

## Global Constraints

- Comentários, mensagens, UI e commits em português. Vocabulário de produto; nunca mencionar motivação pessoal em arquivo do repositório.
- Backend: `cd backend && uv run pytest -q` (684 passam hoje; nunca cair). Frontend: `cd frontend && npm test && npm run build` (680 passam). `npm.cmd` no Bash se `npm` estiver bloqueado.
- Nunca tocar em `backend/data/*` nem em `.claude/`. Nunca baixar nada. Nenhum agente executa treino de modelo (não há treino nesta fase).
- Commit via arquivo: `printf 'mensagem\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n' > "$TEMP/msg.txt" && git commit -F "$TEMP/msg.txt"`. Só adicionar ao stage os arquivos da tarefa.
- Padrões do código: ids `new_id()` (uuid4), `utcnow()` de `chess_trainer.core.models`; migração = declarar o modelo (tabelas novas nascem no `create_all`) e, para coluna nova em tabela antiga, tupla + `_acrescenta_colunas` em `core/db.py:213-218`; rotas com `APIRouter(prefix=...)`, `db: Session = Depends(get_db)`; esquemas pydantic em `api/schemas.py`; testes de API constroem o app com `create_app(db_path=":memory:", engine_factory=lambda s: FakeEngine(default=first_legal_default(0)))` e `TestClient`.
- `VERSAO_ASSINATURA = 1`. Nível padrão da busca: `destinos`.

---

## Mapa de arquivos

| arquivo | responsabilidade |
| --- | --- |
| `backend/chess_trainer/core/golpes/__init__.py` | vazio |
| `backend/chess_trainer/core/golpes/assinatura.py` | puro: anotação dos lances, normalização, níveis, hashes, espelho |
| `backend/chess_trainer/core/golpes/service.py` | assinar Lichess/próprio, garantir assinatura, tarefa de preparo, cobertura, busca de irmãos |
| `backend/chess_trainer/core/golpes/imagem.py` | SVG do golpe |
| `backend/chess_trainer/core/golpes/rotulagem.py` | próximo item de rotulagem, gravação, exportação do ouro |
| `backend/chess_trainer/core/models.py` | `LichessPuzzleSignature`, `PuzzleSignature`, `GolpeLabel`, `Puzzle.sibling_of` |
| `backend/chess_trainer/core/db.py` | coluna `sibling_of` em bancos antigos |
| `backend/chess_trainer/config.py`, `api/schemas.py` | `golpes_enabled`, `golpes_bloco`; esquemas das rotas |
| `backend/chess_trainer/api/routes/golpes.py` | `/api/golpes/*` |
| `backend/chess_trainer/api/routes/tactics.py` | `sibling_of` no salvamento |
| `backend/chess_trainer/api/app.py` | registrar rota, `app.state.rotulagem_enabled` |
| `frontend/src/api/{types,client,queries}.ts` | tipos, chamadas, hooks |
| `frontend/src/train/GolpeCard.tsx` | cartão "Repetir o golpe" |
| `frontend/src/train/BlocoContext.tsx` | como o cartão abre o bloco |
| `frontend/src/train/TacticSession.tsx`, `TrainPage.tsx`, `SessionStart.tsx` | lista fixa, `sibling_of`, montagem do bloco |
| `frontend/src/pages/SettingsPage.tsx`, `components/JobCard.tsx` | seção Golpes, tarefa |
| `frontend/src/pages/RotulagemPage.tsx`, `App.tsx` | rotulagem (dev) |
| `docs/manual.pt-BR.md`, `README.md` | seção Golpes |

---

### Task 1: assinatura do golpe (pura)

**Files:**
- Create: `backend/chess_trainer/core/golpes/__init__.py`, `backend/chess_trainer/core/golpes/assinatura.py`
- Test: `backend/tests/test_golpes_assinatura.py`

**Interfaces:**
- Produces:
  - `VERSAO_ASSINATURA: int = 1`
  - `@dataclass(frozen=True) class Lance: peca: str; origem: str; destino: str; captura: str | None; xeque: str; promocao: str | None; descobertas: tuple[tuple[str, str, str], ...]; ataques: tuple[tuple[str, str], ...]` — `xeque ∈ {"", "+", "++", "d+", "#"}`; descoberta = `(letra_da_peça_atacada, casa_dela, casa_de_quem_ataca)`; ataque = `(letra, casa)`.
  - `@dataclass(frozen=True) class Assinatura: rei: str; lances: tuple[Lance, ...]` com `zona_rei -> str`, `esqueleto() -> str`, `destinos() -> str`, `completo() -> str`, `espelhada() -> Assinatura`, `hashes() -> dict[str, int]` (chaves `esqueleto`, `destinos`, `destinos_esp`, `completo`).
  - `anotar(board: chess.Board, lances_uci: Sequence[str], max_lances: int = 3) -> Assinatura` — anota no tabuleiro dado, sem normalizar (a imagem usa).
  - `assinar(fen: str, lances_uci: Sequence[str], max_lances: int = 3) -> Assinatura` — normaliza (quem joga vira brancas) e anota. Levanta `ValueError` em FEN inválida ou lance ilegal.
  - `hash64(texto: str) -> int`.

- [ ] **Step 1: escrever os testes que falham**

```python
# backend/tests/test_golpes_assinatura.py
import chess
import pytest

from chess_trainer.core.golpes.assinatura import (VERSAO_ASSINATURA, Assinatura, Lance, anotar, assinar, hash64)

# Francesa, avanço: 1.e4 e6 2.d4 d5 3.e5 c5 4.c3 Nc6 5.Nf3 Qb6 6.Bd3 cxd4 7.cxd4 Nxd4 8.Nxd4 Qxd4; brancas jogam 9.Bb5+
FEN_FRANCESA = "r1b1kbnr/pp3ppp/4p3/3pP3/3q4/3B4/PP3PPP/RNBQK2R w KQkq - 0 9"
# Beijo grego: brancas jogam 1.Bxh7+ Kxh7 2.Ng5+ Kg8 3.Qh5
FEN_BEIJO = "r1bq1rk1/pp1nbppp/2p1p3/3pP3/3P4/2PB1N2/PP3PPP/R1BQ1RK1 w - - 0 11"
# Garfo: cavalo branco em d5, rei preto g8, dama preta c8 sem defesa; 1.Ne7+ Kh8 2.Nxc8
FEN_GARFO = "2q3k1/pp3ppp/8/3N4/8/8/PP3PPP/6K1 w - - 0 1"


def test_francesa_anota_o_xeque_que_descobre_a_dama():
    a = assinar(FEN_FRANCESA, ["d3b5", "e8e7", "d1d4"])
    assert a.rei == "e8" and a.zona_rei == "centro-fundo"
    b5, xd4 = a.lances
    assert b5 == Lance("B", "d3", "b5", None, "+", None, (("Q", "d4", "d1"),), ())
    assert xd4.peca == "Q" and xd4.destino == "d4" and xd4.captura == "Q" and xd4.xeque == ""
    assert a.destinos() == "Ke8 | B b5 + desc(Qd4) | Q xQ d4"
    assert a.esqueleto() == "Kcentro-fundo | B + desc(Q) | Q xQ"
    assert a.completo() == "Ke8 | B d3-b5 + desc(Qd4<d1) | Q d1-d4 xQ"


def test_beijo_grego():
    a = assinar(FEN_BEIJO, ["d3h7", "g8h7", "f3g5", "h7g8", "d1h5"])
    assert a.destinos() == "Kg8 | B xP h7 + | N g5 + | Q h5"
    assert a.zona_rei == "rei-fundo"


def test_garfo_anota_o_ataque_da_propria_peca():
    a = assinar(FEN_GARFO, ["d5e7", "g8h8", "e7c8"])
    assert a.lances[0].ataques == (("Q", "c8"),) and a.lances[0].xeque == "+"
    assert a.destinos() == "Kg8 | N e7 + atk(Qc8) | N xQ c8"


def test_pretas_a_jogar_da_a_mesma_assinatura_que_brancas():
    # a mesma francesa com as cores trocadas: pretas jogam ...Bb4+ descobrindo a dama de d8 contra d5
    fen_pretas = "rnbqk2r/pp3ppp/3b4/3Q4/3Pp3/4P3/PP3PPP/R1B1KBNR b KQkq - 0 9"
    assert assinar(fen_pretas, ["d6b4", "e1e2", "d8d5"]).destinos() == assinar(FEN_FRANCESA, ["d3b5", "e8e7", "d1d4"]).destinos()


def test_xeque_descoberto_duplo_e_mate():
    # rei preto h8, torre branca e1 atrás do bispo e4? monte: bispo em e4 sai com xeque descoberto da torre em e8? Use posição simples:
    # brancas: Ke1? -> usar mate do corredor: 1.Re8# com rei preto g8 e peões f7 g7 h7
    fen_mate = "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1"
    assert assinar(fen_mate, ["e1e8"]).destinos() == "Kg8 | R e8 #"
    # descoberto: bispo em d5 sai e a torre de d1 dá xeque em d8; bispo captura em b7 sem xeque próprio
    fen_desc = "3k4/1p6/8/3B4/8/8/8/3RK3 w - - 0 1"
    assert assinar(fen_desc, ["d5b7"]).lances[0].xeque == "d+"
    # duplo: o cavalo de e4 vai para d6 com xeque e destapa a torre de e1 contra e8
    fen_duplo = "4k3/8/8/8/4N3/8/8/4RK2 w - - 0 1"
    assert assinar(fen_duplo, ["e4d6"]).lances[0].xeque == "++"


def test_peoes_nao_sao_alvo_e_mate_nao_tem_alvos():
    # beijo grego: Ng5+ "ataca" e6 e f7, mas peões não entram; Qxf7# ataca Bf8 e Nf6, mas depois do mate nada entra
    a = assinar(FEN_BEIJO, ["d3h7", "g8h7", "f3g5"])
    assert a.lances[1].ataques == ()
    pastor = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 5 5"
    m = assinar(pastor, ["h5f7"]).lances[0]
    assert m.xeque == "#" and m.ataques == () and m.descobertas == ()


def test_espelho_troca_as_colunas_e_a_zona():
    a = assinar(FEN_BEIJO, ["d3h7", "g8h7", "f3g5", "h7g8", "d1h5"])
    e = a.espelhada()
    assert e.rei == "b8" and e.zona_rei == "dama-fundo"
    assert e.destinos() == "Kb8 | B xP a7 + | N b5 + | Q a5"
    assert a.hashes()["destinos_esp"] == hash64(e.destinos()) and a.hashes()["destinos"] == hash64(a.destinos())


def test_hash64_estavel_e_com_sinal():
    assert hash64("x") == hash64("x") and isinstance(hash64("x"), int) and -2**63 <= hash64("x") < 2**63
    assert hash64("x") != hash64("y")


def test_limita_a_tres_lances_e_ignora_respostas():
    a = assinar(FEN_BEIJO, ["d3h7", "g8h7", "f3g5", "h7g8", "d1h5", "f8e8", "h5h7"])
    assert len(a.lances) == 3


def test_promocao_e_en_passant():
    fen_promo = "8/1P4k1/8/8/8/8/8/4K3 w - - 0 1"
    assert assinar(fen_promo, ["b7b8q"]).destinos() == "Kg7 | P b8 =Q"
    fen_ep = "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2"
    assert assinar(fen_ep, ["e5d6"]).lances[0].captura == "P"


def test_erros_de_entrada():
    with pytest.raises(ValueError):
        assinar("posicao invalida", ["e2e4"])
    with pytest.raises(ValueError):
        assinar(FEN_BEIJO, ["a1a8"])


def test_anotar_nao_normaliza():
    board = chess.Board("rnbqk2r/pp3ppp/3b4/3Q4/3Pp3/4P3/PP3PPP/R1B1KBNR b KQkq - 0 9")
    a = anotar(board, ["d6b4"])
    assert a.rei == "e1" and a.lances[0].destino == "b4" and VERSAO_ASSINATURA == 1
```

- [ ] **Step 2: rodar e ver falhar**

Run: `cd backend && uv run pytest -q tests/test_golpes_assinatura.py`
Expected: erro de importação (`chess_trainer.core.golpes` não existe).

- [ ] **Step 3: implementar**

```python
# backend/chess_trainer/core/golpes/__init__.py
"""Golpes: assinatura da solução de um puzzle, irmãos e repetição (spec 2026-09-16-golpes-design)."""
```

```python
# backend/chess_trainer/core/golpes/assinatura.py
"""Assinatura do golpe: o que a solução de um puzzle faz, em texto canônico (spec §3).

Puro: só python-chess. `anotar` descreve os lances de quem soluciona no tabuleiro dado;
`assinar` antes vira o tabuleiro para quem soluciona ser sempre as brancas, de modo que o
mesmo golpe jogado por qualquer cor tenha a mesma assinatura."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Sequence

import chess

VERSAO_ASSINATURA = 1
MAX_LANCES = 3
LETRA = {chess.PAWN: "P", chess.KNIGHT: "N", chess.BISHOP: "B", chess.ROOK: "R", chess.QUEEN: "Q", chess.KING: "K"}
VALOR = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
# quantas peças descobertas/atacadas entram por lance: as mais valiosas
LIMITE_ALVOS = 2


@dataclass(frozen=True)
class Lance:
    peca: str
    origem: str
    destino: str
    captura: str | None
    xeque: str  # "", "+", "++", "d+" (descoberto), "#"
    promocao: str | None
    descobertas: tuple[tuple[str, str, str], ...]  # (peça atacada, casa dela, casa de quem passa a atacar)
    ataques: tuple[tuple[str, str], ...]  # (peça atacada, casa dela) pela própria peça que moveu


@dataclass(frozen=True)
class Assinatura:
    rei: str
    lances: tuple[Lance, ...]

    @property
    def zona_rei(self) -> str:
        return zona(chess.parse_square(self.rei))

    def esqueleto(self) -> str:
        partes = []
        for l in self.lances:
            p = [l.peca] + ([f"x{l.captura}"] if l.captura else []) + ([l.xeque] if l.xeque else []) \
                + ([f"={l.promocao}"] if l.promocao else []) \
                + ([f"desc({''.join(sorted(d[0] for d in l.descobertas))})"] if l.descobertas else []) \
                + ([f"atk({''.join(sorted(a[0] for a in l.ataques))})"] if l.ataques else [])
            partes.append(" ".join(p))
        return " | ".join([f"K{self.zona_rei}", *partes])

    def destinos(self) -> str:
        partes = []
        for l in self.lances:
            p = [l.peca] + ([f"x{l.captura}"] if l.captura else []) + [l.destino] + ([l.xeque] if l.xeque else []) \
                + ([f"={l.promocao}"] if l.promocao else []) \
                + ([f"desc({','.join(f'{d[0]}{d[1]}' for d in l.descobertas)})"] if l.descobertas else []) \
                + ([f"atk({','.join(f'{a[0]}{a[1]}' for a in l.ataques)})"] if l.ataques else [])
            partes.append(" ".join(p))
        return " | ".join([f"K{self.rei}", *partes])

    def completo(self) -> str:
        partes = []
        for l in self.lances:
            p = [l.peca, f"{l.origem}-{l.destino}"] + ([f"x{l.captura}"] if l.captura else []) + ([l.xeque] if l.xeque else []) \
                + ([f"={l.promocao}"] if l.promocao else []) \
                + ([f"desc({','.join(f'{d[0]}{d[1]}<{d[2]}' for d in l.descobertas)})"] if l.descobertas else []) \
                + ([f"atk({','.join(f'{a[0]}{a[1]}' for a in l.ataques)})"] if l.ataques else [])
            partes.append(" ".join(p))
        return " | ".join([f"K{self.rei}", *partes])

    def espelhada(self) -> "Assinatura":
        """O mesmo golpe na outra ala: colunas trocadas (a<->h). Ataques e descobertas são
        simétricos, então basta trocar as casas no texto."""
        return Assinatura(_esp(self.rei), tuple(
            replace(l, origem=_esp(l.origem), destino=_esp(l.destino),
                    descobertas=tuple((p, _esp(c), _esp(q)) for p, c, q in l.descobertas),
                    ataques=tuple((p, _esp(c)) for p, c in l.ataques))
            for l in self.lances))

    def hashes(self) -> dict[str, int]:
        return {"esqueleto": hash64(self.esqueleto()), "destinos": hash64(self.destinos()),
                "destinos_esp": hash64(self.espelhada().destinos()), "completo": hash64(self.completo())}


def hash64(texto: str) -> int:
    """8 bytes do BLAKE2b como inteiro com sinal: cabe num INTEGER do SQLite e indexa bem."""
    return int.from_bytes(hashlib.blake2b(texto.encode("utf-8"), digest_size=8).digest(), "big", signed=True)


def zona(casa: int) -> str:
    coluna = chess.square_file(casa)
    ala = "dama" if coluna < 3 else "centro" if coluna < 5 else "rei"
    return f"{ala}-{'fundo' if chess.square_rank(casa) >= 6 else 'exposto'}"


def _esp(casa: str) -> str:
    sq = chess.parse_square(casa)
    return chess.square_name(chess.square(7 - chess.square_file(sq), chess.square_rank(sq)))


def _alvos(board: chess.Board, cor_alvo: chess.Color) -> list[int]:
    """Casas das peças de `cor_alvo` que contam como alvo: nem rei nem peões (spec §3.3)."""
    return [sq for sq, p in board.piece_map().items()
            if p.color == cor_alvo and p.piece_type not in (chess.KING, chess.PAWN)]


def _atacadas_por_outras(board: chess.Board, quem: chess.Color, exceto: int) -> set[int]:
    """Peças adversárias atacadas por alguma peça de `quem` que não seja a da casa `exceto`."""
    return {sq for sq in _alvos(board, not quem) if any(a != exceto for a in board.attackers(quem, sq))}


def _mais_valiosas(board: chess.Board, casas: set[int]) -> list[int]:
    return sorted(casas, key=lambda sq: (-VALOR[board.piece_type_at(sq)], chess.square_name(sq)))[:LIMITE_ALVOS]


def _anotar_lance(board: chess.Board, mv: chess.Move) -> Lance:
    quem = board.turn
    peca = board.piece_type_at(mv.from_square)
    if peca is None or not board.is_legal(mv):
        raise ValueError(f"lance ilegal: {mv.uci()} em {board.fen()}")
    captura = "P" if board.is_en_passant(mv) else (LETRA[t] if (t := board.piece_type_at(mv.to_square)) else None)
    antes_outras = _atacadas_por_outras(board, quem, mv.from_square)
    antes_propria = set(board.attacks(mv.from_square))
    board.push(mv)
    xeque = ""
    if board.is_check():
        checkers = board.checkers()
        xeque = "++" if len(checkers) >= 2 else "+" if mv.to_square in checkers else "d+"
    if board.is_checkmate():
        # a partida acabou: o que a peça ataca ou destapa não descreve o golpe
        return Lance(LETRA[peca], chess.square_name(mv.from_square), chess.square_name(mv.to_square), captura, "#",
                     LETRA[mv.promotion] if mv.promotion else None, (), ())
    depois_outras = _atacadas_por_outras(board, quem, mv.to_square)
    descobertas = []
    for sq in _mais_valiosas(board, depois_outras - antes_outras):
        por = min(a for a in board.attackers(quem, sq) if a != mv.to_square)
        descobertas.append((LETRA[board.piece_type_at(sq)], chess.square_name(sq), chess.square_name(por)))
    novas = {sq for sq in _alvos(board, not quem) if sq in board.attacks(mv.to_square) and sq not in antes_propria}
    ataques = [(LETRA[board.piece_type_at(sq)], chess.square_name(sq)) for sq in _mais_valiosas(board, novas)]
    return Lance(LETRA[peca], chess.square_name(mv.from_square), chess.square_name(mv.to_square), captura, xeque,
                 LETRA[mv.promotion] if mv.promotion else None, tuple(descobertas), tuple(ataques))


def anotar(board: chess.Board, lances_uci: Sequence[str], max_lances: int = MAX_LANCES) -> Assinatura:
    """Descreve os lances de quem soluciona (índices pares) no tabuleiro dado, sem normalizar."""
    board = board.copy()
    if not board.is_valid():
        raise ValueError(f"posição impossível: {board.fen()}")
    quem = board.turn
    rei = chess.square_name(board.king(not quem))
    lances: list[Lance] = []
    for i, uci in enumerate(lances_uci):
        try:
            mv = chess.Move.from_uci(uci)
        except ValueError as exc:
            raise ValueError(f"lance inválido: {uci}") from exc
        if i % 2 == 0:
            if len(lances) >= max_lances:
                break
            lances.append(_anotar_lance(board, mv))
        else:
            if not board.is_legal(mv):
                raise ValueError(f"lance ilegal: {uci} em {board.fen()}")
            board.push(mv)
    return Assinatura(rei, tuple(lances))


def assinar(fen: str, lances_uci: Sequence[str], max_lances: int = MAX_LANCES) -> Assinatura:
    """Assinatura normalizada: quem soluciona vira as brancas (espelho vertical com troca de cores)."""
    try:
        board = chess.Board(fen)
    except ValueError as exc:
        raise ValueError(f"FEN inválida: {fen}") from exc
    if board.turn == chess.BLACK:
        board = board.mirror()
        lances_uci = [_uci_espelho_vertical(u) for u in lances_uci]
    return anotar(board, lances_uci, max_lances)


def _uci_espelho_vertical(uci: str) -> str:
    mv = chess.Move.from_uci(uci)
    return chess.Move(chess.square_mirror(mv.from_square), chess.square_mirror(mv.to_square), mv.promotion).uci()
```

- [ ] **Step 4: rodar até passar**

Run: `cd backend && uv run pytest -q tests/test_golpes_assinatura.py`
Expected: todos passam. Se um texto esperado não bater por detalhe de formato (ordem de `desc`/`atk`), ajuste o **teste** só se a implementação estiver de acordo com a tabela de §3.3 da spec; caso contrário, corrija a implementação. Confira à mão com python-chess as posições dos testes de xeque descoberto/duplo antes de mudar expectativas.

- [ ] **Step 5: commit**

```
feat(golpes): assinatura do golpe a partir da solução (níveis, hashes, espelho)
```

---

### Task 2: modelos e migração

**Files:**
- Modify: `backend/chess_trainer/core/models.py` (após `LichessPuzzleTheme`, ~linha 248; `Puzzle` ~linha 78-131), `backend/chess_trainer/core/db.py:213-218`
- Test: `backend/tests/test_migration.py`, `backend/tests/test_golpes_models.py`

**Interfaces:**
- Produces:
  - `class LichessPuzzleSignature(Base)` — `__tablename__ = "lichess_puzzle_signatures"`; `puzzle_id: str` PK FK `lichess_puzzles.id` (ondelete CASCADE); `versao: int`; `esqueleto, destinos, destinos_esp, completo: int` (BigInteger); `texto_completo: str`; `zona_rei: str`; `n_lances: int`. Índices: `destinos`, `destinos_esp`, `(esqueleto, zona_rei)`.
  - `class PuzzleSignature(Base)` — `__tablename__ = "puzzle_signatures"`, mesmas colunas, `puzzle_id` FK `puzzles.id` (ondelete CASCADE).
  - `class GolpeLabel(Base)` — `__tablename__ = "golpe_labels"`; `id` (uuid), `anchor_origem: str` (`own|lichess`), `anchor_id: str`, `candidate_id: str` (id do Lichess), `tier_na_hora: str`, `versao_assinatura: int`, `label: str` (`mesmo|parecido|nada`), `created_at`.
  - `Puzzle.sibling_of: str | None` (FK `puzzles.id`, índice).

- [ ] **Step 1: testes que falham**

```python
# backend/tests/test_golpes_models.py
from chess_trainer.core.models import GolpeLabel, LichessPuzzle, LichessPuzzleSignature, Puzzle, PuzzleSignature
from tests.factories import make_puzzle

FEN = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"


def test_tabelas_de_assinatura_e_vinculo_de_irmao(db_session):
    db_session.add(LichessPuzzle(id="abcde", fen=FEN, moves="a2a3 h5f7", rating=1200, rating_deviation=50,
                                 popularity=90, nb_plays=500, themes="mate", opening_tags=""))
    db_session.add(LichessPuzzleSignature(puzzle_id="abcde", versao=1, esqueleto=1, destinos=2, destinos_esp=3, completo=4,
                                          texto_completo="Ke8 | Q xP f7 #", zona_rei="centro-fundo", n_lances=1))
    origem = make_puzzle(db_session, fen=FEN)
    irmao = make_puzzle(db_session, fen=FEN.replace("w", "b"), side="black")
    irmao.sibling_of = origem.id
    db_session.add(PuzzleSignature(puzzle_id=origem.id, versao=1, esqueleto=1, destinos=2, destinos_esp=3, completo=4,
                                   texto_completo="x", zona_rei="centro-fundo", n_lances=1))
    db_session.add(GolpeLabel(anchor_origem="own", anchor_id=origem.id, candidate_id="abcde", tier_na_hora="mesmo",
                              versao_assinatura=1, label="mesmo"))
    db_session.commit()
    assert db_session.get(LichessPuzzleSignature, "abcde").destinos == 2
    assert db_session.get(Puzzle, irmao.id).sibling_of == origem.id
    assert db_session.query(GolpeLabel).one().label == "mesmo"
```

Em `backend/tests/test_migration.py`, acrescente ao teste existente que constrói o banco antigo (procure `OLD_SCHEMA` e o `assert` final) uma verificação de que, depois de `init_db`, `PRAGMA table_info(puzzles)` contém `sibling_of` e que `lichess_puzzle_signatures`, `puzzle_signatures` e `golpe_labels` existem em `sqlite_master`:

```python
def test_migracao_cria_golpes(tmp_path):
    caminho = tmp_path / "old.db"
    con = sqlite3.connect(caminho); con.executescript(OLD_SCHEMA); con.close()
    init_db(make_engine(str(caminho)))
    con = sqlite3.connect(caminho)
    colunas = {r[1] for r in con.execute("PRAGMA table_info(puzzles)")}
    tabelas = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    con.close()
    assert "sibling_of" in colunas
    assert {"lichess_puzzle_signatures", "puzzle_signatures", "golpe_labels"} <= tabelas
```

- [ ] **Step 2: rodar e ver falhar**

Run: `cd backend && uv run pytest -q tests/test_golpes_models.py tests/test_migration.py`

- [ ] **Step 3: implementar**

Em `models.py`, dentro de `Puzzle` (junto das colunas `srs_*`):

```python
    # exercício de origem quando este puzzle entrou pelo bloco "Repetir o golpe" (spec golpes §6)
    sibling_of: Mapped[str | None] = mapped_column(String(36), ForeignKey("puzzles.id"), default=None, index=True)
```

Depois de `LichessPuzzleTheme`:

```python
class _ColunasDeAssinatura:
    versao: Mapped[int] = mapped_column(Integer)
    esqueleto: Mapped[int] = mapped_column(BigInteger)
    destinos: Mapped[int] = mapped_column(BigInteger)
    destinos_esp: Mapped[int] = mapped_column(BigInteger)
    completo: Mapped[int] = mapped_column(BigInteger)
    texto_completo: Mapped[str] = mapped_column(Text)
    zona_rei: Mapped[str] = mapped_column(String(16))
    n_lances: Mapped[int] = mapped_column(Integer)


class LichessPuzzleSignature(_ColunasDeAssinatura, Base):
    """Assinatura do golpe de cada puzzle do Lichess (spec golpes §4.1)."""
    __tablename__ = "lichess_puzzle_signatures"
    __table_args__ = (Index("ix_lps_destinos", "destinos"), Index("ix_lps_destinos_esp", "destinos_esp"),
                      Index("ix_lps_esqueleto_zona", "esqueleto", "zona_rei"))
    puzzle_id: Mapped[str] = mapped_column(ForeignKey("lichess_puzzles.id", ondelete="CASCADE"), primary_key=True)


class PuzzleSignature(_ColunasDeAssinatura, Base):
    """Assinatura do golpe dos exercícios do usuário."""
    __tablename__ = "puzzle_signatures"
    __table_args__ = (Index("ix_ps_destinos", "destinos"),)
    puzzle_id: Mapped[str] = mapped_column(ForeignKey("puzzles.id", ondelete="CASCADE"), primary_key=True)


class GolpeLabel(Base):
    """Julgamento humano na tela de rotulagem: o conjunto de ouro (spec golpes §8)."""
    __tablename__ = "golpe_labels"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    anchor_origem: Mapped[str] = mapped_column(String(8))  # own | lichess
    anchor_id: Mapped[str] = mapped_column(String(36), index=True)
    candidate_id: Mapped[str] = mapped_column(String(8))
    tier_na_hora: Mapped[str] = mapped_column(String(16))
    versao_assinatura: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(8))  # mesmo | parecido | nada
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
```

(`BigInteger` e `Index` vêm de `sqlalchemy`; confira os imports no topo do arquivo.)

Em `db.py`, junto de `_NEW_COACH_EXPLANATION_COLUMNS`:

```python
_NEW_GOLPES_PUZZLE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("sibling_of", "VARCHAR(36)"),
)
```

e no bloco `with engine.begin() as conn:` (linha ~213), depois de `_acrescenta_colunas(conn, "coach_explanations", ...)`:

```python
    _acrescenta_colunas(conn, "puzzles", _NEW_GOLPES_PUZZLE_COLUMNS)
    conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_puzzles_sibling_of ON puzzles (sibling_of)")
```

- [ ] **Step 4: rodar tudo**

Run: `cd backend && uv run pytest -q`
Expected: tudo passa (684 + novos).

- [ ] **Step 5: commit**

```
feat(golpes): tabelas de assinatura, rótulos do conjunto de ouro e vínculo sibling_of
```

---

### Task 3: serviço de assinatura e ganchos na criação de exercícios

**Files:**
- Create: `backend/chess_trainer/core/golpes/service.py`
- Modify: `backend/chess_trainer/core/puzzles/service.py:113-134` (`persist_draft`), `backend/chess_trainer/core/studies/service.py:281-323` (`_upsert_puzzle`)
- Test: `backend/tests/test_golpes_service.py`

**Interfaces:**
- Consumes: `assinar`, `Assinatura`, `VERSAO_ASSINATURA` (Task 1); modelos (Task 2).
- Produces:
  - `assinar_lichess(row: LichessPuzzle) -> Assinatura | None` — `None` quando a linha é inválida (menos de dois lances, lance ilegal).
  - `assinar_proprio(puzzle: Puzzle) -> Assinatura | None`.
  - `linha_de_assinatura(a: Assinatura, cls, puzzle_id: str)` — monta a linha ORM (`LichessPuzzleSignature` ou `PuzzleSignature`).
  - `garantir_assinatura(db: Session, puzzle: Puzzle) -> PuzzleSignature | None` — grava/atualiza se faltar ou a versão for antiga; devolve a linha.
  - `assinatura_de(db, origem: str, id: str) -> tuple[Assinatura, str, list[str]] | None` — devolve `(assinatura, fen_start, lances_uci)` de um exercício próprio (`own`) ou de um puzzle do Lichess (`lichess`), calculando na hora se preciso; `None` se não existe ou é inválido.

- [ ] **Step 1: testes que falham**

```python
# backend/tests/test_golpes_service.py
import json

from chess_trainer.core.golpes.assinatura import VERSAO_ASSINATURA
from chess_trainer.core.golpes.service import assinar_lichess, assinar_proprio, assinatura_de, garantir_assinatura
from chess_trainer.core.models import LichessPuzzle, PuzzleSignature
from tests.factories import make_puzzle

# Puzzle do Lichess: `fen` é a posição ANTES do lance de preparação (moves[0]); quem soluciona joga depois dele.
# Aqui: pretas a jogar, o preparo é 8...Qb6xd4?? (toma o cavalo achando o peão de graça) e as brancas
# solucionam com 9.Bb5+ descobrindo a dama de d1 contra d4 — a armadilha da francesa.
FEN_FRANCESA_ANTES = "r1b1kbnr/pp3ppp/1q2p3/3pP3/3N4/3B4/PP3PPP/RNBQK2R b KQkq - 0 8"
MOVES_FRANCESA = "b6d4 d3b5 e8e7 d1d4"
# Mate do pastor: pretas a jogar, preparo 4...Nf6?? e Qxf7#
FEN_PASTOR_ANTES = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 4 4"
MOVES_PASTOR = "g8f6 h5f7"


def lichess(pid: str, fen: str, moves: str, rating: int = 1500, popularity: int = 90):
    return LichessPuzzle(id=pid, fen=fen, moves=moves, rating=rating, rating_deviation=50, popularity=popularity,
                         nb_plays=500, themes="fork", opening_tags="")


def pastor(pid: str, rating: int = 800, popularity: int = 90):
    return lichess(pid, FEN_PASTOR_ANTES, MOVES_PASTOR, rating, popularity)


def test_assinar_lichess_usa_a_posicao_depois_do_preparo(db_session):
    a = assinar_lichess(lichess("frnc1", FEN_FRANCESA_ANTES, MOVES_FRANCESA))
    assert a is not None and a.destinos() == "Ke8 | B b5 + desc(Qd4) | Q xQ d4"
    assert assinar_lichess(lichess("curto", FEN_PASTOR_ANTES, "g8f6")) is None  # menos de dois lances
    assert assinar_lichess(lichess("ilegal", FEN_PASTOR_ANTES, "g8f6 a1a8")) is None  # lance ilegal


def test_garantir_assinatura_grava_e_refaz_por_versao(db_session):
    sol = {"moves": [{"uci": "h5f7", "by": "solver", "alternatives": []}], "explanation_pv": []}
    p = make_puzzle(db_session, fen="r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4", solution=sol)
    s = garantir_assinatura(db_session, p)
    assert s is not None and s.versao == VERSAO_ASSINATURA and s.texto_completo == "Ke8 | Q h5-f7 xP #"
    s.versao = 0
    db_session.commit()
    s2 = garantir_assinatura(db_session, p)
    assert s2.versao == VERSAO_ASSINATURA and db_session.query(PuzzleSignature).count() == 1
    assert assinar_proprio(p).destinos() == "Ke8 | Q xP f7 #"


def test_assinatura_de_own_e_lichess(db_session):
    sol = {"moves": [{"uci": "h5f7", "by": "solver", "alternatives": []}], "explanation_pv": []}
    p = make_puzzle(db_session, fen="r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4", solution=sol)
    a, fen, lances = assinatura_de(db_session, "own", p.id)
    assert a.destinos() == "Ke8 | Q xP f7 #" and fen == p.fen_start and lances == ["h5f7"]
    db_session.add(lichess("frnc1", FEN_FRANCESA_ANTES, MOVES_FRANCESA)); db_session.commit()
    a2, fen2, lances2 = assinatura_de(db_session, "lichess", "frnc1")
    assert a2.destinos().startswith("Ke8 | B b5 +") and lances2 == ["d3b5", "e8e7", "d1d4"] and fen2.split()[1] == "w"
    assert assinatura_de(db_session, "lichess", "nao-existe") is None
```

- [ ] **Step 2: rodar e ver falhar**

Run: `cd backend && uv run pytest -q tests/test_golpes_service.py`

- [ ] **Step 3: implementar**

```python
# backend/chess_trainer/core/golpes/service.py
"""Assinaturas no banco: calcular para o Lichess e para os exercícios do usuário (spec golpes §4)."""
from __future__ import annotations

import json

import chess
from sqlalchemy.orm import Session

from chess_trainer.core.golpes.assinatura import VERSAO_ASSINATURA, Assinatura, assinar
from chess_trainer.core.models import LichessPuzzle, LichessPuzzleSignature, Puzzle, PuzzleSignature


def _lances_lichess(row: LichessPuzzle) -> tuple[str, list[str]] | None:
    """(fen da posição do puzzle, lances da solução). `moves[0]` é o lance de preparação do adversário."""
    ucis = row.moves.split()
    if len(ucis) < 2:
        return None
    try:
        board = chess.Board(row.fen)
        board.push(chess.Move.from_uci(ucis[0]))
    except ValueError:
        return None
    return board.fen(), ucis[1:]


def assinar_lichess(row: LichessPuzzle) -> Assinatura | None:
    par = _lances_lichess(row)
    if par is None:
        return None
    try:
        return assinar(par[0], par[1])
    except ValueError:
        return None


def _lances_proprio(puzzle: Puzzle) -> list[str]:
    return [m["uci"] for m in json.loads(puzzle.solution).get("moves", [])]


def assinar_proprio(puzzle: Puzzle) -> Assinatura | None:
    try:
        return assinar(puzzle.fen_start, _lances_proprio(puzzle))
    except ValueError:
        return None


def linha_de_assinatura(a: Assinatura, cls, puzzle_id: str):
    h = a.hashes()
    return cls(puzzle_id=puzzle_id, versao=VERSAO_ASSINATURA, esqueleto=h["esqueleto"], destinos=h["destinos"],
               destinos_esp=h["destinos_esp"], completo=h["completo"], texto_completo=a.completo(),
               zona_rei=a.zona_rei, n_lances=len(a.lances))


def garantir_assinatura(db: Session, puzzle: Puzzle) -> PuzzleSignature | None:
    """Grava a assinatura do exercício se faltar ou estiver com versão antiga."""
    atual = db.get(PuzzleSignature, puzzle.id)
    if atual is not None and atual.versao == VERSAO_ASSINATURA:
        return atual
    a = assinar_proprio(puzzle)
    if a is None:
        return None
    if atual is not None:
        db.delete(atual)
        db.flush()
    linha = linha_de_assinatura(a, PuzzleSignature, puzzle.id)
    db.add(linha)
    db.commit()
    return linha


def assinatura_de(db: Session, origem: str, id: str) -> tuple[Assinatura, str, list[str]] | None:
    """Assinatura, posição e lances de um exercício próprio (`own`) ou de um puzzle do Lichess."""
    if origem == "own":
        puzzle = db.get(Puzzle, id)
        if puzzle is None:
            return None
        a = assinar_proprio(puzzle)
        return None if a is None else (a, puzzle.fen_start, _lances_proprio(puzzle))
    if origem == "lichess":
        row = db.get(LichessPuzzle, id)
        if row is None:
            return None
        par = _lances_lichess(row)
        if par is None:
            return None
        try:
            return assinar(par[0], par[1]), par[0], par[1]
        except ValueError:
            return None
    return None
```

Ganchos (uma linha cada, depois do `commit` que cria o `Puzzle`):

- `backend/chess_trainer/core/puzzles/service.py` em `persist_draft`, depois de gravar o puzzle: `garantir_assinatura(db, puzzle)` (import `from chess_trainer.core.golpes.service import garantir_assinatura`).
- `backend/chess_trainer/core/studies/service.py` em `_upsert_puzzle`, tanto no caminho de criação (~linha 309) quanto no de atualização (~293-307), depois do `commit`/`flush`: `garantir_assinatura(db, puzzle)`. No caminho de atualização a solução pode ter mudado: apague a `PuzzleSignature` existente antes (`db.query(PuzzleSignature).filter_by(puzzle_id=puzzle.id).delete()`) e chame `garantir_assinatura`.

Acrescente um teste ao final de `test_golpes_service.py` que passa por `persist_draft` (veja `backend/tests/test_generator_punish.py` para montar um `PuzzleDraft` e uma `Position`; copie a forma que aquele arquivo usa) e confirma `db_session.get(PuzzleSignature, puzzle.id) is not None`.

- [ ] **Step 4: rodar tudo**

Run: `cd backend && uv run pytest -q`

- [ ] **Step 5: commit**

```
feat(golpes): assinatura calculada na criação dos exercícios e sob demanda para o Lichess
```

---

### Task 4: tarefa "Preparar golpes", cobertura, status, configurações

**Files:**
- Modify: `backend/chess_trainer/core/golpes/service.py`, `backend/chess_trainer/config.py:12-48`, `backend/chess_trainer/api/schemas.py` (`SettingsOut`/`SettingsIn`, novos `GolpesStatusOut`), `backend/chess_trainer/api/app.py:155-163`
- Create: `backend/chess_trainer/api/routes/golpes.py`
- Test: `backend/tests/test_golpes_service.py`, `backend/tests/test_api_golpes.py`

**Interfaces:**
- Produces:
  - `AppSettings.golpes_enabled: bool = True`, `AppSettings.golpes_bloco: int = 5`.
  - `preparar(db: Session, progress: ProgressFn, should_stop: Callable[[], bool] | None = None, lote: int = 5000) -> int` — assina o que falta ou está com versão antiga; devolve quantos processou; no fim (não cancelado) grava `cobertura(db)` em `settings["golpes_cobertura"]` e `settings["golpes_assinados"]`.
  - `cobertura(db: Session) -> dict[str, dict[str, int]]` — por nível (`esqueleto`, `destinos`, `completo`): `{"ge5": n, "ge2": n, "sozinhos": n}` contados em puzzles.
  - `golpes_ligado(db)` dependência FastAPI: 404 quando `golpes_enabled` é falso.
  - Rotas: `GET /api/golpes/status` → `GolpesStatusOut{enabled, versao, assinados, total, cobertura, rotulagem}`; `POST /api/golpes/preparar` → 202 `{"queued": true, "job": "golpes_preparar"}` (409 se já há tarefa).

- [ ] **Step 1: testes que falham**

Acrescente a `test_golpes_service.py`:

```python
from chess_trainer.core.golpes.service import cobertura, preparar
from chess_trainer.core.models import LichessPuzzleSignature
from chess_trainer.config import get_setting


def test_preparar_assina_em_lotes_e_grava_cobertura(db_session):
    for i in range(7):
        db_session.add(pastor(f"p{i}"))
    db_session.add(lichess("ruim", FEN_PASTOR_ANTES, "g8f6"))  # inválido: fica sem assinatura, sem derrubar a tarefa
    db_session.commit()
    chamadas = []
    n = preparar(db_session, lambda *a: chamadas.append(a), lote=3)
    assert n == 8 and db_session.query(LichessPuzzleSignature).count() == 7
    assert chamadas[-1][0] == "golpes_preparar" and chamadas[-1][1] == chamadas[-1][2]
    cob = get_setting(db_session, "golpes_cobertura", None)
    assert cob["destinos"] == {"ge5": 7, "ge2": 7, "sozinhos": 0} and get_setting(db_session, "golpes_assinados", 0) == 7
    # segunda rodada: nada a fazer
    assert preparar(db_session, lambda *a: None) == 0
    # versão antiga: refaz só ela
    s = db_session.get(LichessPuzzleSignature, "p0"); s.versao = 0; db_session.commit()
    assert preparar(db_session, lambda *a: None) == 1


def test_preparar_para_no_cancelamento(db_session):
    for i in range(6):
        db_session.add(pastor(f"c{i}"))
    db_session.commit()
    vezes = iter([False, True, True])
    n = preparar(db_session, lambda *a: None, should_stop=lambda: next(vezes), lote=2)
    assert n == 2 and db_session.query(LichessPuzzleSignature).count() == 2
    assert get_setting(db_session, "golpes_cobertura", None) is None  # cancelado: cobertura não é gravada


def test_cobertura_conta_grupos_por_nivel(db_session):
    for i in range(5):
        db_session.add(pastor(f"g{i}"))
    db_session.add(lichess("solo", FEN_FRANCESA_ANTES, MOVES_FRANCESA))
    db_session.commit()
    preparar(db_session, lambda *a: None)
    cob = cobertura(db_session)
    assert cob["destinos"] == {"ge5": 5, "ge2": 5, "sozinhos": 1}
```

Novo `backend/tests/test_api_golpes.py`:

```python
import pytest
from fastapi.testclient import TestClient

from chess_trainer.api.app import create_app
from chess_trainer.core.models import LichessPuzzle
from tests.fakes import FakeEngine, first_legal_default

FEN_PASTOR_ANTES = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 4 4"


def pastor(pid, rating=800):
    return LichessPuzzle(id=pid, fen=FEN_PASTOR_ANTES, moves="g8f6 h5f7", rating=rating, rating_deviation=50,
                         popularity=90, nb_plays=500, themes="mateIn1", opening_tags="")


@pytest.fixture
def client():
    app = create_app(db_path=":memory:", engine_factory=lambda s: FakeEngine(default=first_legal_default(0)))
    with TestClient(app) as c:
        db = app.state.session_factory()
        for i in range(6):
            db.add(pastor(f"p{i}", 700 + 100 * i))
        db.commit(); db.close()
        yield c


def test_status_e_preparar(client):
    s = client.get("/api/golpes/status").json()
    assert s["enabled"] is True and s["versao"] == 1 and s["assinados"] == 0 and s["cobertura"] is None and s["rotulagem"] is False
    assert client.post("/api/golpes/preparar").status_code == 202
    client.app.state.jobs.wait()
    assert client.get("/api/status").json()["job"]["state"] == "idle"
    s = client.get("/api/golpes/status").json()
    assert s["assinados"] == 6 and s["cobertura"]["destinos"]["ge5"] == 6


def test_desligado_da_404(client):
    assert client.put("/api/settings", json={"golpes_enabled": False}).status_code == 200
    assert client.post("/api/golpes/preparar").status_code == 404
    assert client.get("/api/golpes/status").json()["enabled"] is False


def test_settings_validam_o_bloco(client):
    assert client.put("/api/settings", json={"golpes_bloco": 2}).status_code == 422
    assert client.put("/api/settings", json={"golpes_bloco": 7}).status_code == 200
    assert client.get("/api/settings").json()["golpes_bloco"] == 7
```

- [ ] **Step 2: rodar e ver falhar**

Run: `cd backend && uv run pytest -q tests/test_golpes_service.py tests/test_api_golpes.py`

- [ ] **Step 3: implementar**

`config.py`, em `AppSettings`:

```python
    # golpes: cartão "Repetir o golpe" e tamanho do bloco de irmãos
    golpes_enabled: bool = True
    golpes_bloco: int = 5
```

`schemas.py`: em `SettingsOut` acrescente `golpes_enabled: bool` e `golpes_bloco: int`; em `SettingsIn` acrescente `golpes_enabled: bool | None = None` e `golpes_bloco: int | None = Field(None, ge=3, le=10)`. Novo esquema:

```python
class GolpesStatusOut(BaseModel):
    enabled: bool
    versao: int
    assinados: int
    total: int
    cobertura: dict[str, dict[str, int]] | None
    rotulagem: bool
```

`service.py`, acrescentar:

```python
from typing import Callable

from sqlalchemy import func, select

from chess_trainer.config import get_setting, set_setting

ProgressFn = Callable[[str, int, int, str], None]
NOME_TAREFA = "golpes_preparar"


def _pendentes(db: Session):
    """Ids do Lichess sem assinatura ou com versão antiga."""
    return (select(LichessPuzzle.id).outerjoin(LichessPuzzleSignature, LichessPuzzleSignature.puzzle_id == LichessPuzzle.id)
            .where((LichessPuzzleSignature.puzzle_id.is_(None)) | (LichessPuzzleSignature.versao < VERSAO_ASSINATURA))
            .order_by(LichessPuzzle.id))


def preparar(db: Session, progress: ProgressFn, should_stop: Callable[[], bool] | None = None, lote: int = 5000) -> int:
    """Assina o que falta, em lotes, com progresso e cancelamento. Percorre os pendentes por um
    cursor de id: puzzle inválido do Lichess não ganha linha, e sem o cursor ele voltaria no lote
    seguinte para sempre. Devolve quantos puzzles foram processados (válidos ou não)."""
    total = db.scalar(select(func.count()).select_from(_pendentes(db).subquery())) or 0
    progress(NOME_TAREFA, 0, total, "contando")
    feitos = 0
    ultimo = ""
    while True:
        if should_stop is not None and should_stop():
            progress(NOME_TAREFA, feitos, total, "cancelado")
            return feitos
        ids = list(db.scalars(_pendentes(db).where(LichessPuzzle.id > ultimo).limit(lote)))
        if not ids:
            break
        ultimo = ids[-1]
        rows = db.scalars(select(LichessPuzzle).where(LichessPuzzle.id.in_(ids))).all()
        for s in db.scalars(select(LichessPuzzleSignature).where(LichessPuzzleSignature.puzzle_id.in_(ids))):
            db.delete(s)  # versão antiga: sai antes de entrar a nova
        db.flush()
        for row in rows:
            a = assinar_lichess(row)
            if a is not None:
                db.add(linha_de_assinatura(a, LichessPuzzleSignature, row.id))
        db.commit()
        feitos += len(ids)
        progress(NOME_TAREFA, feitos, total, f"{feitos}/{total} puzzles")
    set_setting(db, "golpes_cobertura", cobertura(db))
    set_setting(db, "golpes_assinados", db.scalar(select(func.count()).select_from(LichessPuzzleSignature)) or 0)
    progress(NOME_TAREFA, total, total, "concluído")
    return feitos
```

```python
def cobertura(db: Session) -> dict[str, dict[str, int]]:
    """Por nível: quantos puzzles têm grupo ≥ 5, ≥ 2 e ficam sozinhos (spec §4.2)."""
    out = {}
    for nivel in ("esqueleto", "destinos", "completo"):
        col = getattr(LichessPuzzleSignature, nivel)
        grupos = select(func.count().label("c")).group_by(col).subquery()
        ge5, ge2, solos = db.execute(select(
            func.coalesce(func.sum(func.iif(grupos.c.c >= 5, grupos.c.c, 0)), 0),
            func.coalesce(func.sum(func.iif(grupos.c.c >= 2, grupos.c.c, 0)), 0),
            func.coalesce(func.sum(func.iif(grupos.c.c == 1, 1, 0)), 0),
        )).one()
        out[nivel] = {"ge5": int(ge5), "ge2": int(ge2), "sozinhos": int(solos)}
    return out
```

`api/routes/golpes.py`:

```python
"""Golpes: status, tarefa de preparo (e, nas tarefas seguintes, irmãos, imagem e rotulagem)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chess_trainer.api.deps import get_db
from chess_trainer.api.schemas import GolpesStatusOut
from chess_trainer.config import get_setting, load_settings
from chess_trainer.core.golpes.assinatura import VERSAO_ASSINATURA
from chess_trainer.core.golpes.service import NOME_TAREFA, preparar
from chess_trainer.core.models import LichessPuzzle

router = APIRouter(prefix="/api/golpes")


def golpes_ligado(db: Session = Depends(get_db)) -> None:
    if not load_settings(db).golpes_enabled:
        raise HTTPException(404, "golpes desligados em Configurações")


@router.get("/status", response_model=GolpesStatusOut)
def golpes_status(request: Request, db: Session = Depends(get_db)):
    s = load_settings(db)
    total = int(get_setting(db, "lichess_total", 0) or 0)
    if not total:
        total = db.scalar(select(func.count()).select_from(LichessPuzzle)) or 0
    return GolpesStatusOut(enabled=s.golpes_enabled, versao=VERSAO_ASSINATURA,
                           assinados=int(get_setting(db, "golpes_assinados", 0) or 0), total=total,
                           cobertura=get_setting(db, "golpes_cobertura", None),
                           rotulagem=bool(getattr(request.app.state, "rotulagem_enabled", False)))


@router.post("/preparar", status_code=202, dependencies=[Depends(golpes_ligado)])
def golpes_preparar(request: Request):
    app = request.app

    def job(progress):
        db = app.state.session_factory()
        try:
            preparar(db, progress, should_stop=app.state.jobs.should_stop)
        finally:
            db.close()

    if not app.state.jobs.submit(NOME_TAREFA, job):
        raise HTTPException(409, "já existe uma tarefa em andamento")
    return {"queued": True, "job": NOME_TAREFA}
```

(Se existir uma chave de contagem do Lichess em `settings` com outro nome — procure `lichess_theme_counts`/`tactics_status` em `core/tactics/service.py:157` — use a mesma fonte que `tactics_status` usa para o total, para não fazer `COUNT(*)` no milhão a cada pedido.)

`app.py`: `from chess_trainer.api.routes import golpes` e `app.include_router(golpes.router)` junto dos outros; e, ao lado de `coach_enabled`: `app.state.rotulagem_enabled = os.environ.get("CHESS_TRAINER_ROTULAGEM") == "1"` (com parâmetro opcional `rotulagem_enabled: bool | None = None` em `create_app`, mesmo padrão do `coach_enabled`).

- [ ] **Step 4: rodar tudo**

Run: `cd backend && uv run pytest -q`

- [ ] **Step 5: commit**

```
feat(golpes): tarefa "Preparar golpes" com cobertura, status e configurações
```

---

### Task 5: busca de irmãos e rota

**Files:**
- Modify: `backend/chess_trainer/core/golpes/service.py`, `backend/chess_trainer/api/routes/golpes.py`, `backend/chess_trainer/api/schemas.py`
- Test: `backend/tests/test_golpes_service.py`, `backend/tests/test_api_golpes.py`

**Interfaces:**
- Consumes: `to_tactic(row) -> Tactic` (`core/tactics/convert.py:34`), `_seen_ids(db, now, exclude)` (`core/tactics/service.py:34`), `AppSettings.tactics_rating/tactics_window`.
- Produces:
  - `@dataclass class Irmao: row: LichessPuzzle; tier: str` (`tier ∈ {"mesmo", "espelho", "esqueleto"}`).
  - `irmaos(db, a: Assinatura, *, rating_lo: int, rating_hi: int, excluir: set[str], k: int = 5, min_popularity: int = 50, min_plays: int = 50) -> list[Irmao]`.
  - `espalhar(itens: list, k: int) -> list` — k itens espalhados ao longo de uma lista já ordenada.
  - `GET /api/golpes/{origem}/{id}/irmaos?k=` → `IrmaosOut{assinatura: str, itens: list[IrmaoOut{tier: str, tactic: TacticOut}]}`; 404 quando desligado, quando o puzzle não existe/não tem assinatura, e `itens: []` quando não há irmãos.

- [ ] **Step 1: testes que falham**

`test_golpes_service.py`:

```python
from chess_trainer.core.golpes.service import Irmao, espalhar, irmaos
from chess_trainer.core.golpes.assinatura import assinar

FEN_PASTOR_START = "r1bqkbnr/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 5 5"


def test_espalhar_pega_do_facil_ao_dificil():
    assert espalhar(list(range(10)), 5) == [0, 2, 4, 7, 9]
    assert espalhar([1, 2, 3], 5) == [1, 2, 3]
    assert espalhar([], 3) == []


def test_irmaos_em_cascata_com_faixa_e_exclusao(db_session):
    """Seis iguais (mate do pastor, ratings 700..1200), um só espelho e um só esqueleto — os dois
    últimos com a assinatura gravada à mão, porque no xadrez real esse mate não existe na outra ala."""
    from chess_trainer.core.golpes.service import linha_de_assinatura
    for i in range(6):
        db_session.add(pastor(f"m{i}", rating=700 + 100 * i))
    db_session.add(pastor("esp", rating=900))
    db_session.add(pastor("esq", rating=1000))
    db_session.commit()
    a = assinar(FEN_PASTOR_START, ["h5f7"])
    for pid in (f"m{i}" for i in range(6)):
        db_session.add(linha_de_assinatura(a, LichessPuzzleSignature, pid))
    db_session.add(linha_de_assinatura(a.espelhada(), LichessPuzzleSignature, "esp"))
    esq = linha_de_assinatura(a, LichessPuzzleSignature, "esq")
    esq.destinos, esq.destinos_esp = 12345, 54321  # mesmo esqueleto e zona, outras casas
    db_session.add(esq)
    db_session.commit()

    r = irmaos(db_session, a, rating_lo=650, rating_hi=1250, excluir={"m0"}, k=5)
    assert [x.tier for x in r] == ["mesmo"] * 5 and "m0" not in {x.row.id for x in r}
    assert [x.row.rating for x in r] == sorted(x.row.rating for x in r)
    r2 = irmaos(db_session, a, rating_lo=650, rating_hi=1250, excluir=set(), k=8)
    assert [x.tier for x in r2] == ["mesmo"] * 6 + ["espelho", "esqueleto"]
    assert irmaos(db_session, a, rating_lo=2000, rating_hi=2200, excluir=set(), k=5) == []


def test_irmaos_respeita_popularidade(db_session):
    db_session.add(pastor("pop", popularity=10))
    db_session.commit()
    preparar(db_session, lambda *a: None)
    assert irmaos(db_session, assinar(FEN_PASTOR_START, ["h5f7"]), rating_lo=0, rating_hi=3000, excluir=set()) == []
```

`test_api_golpes.py`:

```python
def test_irmaos_de_um_puzzle_do_lichess(client):
    client.post("/api/golpes/preparar"); client.app.state.jobs.wait()
    client.put("/api/settings", json={"tactics_rating": 900, "tactics_window": 400})
    r = client.get("/api/golpes/lichess/p0/irmaos?k=3").json()
    assert r["assinatura"].startswith("Ke8 | Q") and len(r["itens"]) == 3
    assert all(i["tier"] == "mesmo" for i in r["itens"]) and r["itens"][0]["tactic"]["id"] != "p0"
    assert r["itens"][0]["tactic"]["fen_start"] and r["itens"][0]["tactic"]["rating"] <= r["itens"][-1]["tactic"]["rating"]
    assert client.get("/api/golpes/lichess/nao/irmaos").status_code == 404
    assert client.get("/api/golpes/own/nao/irmaos").status_code == 404
```

- [ ] **Step 2: rodar e ver falhar**

- [ ] **Step 3: implementar**

`service.py`:

```python
from dataclasses import dataclass


@dataclass
class Irmao:
    row: LichessPuzzle
    tier: str  # mesmo | espelho | esqueleto


def espalhar(itens: list, k: int) -> list:
    """k itens espalhados ao longo de uma lista ordenada: do fácil ao difícil, sem se amontoar."""
    n = len(itens)
    if n <= k:
        return list(itens)
    if k == 1:
        return [itens[0]]
    posicoes = sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})
    return [itens[p] for p in posicoes]


def _candidatos(db: Session, cond, rating_lo: int, rating_hi: int, excluir: set[str], min_popularity: int, min_plays: int):
    q = (select(LichessPuzzle).join(LichessPuzzleSignature, LichessPuzzleSignature.puzzle_id == LichessPuzzle.id)
         .where(cond, LichessPuzzle.rating.between(rating_lo, rating_hi),
                LichessPuzzle.popularity >= min_popularity, LichessPuzzle.nb_plays >= min_plays)
         .order_by(LichessPuzzle.rating, LichessPuzzle.id))
    return [r for r in db.scalars(q) if r.id not in excluir]


def irmaos(db: Session, a: Assinatura, *, rating_lo: int, rating_hi: int, excluir: set[str], k: int = 5,
           min_popularity: int = 50, min_plays: int = 50) -> list[Irmao]:
    """Cascata (spec §5): mesmo golpe → espelho → esqueleto na mesma zona. Cada camada enche o que
    falta, espalhada do fácil ao difícil; o que já saiu numa camada não volta na seguinte."""
    h = a.hashes()
    camadas = [
        ("mesmo", LichessPuzzleSignature.destinos == h["destinos"]),
        ("espelho", LichessPuzzleSignature.destinos == h["destinos_esp"]),
        ("esqueleto", (LichessPuzzleSignature.esqueleto == h["esqueleto"]) & (LichessPuzzleSignature.zona_rei == a.zona_rei)),
    ]
    out: list[Irmao] = []
    usados = set(excluir)
    for tier, cond in camadas:
        if len(out) >= k:
            break
        cands = _candidatos(db, cond, rating_lo, rating_hi, usados, min_popularity, min_plays)
        for row in espalhar(cands, k - len(out)):
            out.append(Irmao(row, tier))
            usados.add(row.id)
    return out
```

`schemas.py`:

```python
class IrmaoOut(BaseModel):
    tier: str
    tactic: TacticOut


class IrmaosOut(BaseModel):
    assinatura: str
    itens: list[IrmaoOut]
```

`routes/golpes.py`:

```python
from dataclasses import asdict

from chess_trainer.api.schemas import IrmaoOut, IrmaosOut
from chess_trainer.core.golpes.service import assinatura_de, irmaos
from chess_trainer.core.models import Puzzle, utcnow
from chess_trainer.core.tactics.convert import to_tactic
from chess_trainer.core.tactics.service import _seen_ids


@router.get("/{origem}/{id}/irmaos", response_model=IrmaosOut, dependencies=[Depends(golpes_ligado)])
def golpes_irmaos(origem: str, id: str, k: int | None = None, db: Session = Depends(get_db)):
    achado = assinatura_de(db, origem, id)
    if achado is None:
        raise HTTPException(404, "exercício sem assinatura de golpe")
    a, _fen, _lances = achado
    s = load_settings(db)
    n = max(1, min(10, k or s.golpes_bloco))
    excluir = _seen_ids(db, utcnow(), [id] if origem == "lichess" else [])
    excluir |= set(db.scalars(select(Puzzle.external_id).where(Puzzle.external_id.is_not(None))))
    lo, hi = s.tactics_rating - s.tactics_window, s.tactics_rating + s.tactics_window
    itens = []
    for irmao in irmaos(db, a, rating_lo=lo, rating_hi=hi, excluir=excluir, k=n):
        try:
            itens.append(IrmaoOut(tier=irmao.tier, tactic=asdict(to_tactic(irmao.row))))
        except ValueError:
            continue
    return IrmaosOut(assinatura=a.destinos(), itens=itens)
```

(`TacticOut` é o esquema que `GET /api/tactics/next` já devolve; `asdict(to_tactic(row))` é como `tactics.py:104` monta a resposta. Se `TacticOut` exigir o campo `saved`, preencha `saved=False`.)

- [ ] **Step 4: rodar tudo**

- [ ] **Step 5: commit**

```
feat(golpes): busca de irmãos em cascata (mesmo golpe, espelho, esqueleto) e rota
```

---

### Task 6: imagem do golpe

**Files:**
- Create: `backend/chess_trainer/core/golpes/imagem.py`
- Modify: `backend/chess_trainer/api/routes/golpes.py`
- Test: `backend/tests/test_golpes_imagem.py`, `backend/tests/test_api_golpes.py`

**Interfaces:**
- Consumes: `anotar(board, lances)` (Task 1), `assinatura_de` (Task 3).
- Produces: `svg_do_golpe(fen: str, lances_uci: Sequence[str], tamanho: int = 400) -> str`; `GET /api/golpes/{origem}/{id}/imagem.svg` → `image/svg+xml`, `Cache-Control: public, max-age=86400`.

- [ ] **Step 1: testes que falham**

```python
# backend/tests/test_golpes_imagem.py
from chess_trainer.core.golpes.imagem import svg_do_golpe

FEN_FRANCESA = "r1b1kbnr/pp3ppp/4p3/3pP3/3q4/3B4/PP3PPP/RNBQK2R w KQkq - 0 9"


def test_svg_desenha_lances_descobertas_e_rei():
    svg = svg_do_golpe(FEN_FRANCESA, ["d3b5", "e8e7", "d1d4"])
    assert svg.startswith("<svg") and 'viewBox' in svg
    # setas: verde para os lances de quem soluciona (d3→b5, d1→d4), vermelha para a descoberta (d1→d4 antes do lance)
    assert svg.count("#15803d") >= 2 and "#b91c1c" in svg


def test_svg_com_pretas_embaixo():
    fen_pretas = "rnbqk2r/pp3ppp/3b4/3Q4/3Pp3/4P3/PP3PPP/R1B1KBNR b KQkq - 0 9"
    svg = svg_do_golpe(fen_pretas, ["d6b4"])
    # orientação preta: a casa a1 fica no canto superior direito; chess.svg escreve as coordenadas na ordem invertida
    assert "<svg" in svg and "#15803d" in svg
```

`test_api_golpes.py`:

```python
def test_imagem_svg(client):
    r = client.get("/api/golpes/lichess/p0/imagem.svg")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml") and r.text.startswith("<svg")
    assert "max-age" in r.headers["cache-control"]
    assert client.get("/api/golpes/lichess/nao/imagem.svg").status_code == 404
```

- [ ] **Step 2: rodar e ver falhar**

- [ ] **Step 3: implementar**

```python
# backend/chess_trainer/core/golpes/imagem.py
"""O golpe desenhado: setas verdes para os lances de quem soluciona, vermelhas para o que eles
descobrem ou atacam, rei adversário e casas de chegada marcadas (spec golpes §6.1)."""
from __future__ import annotations

from typing import Sequence

import chess
import chess.svg

from chess_trainer.core.golpes.assinatura import anotar

VERDE = "#15803d"
VERMELHO = "#b91c1c"


def svg_do_golpe(fen: str, lances_uci: Sequence[str], tamanho: int = 400) -> str:
    board = chess.Board(fen)
    a = anotar(board, lances_uci)
    setas = []
    casas = chess.SquareSet([chess.parse_square(a.rei)])
    for l in a.lances:
        setas.append(chess.svg.Arrow(chess.parse_square(l.origem), chess.parse_square(l.destino), color=VERDE))
        casas.add(chess.parse_square(l.destino))
        for _peca, casa, por in l.descobertas:
            setas.append(chess.svg.Arrow(chess.parse_square(por), chess.parse_square(casa), color=VERMELHO))
        for _peca, casa in l.ataques:
            setas.append(chess.svg.Arrow(chess.parse_square(l.destino), chess.parse_square(casa), color=VERMELHO))
    return chess.svg.board(board, orientation=board.turn, arrows=setas, squares=casas, size=tamanho)
```

Rota:

```python
from fastapi import Response

from chess_trainer.core.golpes.imagem import svg_do_golpe


@router.get("/{origem}/{id}/imagem.svg", dependencies=[Depends(golpes_ligado)])
def golpes_imagem(origem: str, id: str, db: Session = Depends(get_db)):
    achado = assinatura_de(db, origem, id)
    if achado is None:
        raise HTTPException(404, "exercício sem assinatura de golpe")
    _a, fen, lances = achado
    return Response(content=svg_do_golpe(fen, lances), media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})
```

- [ ] **Step 4: rodar tudo**

- [ ] **Step 5: commit**

```
feat(golpes): imagem do golpe em SVG com as setas do lance e do que ele descobre
```

---

### Task 7: `sibling_of` no salvamento de táticas

**Files:**
- Modify: `backend/chess_trainer/api/schemas.py` (`SaveTacticIn` ~238-246), `backend/chess_trainer/api/routes/tactics.py:151-156`
- Test: `backend/tests/test_api_tactics.py`

**Interfaces:**
- Produces: `SaveTacticIn.sibling_of: str | None = None`; o `Puzzle` salvo carrega `sibling_of`; 404 se `sibling_of` não existe em `puzzles`.

- [ ] **Step 1: teste que falha** (em `test_api_tactics.py`, usando `client` e `run_import` do arquivo; pegue um id de tática com `client.get("/api/tactics/next").json()["id"]` e crie um exercício próprio de origem com a factory ou por outra tática salva antes):

```python
def test_salvar_tatica_com_sibling_of(client):
    run_import(client)
    origem = client.get("/api/tactics/next").json()["id"]
    p_origem = client.post(f"/api/tactics/{origem}/save").json()
    outro = client.get(f"/api/tactics/next?exclude={origem}").json()["id"]
    r = client.post(f"/api/tactics/{outro}/save", json={"correct": True, "sibling_of": p_origem["id"]})
    assert r.status_code == 201 and r.json()["sibling_of"] == p_origem["id"]
    assert client.post(f"/api/tactics/{outro}/save", json={"sibling_of": "nao-existe"}).status_code == 404
```

Acrescente `sibling_of: str | None` a `PuzzleOut` (schemas) e ao `_puzzle_out` de `routes/training.py:80` (`sibling_of=p.sibling_of`), e `sibling_of?: string | null` ao `PuzzleOut` do frontend (`types.ts`).

- [ ] **Step 2: rodar e ver falhar**

- [ ] **Step 3: implementar** — em `post_save_tactic`, antes de criar: `if body is not None and body.sibling_of is not None and db.get(Puzzle, body.sibling_of) is None: raise HTTPException(404, "exercício de origem não encontrado")`; na criação: `sibling_of=body.sibling_of if body is not None else None`; em `_back_to_queue`, se `body.sibling_of` vier e o puzzle ainda não tiver, preencha e faça `commit`.

- [ ] **Step 4: rodar tudo** (backend + `npm run build` para o tipo)

- [ ] **Step 5: commit**

```
feat(golpes): tática salva pelo bloco guarda o exercício de origem (sibling_of)
```

---

### Task 8: frontend — tipos, cliente, hooks e o cartão "Repetir o golpe"

**Files:**
- Modify: `frontend/src/api/types.ts`, `frontend/src/api/client.ts`, `frontend/src/api/queries.ts`, `frontend/src/train/ResultPanel.tsx:80-82`, `frontend/src/train/TacticResultPanel.tsx:26-50`
- Create: `frontend/src/train/GolpeCard.tsx`, `frontend/src/train/BlocoContext.tsx`
- Test: `frontend/tests/golpeCard.test.tsx`

**Interfaces:**
- Produces (types.ts): `GolpesStatus { enabled: boolean; versao: number; assinados: number; total: number; cobertura: Record<string, {ge5: number; ge2: number; sozinhos: number}> | null; rotulagem: boolean }`, `IrmaoOut { tier: "mesmo" | "espelho" | "esqueleto"; tactic: TacticOut }`, `IrmaosOut { assinatura: string; itens: IrmaoOut[] }`, `SaveTacticIn.sibling_of?: string`.
- client.ts: `golpesStatus: () => Promise<GolpesStatus>`, `golpesIrmaos: (origem: "own" | "lichess", id: string, k?: number) => Promise<IrmaosOut | null>` (null em 404, como `coachExplanation`), `golpesPreparar: () => Promise<JobQueued>`, `export const golpeImagemUrl = (origem, id) => `/api/golpes/${origem}/${id}/imagem.svg``.
- queries.ts: `useGolpesStatus()`, `useIrmaos(origem, id, enabled)`; `useStartJob` aceita `kind: "golpes_preparar"`.
- `BlocoContext`: `{ iniciar(bloco: Bloco): void }` com `Bloco = { anchorId: string; anchorOrigem: "own" | "lichess"; itens: TacticOut[] }`; `useBloco()`; provider padrão sem efeito (para testes e para páginas fora do treino).
- `GolpeCard({ origem, id, errou })`: renderiza nada enquanto carrega ou sem irmãos e sem assinatura; com assinatura: `<img alt="O golpe desenhado" src={golpeImagemUrl(...)}>`; com `errou` e `itens.length > 0`: botão `Treinar N parecidos` que chama `iniciar({...})`.

- [ ] **Step 1: teste que falha**

```tsx
// frontend/tests/golpeCard.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../src/api/client";
import type { IrmaosOut, TacticOut } from "../src/api/types";
import { BlocoProvider } from "../src/train/BlocoContext";
import { GolpeCard } from "../src/train/GolpeCard";

const tactic = (id: string, rating: number): TacticOut => ({ id, fen_start: "8/8/8/8/8/8/8/K6k w - - 0 1", side_to_move: "white", solution: { moves: [], explanation_pv: [] }, rating, themes: [], saved: false } as unknown as TacticOut);
const irmaos: IrmaosOut = { assinatura: "Ke8 | Q xP f7 #", itens: [{ tier: "mesmo", tactic: tactic("a", 800) }, { tier: "mesmo", tactic: tactic("b", 900) }] };

function montar(props: { errou: boolean }, iniciar = vi.fn()) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <BlocoProvider value={{ iniciar }}><GolpeCard origem="own" id="p1" errou={props.errou} /></BlocoProvider>
    </QueryClientProvider>,
  );
  return iniciar;
}

beforeEach(() => vi.spyOn(api, "golpesIrmaos").mockResolvedValue(irmaos));
afterEach(() => vi.restoreAllMocks());

describe("GolpeCard", () => {
  it("erro: imagem e botão que abre o bloco com os irmãos", async () => {
    const iniciar = montar({ errou: true });
    expect(await screen.findByAltText("O golpe desenhado")).toHaveAttribute("src", "/api/golpes/own/p1/imagem.svg");
    await userEvent.click(screen.getByRole("button", { name: "Treinar 2 parecidos" }));
    expect(iniciar).toHaveBeenCalledWith({ anchorId: "p1", anchorOrigem: "own", itens: irmaos.itens.map((i) => i.tactic) });
  });
  it("acerto: só a imagem", async () => {
    montar({ errou: false });
    expect(await screen.findByAltText("O golpe desenhado")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /parecidos/ })).toBeNull();
  });
  it("sem assinatura (404): nada", async () => {
    vi.spyOn(api, "golpesIrmaos").mockResolvedValue(null);
    const { container } = render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><GolpeCard origem="lichess" id="x" errou /></QueryClientProvider>,
    );
    await waitFor(() => expect(api.golpesIrmaos).toHaveBeenCalled());
    expect(container.querySelector("img")).toBeNull();
  });
});
```

- [ ] **Step 2: rodar e ver falhar** — `cd frontend && npm test -- golpeCard`

- [ ] **Step 3: implementar**

`types.ts`: as interfaces acima (junto de `TacticOut`/`SaveTacticIn`).

`client.ts` (no objeto `api`, e o construtor de URL fora dele):

```ts
  golpesStatus: () => request<GolpesStatus>("/golpes/status"),
  golpesIrmaos: async (origem: "own" | "lichess", id: string, k?: number) => {
    try { return await request<IrmaosOut>(`/golpes/${origem}/${id}/irmaos${qs({ k })}`); }
    catch (e) { if (e instanceof ApiError && e.status === 404) return null; throw e; }
  },
  golpesPreparar: () => request<JobQueued>("/golpes/preparar", post("")),
```

```ts
export const golpeImagemUrl = (origem: "own" | "lichess", id: string) => `/api/golpes/${origem}/${id}/imagem.svg`;
```

`queries.ts`: `keys.golpesStatus = ["golpes", "status"]`, `keys.irmaos = (o, id) => ["golpes", "irmaos", o, id]`;

```ts
export const useGolpesStatus = () => useQuery({ queryKey: keys.golpesStatus, queryFn: api.golpesStatus });
export const useIrmaos = (origem: "own" | "lichess", id: string, enabled = true) =>
  useQuery({ queryKey: keys.irmaos(origem, id), queryFn: () => api.golpesIrmaos(origem, id), enabled, staleTime: 60_000 });
```

e em `useStartJob` o novo `kind: "golpes_preparar"` → `api.golpesPreparar()`.

`BlocoContext.tsx`:

```tsx
import { createContext, useContext, type ReactNode } from "react";
import type { TacticOut } from "../api/types";

export type Bloco = { anchorId: string; anchorOrigem: "own" | "lichess"; itens: TacticOut[] };
type Ctx = { iniciar: (bloco: Bloco) => void };
const BlocoCtx = createContext<Ctx>({ iniciar: () => {} });
export const useBloco = () => useContext(BlocoCtx);
export function BlocoProvider({ value, children }: { value: Ctx; children: ReactNode }) {
  return <BlocoCtx.Provider value={value}>{children}</BlocoCtx.Provider>;
}
```

`GolpeCard.tsx`:

```tsx
import { golpeImagemUrl } from "../api/client";
import { useIrmaos } from "../api/queries";
import { useBloco } from "./BlocoContext";

/** Cartão "Repetir o golpe": o golpe desenhado e, no erro, o bloco de irmãos (spec golpes §6). */
export function GolpeCard({ origem, id, errou }: { origem: "own" | "lichess"; id: string; errou: boolean }) {
  const { data } = useIrmaos(origem, id);
  const { iniciar } = useBloco();
  if (!data) return null;
  const itens = data.itens.map((i) => i.tactic);
  return (
    <div className="card golpe-card">
      <h3 style={{ marginTop: 0 }}>Repetir o golpe</h3>
      <img alt="O golpe desenhado" src={golpeImagemUrl(origem, id)} style={{ width: "100%", maxWidth: 320 }} />
      {errou && itens.length > 0 && (
        <button onClick={() => iniciar({ anchorId: id, anchorOrigem: origem, itens })}>Treinar {itens.length} parecidos</button>
      )}
    </div>
  );
}
```

`ResultPanel.tsx` (linha ~81): `{golpes?.enabled && <GolpeCard origem="own" id={puzzle.id} errou={!review?.correct} />}` com `const { data: golpes } = useGolpesStatus();` (veja como `coach` é obtido no mesmo arquivo e como `review.correct`/`result` é exposto — use o campo que o painel já usa para dizer se errou). `TacticResultPanel.tsx`: dentro de `lateral`, depois do cartão existente: `{golpes?.enabled && <GolpeCard origem="lichess" id={tactic.id} errou={!attempt?.correct || !!attempt?.used_hint} />}`. Ajuste os testes existentes desses painéis para mockar `api.golpesStatus` (`enabled: false`) quando não quiserem o cartão.

- [ ] **Step 4: rodar** — `npm test && npm run build`

- [ ] **Step 5: commit**

```
feat(golpes): cartão "Repetir o golpe" nos painéis de resultado
```

---

### Task 9: frontend — o bloco: sessão de táticas com lista fixa que salva com `sibling_of`

**Files:**
- Modify: `frontend/src/train/SessionStart.tsx:13-20` (`SessionConfig`), `frontend/src/train/TacticSession.tsx` (linhas 27-50 `TacticPuzzle`, 110 e 127 `api.nextTactic`), `frontend/src/train/TrainPage.tsx:36`
- Test: `frontend/tests/tacticSession.test.tsx` (existe? se não, crie), `frontend/tests/trainPage.test.tsx` (idem)

**Interfaces:**
- `SessionConfig` ganha `bloco?: Bloco` (de `BlocoContext`). Com `bloco`, a sessão não chama `api.nextTactic`: percorre `bloco.itens` na ordem; ao acabar, `finish(...)` com o resumo normal.
- Depois de cada tentativa registrada (`api.attempt`), com `bloco` presente: `api.saveTactic(tactic.id, { correct: out.correct, used_hint: out.used_hint, duration_ms, session_id, sibling_of: bloco.anchorOrigem === "own" ? bloco.anchorId : undefined })`. (Âncora do Lichess não é um `Puzzle`; sem `sibling_of` nesse caso — o vínculo fica para quando a âncora for exercício próprio.)
- `TrainPage` provê `BlocoProvider` com `iniciar` que troca a configuração corrente por `{ source: "tactics", mode: "bloco", bloco, ... }` e monta `TacticSession`; ao terminar mostra `TacticSummary` como hoje.

- [ ] **Step 1: testes que falham**

Para não acoplar o teste ao tabuleiro, a lógica do bloco vive em funções puras exportadas de um módulo novo `frontend/src/train/bloco.ts`:

```ts
// frontend/src/train/bloco.ts
import type { SaveTacticIn, TacticOut } from "../api/types";
import type { Bloco } from "./BlocoContext";
import type { SessionConfig } from "./SessionStart";

/** O item i do bloco, ou nulo quando acabou. */
export const itemDoBloco = (bloco: Bloco, i: number): TacticOut | null => bloco.itens[i] ?? null;

/** O que se manda para `saveTactic` depois de uma tentativa do bloco: o irmão entra na fila com
 *  o vínculo para o exercício de origem (só quando a âncora é exercício próprio). */
export function corpoDoSalvamento(bloco: Bloco, r: { correct: boolean; used_hint: boolean; duration_ms: number; session_id?: string | null }): SaveTacticIn {
  return { correct: r.correct, used_hint: r.used_hint, duration_ms: r.duration_ms, session_id: r.session_id ?? undefined,
           sibling_of: bloco.anchorOrigem === "own" ? bloco.anchorId : undefined };
}

/** A configuração de sessão que o cartão abre. */
export const configDoBloco = (bloco: Bloco): SessionConfig =>
  ({ source: "tactics", mode: "bloco", filters: {}, plannedMinutes: 0, themes: [], bloco });
```

```tsx
// frontend/tests/bloco.test.tsx
import { describe, expect, it } from "vitest";

import type { TacticOut } from "../src/api/types";
import { configDoBloco, corpoDoSalvamento, itemDoBloco } from "../src/train/bloco";

const t = (id: string): TacticOut => ({ id } as unknown as TacticOut);
const bloco = { anchorId: "p1", anchorOrigem: "own" as const, itens: [t("a"), t("b")] };

describe("bloco de irmãos", () => {
  it("percorre a lista fixa e acaba", () => {
    expect(itemDoBloco(bloco, 0)?.id).toBe("a");
    expect(itemDoBloco(bloco, 1)?.id).toBe("b");
    expect(itemDoBloco(bloco, 2)).toBeNull();
  });
  it("salva o irmão com o vínculo para o exercício de origem", () => {
    expect(corpoDoSalvamento(bloco, { correct: true, used_hint: false, duration_ms: 1200, session_id: "s1" }))
      .toEqual({ correct: true, used_hint: false, duration_ms: 1200, session_id: "s1", sibling_of: "p1" });
    expect(corpoDoSalvamento({ ...bloco, anchorOrigem: "lichess" }, { correct: false, used_hint: true, duration_ms: 5 }).sibling_of).toBeUndefined();
  });
  it("abre uma sessão de táticas no modo bloco", () => {
    expect(configDoBloco(bloco)).toMatchObject({ source: "tactics", mode: "bloco", bloco });
  });
});
```

E um teste de integração leve em `frontend/tests/tacticSession.test.tsx` (crie o arquivo se não existir, com `Board` mockado como em `tacticResultPanel.test.tsx` e um `wrapper` com `QueryClientProvider` + `MemoryRouter`):

```tsx
it("bloco: não chama nextTactic e mostra o primeiro irmão", async () => {
  const next = vi.spyOn(api, "nextTactic");
  vi.spyOn(api, "analyse").mockResolvedValue({ lines: [] } as never);
  render(<TacticSession config={configDoBloco({ anchorId: "p1", anchorOrigem: "own", itens: [tactic("a", 800), tactic("b", 900)] })} onFinish={vi.fn()} />, { wrapper });
  expect(await screen.findByText(/Repetir o golpe/)).toBeInTheDocument();
  expect(next).not.toHaveBeenCalled();
});
```

(`tactic(id, rating)` como no teste do `GolpeCard`; se o `TacticSession` exigir mais campos em `TacticOut` para renderizar, copie o `TacticOut` completo usado em `tacticResultPanel.test.tsx`.)

- [ ] **Step 2: rodar e ver falhar**

- [ ] **Step 3: implementar**

`SessionConfig` (`SessionStart.tsx`): `mode: ... | "bloco"`, `bloco?: Bloco`. Crie `frontend/src/train/bloco.ts` com o conteúdo do Step 1.

`TacticSession.tsx`: um `useRef<number>(0)` como cursor quando `config.bloco` existe. Nos dois pontos que hoje chamam `api.nextTactic(...)` (linhas ~110 e ~127), antes deles:

```ts
if (config.bloco) {
  const item = itemDoBloco(config.bloco, cursor.current++);
  if (item === null) { finish("bloco concluído"); return; }
  setTactic(item);
  return;
}
```

Em `TacticPuzzle.submit`, depois de `const out = await api.attempt(body)`:

```ts
if (bloco) await api.saveTactic(tactic.id, corpoDoSalvamento(bloco, { ...out, duration_ms: body.duration_ms, session_id: body.session_id }));
```

(passe `bloco` como prop de `TacticSession` para `TacticPuzzle`). Quando `bloco`, o título da tela é "Repetir o golpe" e o resumo diz "N de M".

`TrainPage.tsx`: `const iniciar = (bloco: Bloco) => setConfig(configDoBloco(bloco));` e envolva o corpo em `<BlocoProvider value={{ iniciar }}>`.

- [ ] **Step 4: rodar** — `npm test && npm run build`

- [ ] **Step 5: commit**

```
feat(golpes): bloco de irmãos na sessão de táticas, salvo na fila com o exercício de origem
```

---

### Task 10: frontend — Configurações: seção Golpes e a tarefa

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx` (nova seção `card`; `validate`), `frontend/src/components/JobCard.tsx:6-40`, `frontend/tests/fixtures/settings.ts`
- Test: `frontend/tests/settingsPage.test.tsx` (existente; acrescente casos)

**Interfaces:** `Settings.golpes_enabled: boolean`, `Settings.golpes_bloco: number`; `JOB_LABEL.golpes_preparar = "Preparando golpes"`, `JOB_RUNNING_HINT` e `CANCEL_LABEL` correspondentes.

- [ ] **Step 1: testes que falham** — na página: a seção "Golpes" mostra o toggle, o campo "Irmãos por bloco", o botão "Preparar golpes" (chama `start.mutate({ kind: "golpes_preparar" })` → `api.golpesPreparar`), e o texto de status `"{assinados} de {total} puzzles com assinatura"` + cobertura quando existir (`useGolpesStatus` mockado). `validate` rejeita bloco fora de 3–10 ("Irmãos por bloco: entre 3 e 10").

- [ ] **Step 2: rodar e ver falhar**

- [ ] **Step 3: implementar** — seção:

```tsx
<div className="card">
  <h3 style={{ marginTop: 0 }}>Golpes</h3>
  <label className="row"><input type="checkbox" checked={form.golpes_enabled} onChange={(e) => setForm({ ...form, golpes_enabled: e.target.checked })} /> Mostrar "Repetir o golpe" no resultado dos exercícios</label>
  {field("Irmãos por bloco", "golpes_bloco")}
  <p className="muted">{golpes ? `${nf.format(golpes.assinados)} de ${nf.format(golpes.total)} puzzles com assinatura` : ""}
    {golpes?.cobertura ? ` · ${nf.format(golpes.cobertura.destinos.ge5)} com cinco ou mais irmãos` : ""}</p>
  <button onClick={() => start.mutate({ kind: "golpes_preparar" })} disabled={status?.job.state === "running"}>Preparar golpes</button>
</div>
```

`JobCard.tsx`: as três entradas. `fixtures/settings.ts`: `golpes_enabled: true, golpes_bloco: 5`.

- [ ] **Step 4: rodar** — `npm test && npm run build`

- [ ] **Step 5: commit**

```
feat(golpes): seção Golpes em Configurações com a tarefa "Preparar golpes"
```

---

### Task 11: rotulagem (backend) e exportação do ouro

**Files:**
- Create: `backend/chess_trainer/core/golpes/rotulagem.py`, `backend/chess_trainer/core/golpes/exportar_ouro.py`
- Modify: `backend/chess_trainer/api/routes/golpes.py`, `backend/chess_trainer/api/schemas.py`, `backend/chess_trainer/api/app.py`
- Test: `backend/tests/test_golpes_rotulagem.py`, `backend/tests/test_api_golpes.py`

**Interfaces:**
- `proximo_item(db, settings, rng: random.Random | None = None, por_camada: int = 3) -> dict | None` — escolhe uma âncora (exercício próprio com assinatura, se houver; senão um puzzle do Lichess assinado ao acaso), e candidatos: até `por_camada` de cada camada (`mesmo`, `espelho`, `esqueleto`), sem filtro de rating, excluindo pares já rotulados; embaralhados. Devolve `{"anchor": {"origem", "id", "assinatura", "tactic"|"puzzle"}, "candidatos": [{"id", "tier", "tactic"}]}` (o `tier` viaja para a gravação; a interface não o mostra).
- `rotular(db, *, anchor_origem, anchor_id, candidate_id, tier, label) -> GolpeLabel` (`label ∈ mesmo|parecido|nada`, senão `ValueError`).
- `exportar_ouro(db) -> str` — JSONL, uma linha por rótulo: `{"anchor_origem","anchor_id","anchor_assinatura","candidate_id","candidate_assinatura","tier","versao","label","created_at"}`; e `main()` em `exportar_ouro.py` que grava em `ml/golpes/gold/<AAAA-MM-DD>.jsonl` (caminho relativo à raiz do repositório = `backend/..`), usando o banco de `CHESS_TRAINER_DB` como o resto do app.
- Rotas (todas 404 sem `app.state.rotulagem_enabled`): `GET /api/golpes/rotulagem/proximo`, `POST /api/golpes/rotulagem` (`RotuloIn{anchor_origem, anchor_id, candidate_id, tier, label}` → 201), `GET /api/golpes/rotulagem/ouro` (JSONL, `text/plain`), `GET /api/golpes/rotulagem/contagem` → `{"total": n, "por_label": {...}}`.

- [ ] **Step 1: testes que falham**

```python
# backend/tests/test_golpes_rotulagem.py
import json
import random

import pytest

from chess_trainer.config import load_settings
from chess_trainer.core.golpes.rotulagem import exportar_ouro, proximo_item, rotular
from chess_trainer.core.golpes.service import preparar
from chess_trainer.core.models import GolpeLabel
from tests.test_golpes_service import pastor


def _oito_pastores(db):
    for i in range(8):
        db.add(pastor(f"r{i}", rating=700 + 50 * i))
    db.commit()
    preparar(db, lambda *a: None)


def test_proximo_item_traz_ancora_e_candidatos_com_tier(db_session):
    _oito_pastores(db_session)
    item = proximo_item(db_session, load_settings(db_session), rng=random.Random(1))
    assert item["anchor"]["origem"] == "lichess" and item["anchor"]["assinatura"] == "Ke8 | Q xP f7 #"
    assert 1 <= len(item["candidatos"]) <= 3 and all(c["tier"] == "mesmo" for c in item["candidatos"])
    assert item["anchor"]["id"] not in {c["id"] for c in item["candidatos"]}
    assert item["candidatos"][0]["tactic"]["fen_start"]


def test_rotular_grava_e_o_proximo_item_nao_repete(db_session):
    _oito_pastores(db_session)
    item = proximo_item(db_session, load_settings(db_session), rng=random.Random(1))
    ancora = item["anchor"]["id"]
    for c in item["candidatos"]:
        rotular(db_session, anchor_origem="lichess", anchor_id=ancora, candidate_id=c["id"], tier=c["tier"], label="mesmo")
    assert db_session.query(GolpeLabel).count() == len(item["candidatos"])
    de_novo = proximo_item(db_session, load_settings(db_session), rng=random.Random(1), ancora=("lichess", ancora))
    assert not ({c["id"] for c in de_novo["candidatos"]} & {c["id"] for c in item["candidatos"]})
    with pytest.raises(ValueError):
        rotular(db_session, anchor_origem="lichess", anchor_id=ancora, candidate_id="r1", tier="mesmo", label="talvez")


def test_exportar_ouro_uma_linha_por_rotulo(db_session):
    _oito_pastores(db_session)
    rotular(db_session, anchor_origem="lichess", anchor_id="r0", candidate_id="r1", tier="mesmo", label="parecido")
    linhas = [json.loads(l) for l in exportar_ouro(db_session).splitlines()]
    assert len(linhas) == 1
    assert linhas[0]["anchor_id"] == "r0" and linhas[0]["candidate_id"] == "r1" and linhas[0]["label"] == "parecido"
    assert linhas[0]["anchor_assinatura"] == linhas[0]["candidate_assinatura"] == "Ke8 | Q xP f7 #" and linhas[0]["versao"] == 1
```

(`proximo_item` aceita `ancora=(origem, id)` opcional para fixar a âncora; sem ela, sorteia.) Em `test_api_golpes.py`:

```python
def test_rotulagem_desligada_por_padrao(client):
    assert client.get("/api/golpes/rotulagem/proximo").status_code == 404
    assert client.post("/api/golpes/rotulagem", json={"anchor_origem": "lichess", "anchor_id": "p0", "candidate_id": "p1", "tier": "mesmo", "label": "mesmo"}).status_code == 404


def test_rotulagem_ligada(tmp_path):
    app = create_app(db_path=":memory:", engine_factory=lambda s: FakeEngine(default=first_legal_default(0)), rotulagem_enabled=True)
    with TestClient(app) as c:
        db = app.state.session_factory()
        for i in range(6):
            db.add(pastor(f"p{i}", 700 + 100 * i))
        db.commit(); db.close()
        c.post("/api/golpes/preparar"); app.state.jobs.wait()
        assert c.get("/api/golpes/status").json()["rotulagem"] is True
        item = c.get("/api/golpes/rotulagem/proximo").json()
        cand = item["candidatos"][0]
        r = c.post("/api/golpes/rotulagem", json={"anchor_origem": "lichess", "anchor_id": item["anchor"]["id"], "candidate_id": cand["id"], "tier": cand["tier"], "label": "nada"})
        assert r.status_code == 201
        assert c.get("/api/golpes/rotulagem/contagem").json() == {"total": 1, "por_label": {"nada": 1}}
        ouro = c.get("/api/golpes/rotulagem/ouro")
        assert ouro.status_code == 200 and ouro.text.count("\n") == 1
```

- [ ] **Step 2: rodar e ver falhar**

- [ ] **Step 3: implementar** — `rotulagem.py` usa `irmaos(...)` com `rating_lo=0, rating_hi=4000, k=por_camada` por camada (chame três vezes, uma por camada, filtrando o `tier`; ou exponha em `service.py` um `candidatos_por_camada(db, a, k)` que devolve `dict[tier, list[LichessPuzzle]]`, reutilizado por `irmaos`). Pares já rotulados: `select(GolpeLabel.candidate_id).where(anchor_id == ...)`. `exportar_ouro` calcula as assinaturas com `assinatura_de` na hora (texto de `destinos`). `main()`:

```python
def main() -> None:
    import os, sys
    from datetime import date
    from pathlib import Path
    from chess_trainer.core.db import make_engine, make_session_factory
    caminho = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[4] / "ml" / "golpes" / "gold" / f"{date.today().isoformat()}.jsonl"
    engine = make_engine(os.environ.get("CHESS_TRAINER_DB", "data/chess_trainer.db"))
    with make_session_factory(engine)() as db:
        texto = exportar_ouro(db)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto, encoding="utf-8")
    print(f"{texto.count(chr(10))} rótulos em {caminho}")
```

(confira os nomes reais de `make_engine`/`make_session_factory` e o caminho padrão do banco em `core/db.py` e `__main__.py`).

- [ ] **Step 4: rodar tudo**

- [ ] **Step 5: commit**

```
feat(golpes): rotulagem em dev (próximo item, rótulos, exportação do conjunto de ouro)
```

---

### Task 12: rotulagem (frontend)

**Files:**
- Create: `frontend/src/pages/RotulagemPage.tsx`
- Modify: `frontend/src/App.tsx` (rota `/rotulagem`), `frontend/src/api/{types,client,queries}.ts`
- Test: `frontend/tests/rotulagemPage.test.tsx`

**Interfaces:** `api.rotulagemProximo()`, `api.rotular(body)`, `api.rotulagemContagem()`; a página existe só quando `useGolpesStatus().data?.rotulagem` é verdadeiro (senão mostra "Rotulagem desligada: inicie o servidor com CHESS_TRAINER_ROTULAGEM=1"). Layout: a âncora à esquerda com a imagem do golpe (`golpeImagemUrl`) e a assinatura em texto; à direita a lista de candidatos, cada um com a própria imagem (`golpeImagemUrl("lichess", id)`) e três botões: "mesmo golpe", "parecido", "nada a ver"; ao clicar, grava e some o candidato; quando acabam, carrega o próximo item. Contagem no topo ("N rótulos").

- [ ] **Step 1: teste que falha**

Tipos (types.ts): `RotulagemItem { anchor: { origem: "own" | "lichess"; id: string; assinatura: string }; candidatos: { id: string; tier: string; tactic: TacticOut }[] }`, `RotuloIn { anchor_origem: "own" | "lichess"; anchor_id: string; candidate_id: string; tier: string; label: "mesmo" | "parecido" | "nada" }`, `RotulagemContagem { total: number; por_label: Record<string, number> }`. Cliente: `rotulagemProximo: () => request<RotulagemItem>("/golpes/rotulagem/proximo")`, `rotular: (body: RotuloIn) => request<unknown>("/golpes/rotulagem", post("", body))`, `rotulagemContagem: () => request<RotulagemContagem>("/golpes/rotulagem/contagem")`.

```tsx
// frontend/tests/rotulagemPage.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../src/api/client";
import type { GolpesStatus, RotulagemItem, TacticOut } from "../src/api/types";
import { RotulagemPage } from "../src/pages/RotulagemPage";

const status: GolpesStatus = { enabled: true, versao: 1, assinados: 6, total: 6, cobertura: null, rotulagem: true };
const t = (id: string): TacticOut => ({ id, fen_start: "8/8/8/8/8/8/8/K6k w - - 0 1" } as unknown as TacticOut);
const item: RotulagemItem = { anchor: { origem: "lichess", id: "p0", assinatura: "Ke8 | Q xP f7 #" },
                              candidatos: [{ id: "a", tier: "mesmo", tactic: t("a") }, { id: "b", tier: "espelho", tactic: t("b") }] };

function montar() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><RotulagemPage /></QueryClientProvider>);
}

beforeEach(() => {
  vi.spyOn(api, "golpesStatus").mockResolvedValue(status);
  vi.spyOn(api, "rotulagemProximo").mockResolvedValue(item);
  vi.spyOn(api, "rotulagemContagem").mockResolvedValue({ total: 3, por_label: { mesmo: 3 } });
  vi.spyOn(api, "rotular").mockResolvedValue({});
});
afterEach(() => vi.restoreAllMocks());

describe("RotulagemPage", () => {
  it("mostra a âncora, os candidatos e grava o rótulo sem revelar a camada", async () => {
    montar();
    expect(await screen.findByText("Ke8 | Q xP f7 #")).toBeInTheDocument();
    expect(screen.getByText("3 rótulos")).toBeInTheDocument();
    expect(screen.queryByText(/espelho/)).toBeNull();
    const botoes = screen.getAllByRole("button", { name: "mesmo golpe" });
    expect(botoes).toHaveLength(2);
    await userEvent.click(botoes[0]);
    expect(api.rotular).toHaveBeenCalledWith({ anchor_origem: "lichess", anchor_id: "p0", candidate_id: "a", tier: "mesmo", label: "mesmo" });
    await waitFor(() => expect(screen.getAllByRole("button", { name: "mesmo golpe" })).toHaveLength(1));
  });
  it("quando os candidatos acabam, pede o próximo item", async () => {
    montar();
    await screen.findByText("Ke8 | Q xP f7 #");
    await userEvent.click(screen.getAllByRole("button", { name: "nada a ver" })[0]);
    await userEvent.click(screen.getAllByRole("button", { name: "nada a ver" })[0]);
    await waitFor(() => expect(api.rotulagemProximo).toHaveBeenCalledTimes(2));
  });
  it("desligada: explica como ligar", async () => {
    vi.spyOn(api, "golpesStatus").mockResolvedValue({ ...status, rotulagem: false });
    montar();
    expect(await screen.findByText(/CHESS_TRAINER_ROTULAGEM=1/)).toBeInTheDocument();
    expect(api.rotulagemProximo).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: rodar e ver falhar**

- [ ] **Step 3: implementar** (componente único, sem entrada na `Nav`).

- [ ] **Step 4: rodar** — `npm test && npm run build`

- [ ] **Step 5: commit**

```
feat(golpes): tela de rotulagem para o conjunto de ouro
```

---

### Task 13: documentação

**Files:**
- Modify: `docs/manual.pt-BR.md` (nova seção `## Golpes` antes de `## Treinador (IA)`), `README.md` (bullet na lista de features e seção `### Patterns and siblings`), spec §11 (marcar os passos 1–4 como feitos com a data)

- [ ] **Step 1: escrever** — manual: o que é a assinatura em uma frase; "Preparar golpes" em Configurações; o cartão "Repetir o golpe" (imagem; no erro, o bloco de N irmãos do fácil ao difícil, que depois entram na repetição espaçada); tamanho do bloco e desligar; rotulagem é ferramenta de desenvolvimento (`CHESS_TRAINER_ROTULAGEM=1`). README: o mesmo em inglês, vocabulário de produto.

- [ ] **Step 2: conferir** — `git diff` sem termos proibidos (vagas, entrevistas, vitrine, showcase).

- [ ] **Step 3: commit**

```
docs(golpes): manual e README descrevem "Repetir o golpe" e a tarefa de preparo
```

---

## Verificação final

- `cd backend && uv run pytest -q` e `cd frontend && npm test && npm run build` verdes.
- Fumaça manual (pelo usuário, depois de reiniciar o backend): Configurações → "Preparar golpes" (uns dez minutos); errar um exercício → cartão com a imagem e "Treinar 5 parecidos"; concluir o bloco; ver os irmãos na fila de revisão com `sibling_of` preenchido (`GET /api/puzzles/{id}`).
- Só então: `CHESS_TRAINER_ROTULAGEM=1` e a primeira sessão de rotulagem (passo 4 da spec).
