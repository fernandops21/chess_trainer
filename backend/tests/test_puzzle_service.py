import json
from datetime import datetime

import chess
from sqlalchemy import func, select

from chess_trainer.config import AppSettings
from chess_trainer.core.analysis.engine import LineEval
from chess_trainer.core.evals import MATE_SCORE
from chess_trainer.core.golpes.service import assinar_proprio, garantir_assinatura
from chess_trainer.core.models import Position, Puzzle, PuzzleSignature, Review
from chess_trainer.core.puzzles.generator import PuzzleConfig
from chess_trainer.core.puzzles import service as puzzle_service
from chess_trainer.core.puzzles.generator import PuzzleDraft, SolutionMove
from chess_trainer.core.puzzles.service import _is_trivial_punish, build_drafts, draft_puzzles, extend_all
from tests.fakes import FakeEngine, first_legal_default

CFG = PuzzleConfig(depth=10)


def _pos(**overrides) -> Position:
    defaults = dict(
        game_id="g1", ply=1, fen=chess.STARTING_FEN, move_played="e4", move_uci="e2e4",
        eval_before=0, eval_after=-50, best_move="e2e4", best_eval=0,
        is_mistake=True, mistake_level="mistake", mistake_by="opponent",
    )
    defaults.update(overrides)
    return Position(**defaults)


def test_prefilter_skips_engine_when_solver_eval_is_low():
    pos = _pos(eval_after=-50)
    fake = FakeEngine()
    drafts = build_drafts(pos, fake, CFG)
    assert drafts == []
    assert fake.calls == []


def test_prefilter_allows_engine_when_mate_for_solver():
    pos = _pos(eval_after=-(MATE_SCORE - 2))
    fake = FakeEngine(default=first_legal_default(0))
    build_drafts(pos, fake, CFG)
    assert fake.calls != []


HANGING_QUEEN_FEN = "3qk3/8/8/8/8/2N5/8/4K3 b - - 0 1"  # ...Qd5?? indefesa, atacada pelo Nc3
DEFENDED_QUEEN_FEN = "3qk3/8/2p5/8/8/2N5/8/4K3 b - - 0 1"  # ...Qd5?? defendida, mas Nc3 (mais barato) ataca
HANGING_PAWN_FEN = "4k3/4p3/8/8/8/3N4/8/4K3 b - - 0 1"  # ...e5?? peão indefeso atacado pelo Nd3


def test_trivial_hanging_queen_is_not_generated():
    pos = _pos(fen=HANGING_QUEEN_FEN, move_uci="d8d5", eval_after=-900)
    fake = FakeEngine()
    assert build_drafts(pos, fake, CFG) == []
    assert fake.calls == []


def test_trivial_rule_yields_to_mate_for_solver():
    pos = _pos(fen=HANGING_QUEEN_FEN, move_uci="d8d5", eval_after=-(MATE_SCORE - 2))
    fake = FakeEngine(default=first_legal_default(0))
    build_drafts(pos, fake, CFG)
    assert fake.calls != []


def test_defended_queen_with_cheap_attacker_is_trivial():
    # bound corrigido usa o ganho líquido (9-3=6 -> 800cp), não o valor de face (900cp+200);
    # com eval_after=-700 (solver +700) o ganho líquido ainda cobre a vantagem.
    pos = _pos(fen=DEFENDED_QUEEN_FEN, move_uci="d8d5", eval_after=-700)
    fake = FakeEngine()
    assert build_drafts(pos, fake, CFG) == []
    assert fake.calls == []


def test_hanging_pawn_is_not_trivial():
    pos = _pos(fen=HANGING_PAWN_FEN, move_uci="e7e5", eval_after=-300)
    fake = FakeEngine(default=first_legal_default(0))
    build_drafts(pos, fake, CFG)
    assert fake.calls != []


# Achado 1: rei conta como "atacante" com PIECE_VALUES[KING] = 0, tornando qualquer peça
# defendida "trivial" por comparação (0 < valor), mesmo quando Kxsquare é ilegal.
KING_ONLY_ATTACKER_FEN = "4k3/8/2p1K3/3n4/8/8/8/8 w - - 0 1"  # Nd5 defendido por c6; só o Ke6 "ataca", mas Kxd5 é ilegal


def test_king_only_attacker_is_not_trivial():
    board_after = chess.Board(KING_ONLY_ATTACKER_FEN)
    assert not _is_trivial_punish(board_after, "c7d5", 300)


# Achado 2: atacante presa (pin) não pode capturar de fato; is_attacked_by/attackers ignoram isso.
PINNED_ATTACKER_FEN = "4k3/8/8/3qb3/8/2N5/8/K7 w - - 0 1"  # Qd5 indefesa; Nc3 preso ao Ka1 pelo Be5, Nxd5 ilegal


def test_pinned_attacker_is_not_trivial():
    board_after = chess.Board(PINNED_ATTACKER_FEN)
    assert not _is_trivial_punish(board_after, "d8d5", 300)


# Achado 4: o teto de avaliação da regra trivial deve usar o ganho líquido da captura
# (valor da peça menos o atacante mais barato quando defendida), não o valor de face.
DEFENDED_BISHOP_FEN = "3qk3/8/8/3b4/2P5/8/8/4K3 w - - 0 1"  # Bd5 defendido pela Qd8; cxd5 (peão) ataca


def test_trivial_bound_uses_net_gain_not_face_value():
    board_after = chess.Board(DEFENDED_BISHOP_FEN)
    # ganho líquido = 3 (bispo) - 1 (peão) = 2 -> teto 400cp; 500 > 400 não é trivial.
    assert not _is_trivial_punish(board_after, "d7d5", 500)
    # 300 <= 400 -> trivial.
    assert _is_trivial_punish(board_after, "d7d5", 300)


# --- extensão dos exercícios já gravados (job "Estender exercícios") -------

HANGING_QUEEN = "4k3/8/8/3q4/8/2N5/7P/4K3 w - - 0 1"  # Nxd5 ganha a dama; depois h4 e h5 são únicos


def _epd(*ucis: str) -> str:
    b = chess.Board(HANGING_QUEEN)
    for u in ucis:
        b.push_uci(u)
    return b.epd()


def _extend_script() -> dict[str, list[LineEval]]:
    """Depois de Nxd5 (já na solução gravada), o branco tem dois lances únicos e para no terceiro."""
    return {
        _epd("c3d5"): [LineEval("e8d7", -900, ("e8d7",))],
        _epd("c3d5", "e8d7"): [LineEval("h2h4", 900, ("h2h4",)), LineEval("e1e2", 100, ("e1e2",))],
        _epd("c3d5", "e8d7", "h2h4"): [LineEval("d7e6", -900, ("d7e6",))],
        _epd("c3d5", "e8d7", "h2h4", "d7e6"): [LineEval("h4h5", 900, ("h4h5",)), LineEval("e1e2", 100, ("e1e2",))],
        _epd("c3d5", "e8d7", "h2h4", "d7e6", "h4h5"): [LineEval("e6d6", -900, ("e6d6",))],
        # gap de 100 cp: acabou o lance único
        _epd("c3d5", "e8d7", "h2h4", "d7e6", "h4h5", "e6d6"): [
            LineEval("h5h6", 900, ("h5h6",)), LineEval("e1e2", 800, ("e1e2",)),
        ],
    }


def _puzzle(**overrides) -> Puzzle:
    defaults = dict(
        kind="punish", source="own", fen_start=HANGING_QUEEN, side_to_move="white",
        solution=json.dumps({"moves": [{"uci": "c3d5", "by": "solver", "alternatives": []}]}),
        end_reason="material_gain", theme="hanging_piece", category="rapid", solver_moves=1,
        created_at=datetime(2026, 9, 1), srs_ease=2.3, srs_interval_days=21, srs_lapses=2,
        srs_due_at=datetime(2026, 12, 1), srs_last_reviewed_at=datetime(2026, 9, 10),
    )
    defaults.update(overrides)
    return Puzzle(**defaults)


SETTINGS = AppSettings(puzzle_depth=10)


def test_extend_all_lengthens_the_line_and_keeps_the_review_history(db_session):
    puzzle = _puzzle(is_leech=True)
    db_session.add(puzzle)
    db_session.flush()
    db_session.add(Review(puzzle_id=puzzle.id, result="correct", ease=2.3, interval_days=21,
                          due_at=datetime(2026, 12, 1), lapses=2))
    db_session.commit()
    puzzle_id = puzzle.id

    n = extend_all(db_session, FakeEngine(_extend_script()), SETTINGS)

    assert n == {"examinados": 1, "estendidos": 1, "falhas": 0}
    novo = db_session.get(Puzzle, puzzle_id)
    assert novo is not None and novo.id == puzzle_id  # o mesmo exercício, não um recriado
    assert [(m["uci"], m["by"]) for m in novo.solution_data["moves"]] == [
        ("c3d5", "solver"), ("e8d7", "engine"), ("h2h4", "solver"), ("d7e6", "engine"), ("h4h5", "solver"),
    ]
    assert novo.solver_moves == 3
    # o histórico de revisão sobrevive à extensão
    assert novo.srs_due_at == datetime(2026, 12, 1) and novo.srs_interval_days == 21
    assert novo.srs_ease == 2.3 and novo.srs_lapses == 2
    assert novo.srs_last_reviewed_at == datetime(2026, 9, 10)
    assert novo.in_queue is True and novo.is_leech is True
    assert db_session.scalar(select(func.count(Review.id))) == 1


def test_extend_all_refaz_a_assinatura_quando_a_solucao_muda(db_session):
    """Achado 1 da revisão: `extend_all` reescreve `solution`/`solver_moves` mas a assinatura
    gravada ficava com os hashes da solução curta para sempre (`garantir_assinatura` só refaz
    por versão, não por conteúdo)."""
    puzzle = _puzzle()
    db_session.add(puzzle)
    db_session.commit()
    antiga = garantir_assinatura(db_session, puzzle)
    assert antiga is not None
    texto_antigo = antiga.texto_completo

    extend_all(db_session, FakeEngine(_extend_script()), SETTINGS)

    novo = db_session.get(Puzzle, puzzle.id)
    nova = db_session.get(PuzzleSignature, puzzle.id)
    esperado = assinar_proprio(novo).completo()
    assert nova is not None and nova.texto_completo == esperado and nova.texto_completo != texto_antigo


def test_extend_all_keeps_the_other_keys_of_the_solution(db_session):
    db_session.add(_puzzle(solution=json.dumps({
        "moves": [{"uci": "c3d5", "by": "solver", "alternatives": []}],
        "comments": {"0": "ganha a dama"}, "wrong_moves": {"e1e2": "muito lento"},
        "shapes": {"start": ["Gd5"]}, "intro": "branco joga e ganha",
    })))
    db_session.commit()

    extend_all(db_session, FakeEngine(_extend_script()), SETTINGS)

    data = db_session.scalars(select(Puzzle)).one().solution_data
    assert len(data["moves"]) == 5
    assert data["comments"] == {"0": "ganha a dama"} and data["wrong_moves"] == {"e1e2": "muito lento"}
    assert data["shapes"] == {"start": ["Gd5"]} and data["intro"] == "branco joga e ganha"


def test_extend_all_skips_mate_and_puzzles_from_other_sources(db_session):
    db_session.add_all([
        _puzzle(kind="avoid", end_reason="mate", theme="mate_in_1"),
        _puzzle(source="lichess", external_id="abc123"),
    ])
    db_session.commit()
    fake = FakeEngine(_extend_script())

    assert extend_all(db_session, fake, SETTINGS) == {"examinados": 0, "estendidos": 0, "falhas": 0}
    assert fake.calls == []  # nem chega a perguntar à engine
    for p in db_session.scalars(select(Puzzle)):
        assert len(p.solution_data["moves"]) == 1


def test_extend_all_stops_in_the_middle_when_asked(db_session):
    db_session.add_all([
        _puzzle(kind="punish", created_at=datetime(2026, 9, 1)),
        _puzzle(kind="avoid", created_at=datetime(2026, 9, 2)),
    ])
    db_session.commit()
    chamadas: list[int] = []

    def should_stop() -> bool:
        chamadas.append(1)
        return len(chamadas) > 1  # deixa o primeiro exercício passar e para no segundo

    n = extend_all(db_session, FakeEngine(_extend_script()), SETTINGS, should_stop=should_stop)

    assert n == {"examinados": 1, "estendidos": 1, "falhas": 0}
    primeiro = db_session.scalars(select(Puzzle).where(Puzzle.kind == "punish")).one()
    segundo = db_session.scalars(select(Puzzle).where(Puzzle.kind == "avoid")).one()
    assert len(primeiro.solution_data["moves"]) == 5  # o que já foi estendido fica
    assert len(segundo.solution_data["moves"]) == 1


TWO_WAYS = "4k3/8/8/3q4/8/2N1N3/7P/4K3 w - - 0 1"  # os dois cavalos tomam a dama
MATE_AFTER_GAIN = "6k1/5ppp/8/3q4/8/2N5/8/R3K3 w - - 0 1"  # Cxd5 ganha a dama e Ta8 é mate


def _epd_de(fen: str, *ucis: str) -> str:
    b = chess.Board(fen)
    for u in ucis:
        b.push_uci(u)
    return b.epd()


def test_extend_all_clears_the_alternatives_of_the_move_that_was_last(db_session):
    """Invariante: só o último lance da solução tem alternativas. A captura que deixou de
    ser o fim da linha perde as dela — a alternativa levaria o aluno para longe da
    continuação gravada."""
    db_session.add(_puzzle(fen_start=TWO_WAYS, solution=json.dumps(
        {"moves": [{"uci": "c3d5", "by": "solver", "alternatives": ["e3d5"]}]})))
    db_session.commit()
    script = {
        _epd_de(TWO_WAYS, "c3d5"): [LineEval("e8d7", -900, ("e8d7",))],
        _epd_de(TWO_WAYS, "c3d5", "e8d7"): [
            LineEval("h2h4", 900, ("h2h4",)), LineEval("e1e2", 100, ("e1e2",)),
        ],
        _epd_de(TWO_WAYS, "c3d5", "e8d7", "h2h4"): [LineEval("d7e6", -900, ("d7e6",))],
        # o gap cai: acabou o lance único
        _epd_de(TWO_WAYS, "c3d5", "e8d7", "h2h4", "d7e6"): [
            LineEval("h4h5", 900, ("h4h5",)), LineEval("e1e2", 800, ("e1e2",)),
        ],
    }

    extend_all(db_session, FakeEngine(script), SETTINGS)

    moves = db_session.scalars(select(Puzzle)).one().solution_data["moves"]
    assert [m["uci"] for m in moves] == ["c3d5", "e8d7", "h2h4"]
    assert [m.get("alternatives") for m in moves] == [[], [], []]


def test_extend_all_marks_mate_and_recalculates_the_theme(db_session):
    db_session.add(_puzzle(fen_start=MATE_AFTER_GAIN, solution=json.dumps(
        {"moves": [{"uci": "c3d5", "by": "solver", "alternatives": []}]})))
    db_session.commit()
    script = {
        _epd_de(MATE_AFTER_GAIN, "c3d5"): [LineEval("g8h8", -900, ("g8h8",))],
        _epd_de(MATE_AFTER_GAIN, "c3d5", "g8h8"): [
            LineEval("a1a8", MATE_SCORE - 1, ("a1a8",)), LineEval("e1e2", 900, ("e1e2",)),
        ],
    }

    assert extend_all(db_session, FakeEngine(script), SETTINGS) == {
        "examinados": 1, "estendidos": 1, "falhas": 0}

    novo = db_session.scalars(select(Puzzle)).one()
    assert [m["uci"] for m in novo.solution_data["moves"]] == ["c3d5", "g8h8", "a1a8"]
    # a linha agora acaba em mate: o exercício deixa de ser o de ganho de material
    assert novo.end_reason == "mate" and novo.theme == "mate_in_2"
    assert novo.solver_moves == 2


def test_extend_all_skips_the_puzzle_when_the_engine_fails(db_session):
    db_session.add_all([
        _puzzle(kind="punish", created_at=datetime(2026, 9, 1)),
        _puzzle(kind="avoid", created_at=datetime(2026, 9, 2)),
    ])
    db_session.commit()
    fake = FakeEngine(_extend_script())
    fake.fail_next = True  # a engine morre no primeiro exercício e volta para o segundo

    n = extend_all(db_session, fake, SETTINGS)

    assert n == {"examinados": 1, "estendidos": 1, "falhas": 1}
    primeiro = db_session.scalars(select(Puzzle).where(Puzzle.kind == "punish")).one()
    segundo = db_session.scalars(select(Puzzle).where(Puzzle.kind == "avoid")).one()
    assert len(primeiro.solution_data["moves"]) == 1  # pulado, intacto
    assert len(segundo.solution_data["moves"]) == 5


def test_extending_twice_changes_nothing(db_session):
    db_session.add(_puzzle())
    db_session.commit()
    extend_all(db_session, FakeEngine(_extend_script()), SETTINGS)
    antes = db_session.scalars(select(Puzzle)).one().solution_data["moves"]

    n = extend_all(db_session, FakeEngine(_extend_script()), SETTINGS)

    assert n == {"examinados": 1, "estendidos": 0, "falhas": 0}
    assert db_session.scalars(select(Puzzle)).one().solution_data["moves"] == antes


def test_extend_all_accepts_a_solution_ending_in_an_opponent_move(db_session):
    """Solução legada que termina com a resposta do adversário: a extensão continua dali."""
    db_session.add(_puzzle(solver_moves=1, solution=json.dumps({"moves": [
        {"uci": "c3d5", "by": "solver", "alternatives": []},
        {"uci": "e8d7", "by": "engine", "alternatives": []},
    ]})))
    db_session.commit()

    assert extend_all(db_session, FakeEngine(_extend_script()), SETTINGS) == {
        "examinados": 1, "estendidos": 1, "falhas": 0}

    novo = db_session.scalars(select(Puzzle)).one()
    assert [m["uci"] for m in novo.solution_data["moves"]] == [
        "c3d5", "e8d7", "h2h4", "d7e6", "h4h5"]
    assert novo.solver_moves == 3


def test_extend_all_survives_a_move_without_the_by_key(db_session):
    """Registro fora do formato não derruba o job inteiro."""
    db_session.add(_puzzle(solution=json.dumps({"moves": [{"uci": "c3d5"}]})))
    db_session.commit()

    n = extend_all(db_session, FakeEngine(_extend_script()), SETTINGS)

    assert n == {"examinados": 1, "estendidos": 1, "falhas": 0}
    novo = db_session.scalars(select(Puzzle)).one()
    assert [m["uci"] for m in novo.solution_data["moves"]] == [
        "c3d5", "e8d7", "h2h4", "d7e6", "h4h5"]
    assert novo.solver_moves == 2  # só os lances da extensão se dizem do aluno


# --- erro do adversário já castigado na partida não vira exercício -----------------------


def _punish_fixo(monkeypatch, alternativas=()):
    """`generate_punish` dublado: a solução começa com Nxd5 (c3d5)."""
    draft = PuzzleDraft(fen_start="4k3/8/8/3q4/8/2N5/7P/4K3 w - - 0 1", side_to_move="white",
                        moves=[SolutionMove("c3d5", "solver", list(alternativas))],
                        end_reason="material_gain", solver_moves=1)
    monkeypatch.setattr(puzzle_service, "generate_punish", lambda *a, **k: draft)
    monkeypatch.setattr(puzzle_service, "_is_trivial_punish", lambda *a, **k: False)


def _erro_do_adversario(**over) -> Position:
    return _pos(fen="3qk3/8/8/8/8/2N5/7P/4K3 b - - 0 1", move_played="Qd5", move_uci="d8d5",
                eval_after=-900, ply=10, **over)


def test_erro_do_adversario_que_o_usuario_castigou_nao_vira_punir(monkeypatch):
    _punish_fixo(monkeypatch)
    assert build_drafts(_erro_do_adversario(), FakeEngine(), CFG, reply_uci="c3d5") == []


def test_erro_do_adversario_que_o_usuario_deixou_passar_vira_punir(monkeypatch):
    _punish_fixo(monkeypatch)
    kinds = [k for k, _ in build_drafts(_erro_do_adversario(), FakeEngine(), CFG, reply_uci="h2h3")]
    assert kinds == ["punish"]
    # sem resposta conhecida (erro no último lance da partida) o exercício também entra
    assert [k for k, _ in build_drafts(_erro_do_adversario(), FakeEngine(), CFG)] == ["punish"]


def test_resposta_que_e_alternativa_aceita_tambem_conta_como_achada(monkeypatch):
    _punish_fixo(monkeypatch, alternativas=["e1e2"])
    assert build_drafts(_erro_do_adversario(), FakeEngine(), CFG, reply_uci="e1e2") == []


def test_punir_irmao_de_um_erro_meu_nao_depende_da_resposta(monkeypatch):
    _punish_fixo(monkeypatch)
    monkeypatch.setattr(puzzle_service, "generate_avoid", lambda *a, **k: None)
    kinds = [k for k, _ in build_drafts(_erro_do_adversario(mistake_by="me"), FakeEngine(), CFG, reply_uci="c3d5")]
    assert kinds == ["punish"]


def test_draft_puzzles_passa_o_lance_seguinte_da_partida(monkeypatch):
    _punish_fixo(monkeypatch)
    erro = _erro_do_adversario()
    achou = _pos(ply=11, move_played="Nxd5", move_uci="c3d5", is_mistake=False, mistake_by=None)
    assert draft_puzzles([erro, achou], FakeEngine(), CFG) == []
    passou = _pos(ply=11, move_played="h3", move_uci="h2h3", is_mistake=False, mistake_by=None)
    assert [k for _, k, _ in draft_puzzles([erro, passou], FakeEngine(), CFG)] == ["punish"]
