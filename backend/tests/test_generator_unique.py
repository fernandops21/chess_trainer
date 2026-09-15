"""Extensão do exercício enquanto o lance do aluno for único (spec 2026-09-15)."""
import chess

from chess_trainer.core.analysis.engine import LineEval
from chess_trainer.core.evals import MATE_SCORE
from chess_trainer.core.puzzles.generator import (
    MAX_EXTENSION_PLIES,
    PuzzleConfig,
    SolutionMove,
    extend_unique_line,
    generate_avoid,
    generate_punish,
)
from tests.fakes import FakeEngine

CFG = PuzzleConfig(depth=10)
M = MATE_SCORE

# Nxd5 ganha a dama; depois o branco ainda tem lances únicos (h4, h5) com o rei preto correndo
HANGING_QUEEN = "4k3/8/8/3q4/8/2N5/7P/4K3 w - - 0 1"
# Nxd5 ganha a dama e, duas jogadas depois, Ta8 é mate
MATE_AFTER_GAIN = "6k1/5ppp/8/3q4/8/2N5/8/R3K3 w - - 0 1"
MATE_IN_2 = "2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 1"
# dois cavalos tomam a dama: a captura tem alternativa próxima e a linha ainda estende (h4, h5)
TWO_WAYS = "4k3/8/8/3q4/8/2N1N3/7P/4K3 w - - 0 1"
# Dg6 afoga o rei preto: fim de jogo no topo do laço da extensão
STALEMATE_IN_1 = "7k/5K2/8/6Q1/8/8/8/8 w - - 0 1"
# Cxd5 ganha a dama e as torres ficam se revezando para sempre: só o teto para a extensão
ENDLESS = "6k1/1r6/8/3q4/8/2N5/8/R5K1 w - - 0 1"


def _after(fen: str, *ucis: str) -> chess.Board:
    b = chess.Board(fen)
    for u in ucis:
        b.push_uci(u)
    return b


def _epd(fen: str, *ucis: str) -> str:
    return _after(fen, *ucis).epd()


def _unique_script() -> dict[str, list[LineEval]]:
    """Nxd5, depois dois lances únicos do branco (h4 e h5) e o gap caindo no terceiro."""
    return {
        chess.Board(HANGING_QUEEN).epd(): [LineEval("c3d5", 900, ("c3d5", "e8d7"))],
        _epd(HANGING_QUEEN, "c3d5"): [LineEval("e8d7", -900, ("e8d7",))],
        _epd(HANGING_QUEEN, "c3d5", "e8d7"): [
            LineEval("h2h4", 900, ("h2h4",)), LineEval("e1e2", 100, ("e1e2",)),
        ],
        _epd(HANGING_QUEEN, "c3d5", "e8d7", "h2h4"): [LineEval("d7e6", -900, ("d7e6",))],
        _epd(HANGING_QUEEN, "c3d5", "e8d7", "h2h4", "d7e6"): [
            LineEval("h4h5", 900, ("h4h5",)), LineEval("e1e2", 100, ("e1e2",)),
        ],
        _epd(HANGING_QUEEN, "c3d5", "e8d7", "h2h4", "d7e6", "h4h5"): [LineEval("e6d6", -900, ("e6d6",))],
        # aqui o segundo lance chega perto: acabou o lance único, o resto é técnica
        _epd(HANGING_QUEEN, "c3d5", "e8d7", "h2h4", "d7e6", "h4h5", "e6d6"): [
            LineEval("h5h6", 900, ("h5h6",)), LineEval("e1e2", 800, ("e1e2",)),
        ],
    }


def _two_ways_script(extensivel: bool = True) -> dict[str, list[LineEval]]:
    """Nc3xd5 com Ne3xd5 pertinho; depois h4, o lance único do branco, e o gap caindo."""
    script = {
        chess.Board(TWO_WAYS).epd(): [
            LineEval("c3d5", 900, ("c3d5", "e8d7")), LineEval("e3d5", 880, ("e3d5", "e8d7")),
        ],
        _epd(TWO_WAYS, "c3d5"): [LineEval("e8d7", -900, ("e8d7",))],
    }
    if extensivel:
        script[_epd(TWO_WAYS, "c3d5", "e8d7")] = [
            LineEval("h2h4", 900, ("h2h4",)), LineEval("e1e2", 100, ("e1e2",)),
        ]
        script[_epd(TWO_WAYS, "c3d5", "e8d7", "h2h4")] = [LineEval("d7e6", -900, ("d7e6",))]
        # aqui o segundo lance chega perto: acabou o lance único e a extensão para
        script[_epd(TWO_WAYS, "c3d5", "e8d7", "h2h4", "d7e6")] = [
            LineEval("h4h5", 900, ("h4h5",)), LineEval("e1e2", 800, ("e1e2",)),
        ]
    else:
        script[_epd(TWO_WAYS, "c3d5", "e8d7")] = []
    return script


def _torres_se_revezando(board: chess.Board) -> list[LineEval]:
    """Cada lado sobe sua torre pela coluna e volta ao começo, em ciclos de tamanhos diferentes
    (6 e 7): a linha nunca repete posição nem termina, então só o teto pode pará-la."""
    coluna, topo, base = ("a", 6, 1) if board.turn == chess.WHITE else ("b", 8, 2)
    origem = next(chess.square_name(sq) for sq in board.pieces(chess.ROOK, board.turn)
                  if chess.square_name(sq)[0] == coluna)
    linha = int(origem[1])
    move = origem + f"{coluna}{linha + 1 if linha < topo else base}"
    return [LineEval(move, 900, (move,))]


def test_line_continues_while_the_move_is_unique_and_stops_when_the_gap_falls():
    fake = FakeEngine(_unique_script())
    draft = generate_punish(chess.Board(HANGING_QUEEN), drop_cp=900, engine=fake, cfg=CFG)
    assert draft is not None and draft.end_reason == "material_gain"
    assert [(m.uci, m.by) for m in draft.moves] == [
        ("c3d5", "solver"), ("e8d7", "engine"), ("h2h4", "solver"), ("d7e6", "engine"), ("h4h5", "solver"),
    ]
    assert draft.solver_moves == 3  # recalculado com os lances da extensão
    # o lance do adversário depois de h5 foi descartado: a solução nunca termina com ele
    assert draft.moves[-1].by == "solver"
    # a extensão pergunta uma linha na vez do adversário e três na vez do aluno
    assert fake.multipvs[-2:] == [1, 3]
    assert fake.depths[-1] == 10 and fake.max_seconds[-1] == CFG.search_seconds


def test_unique_gap_cp_is_respected():
    # com exigência de 900 cp, o gap de 800 do primeiro lance já não é "único": nada é estendido
    fake = FakeEngine(_unique_script())
    draft = generate_punish(chess.Board(HANGING_QUEEN), drop_cp=900, engine=fake,
                            cfg=PuzzleConfig(depth=10, unique_gap_cp=900))
    assert draft is not None and [m.uci for m in draft.moves] == ["c3d5"]


def test_line_ends_on_the_mating_move():
    fake = FakeEngine({
        chess.Board(MATE_AFTER_GAIN).epd(): [LineEval("c3d5", 900, ("c3d5", "g8h8"))],
        _epd(MATE_AFTER_GAIN, "c3d5"): [LineEval("g8h8", -900, ("g8h8",))],
        _epd(MATE_AFTER_GAIN, "c3d5", "g8h8"): [
            LineEval("a1a8", M - 1, ("a1a8",)), LineEval("e1e2", 900, ("e1e2",)),
        ],
    })
    draft = generate_punish(chess.Board(MATE_AFTER_GAIN), drop_cp=900, engine=fake, cfg=CFG)
    assert draft is not None
    assert [m.uci for m in draft.moves] == ["c3d5", "g8h8", "a1a8"]
    # o mate encerra a linha: nenhuma análise depois dele (e a extensão parte da resposta
    # já validada pelo laço, sem buscar de novo a posição depois da solução)
    assert len(fake.calls) == 3
    assert draft.end_reason == "material_gain"  # o exercício continua sendo o de ganho de material


def test_extension_stops_when_the_best_move_no_longer_wins():
    script = _unique_script()
    script[_epd(HANGING_QUEEN, "c3d5", "e8d7")] = [LineEval("h2h4", 50, ("h2h4",))]
    fake = FakeEngine(script)
    draft = generate_punish(chess.Board(HANGING_QUEEN), drop_cp=900, engine=fake, cfg=CFG)
    # o "único" já não ganha (50 < min_solver_eval_cp): a solução fica como estava
    assert draft is not None and [m.uci for m in draft.moves] == ["c3d5"]


def test_trailing_engine_move_is_dropped_when_the_engine_has_no_line():
    script = _unique_script()
    script[_epd(HANGING_QUEEN, "c3d5", "e8d7")] = []
    fake = FakeEngine(script)
    draft = generate_punish(chess.Board(HANGING_QUEEN), drop_cp=900, engine=fake, cfg=CFG)
    assert draft is not None and [(m.uci, m.by) for m in draft.moves] == [("c3d5", "solver")]


def test_mate_puzzle_is_not_extended():
    fake = FakeEngine({
        chess.Board(MATE_IN_2).epd(): [LineEval("e1e8", M - 2, ("e1e8", "c8e8", "a4e8"))],
        _epd(MATE_IN_2, "e1e8"): [LineEval("c8e8", -(M - 1), ("c8e8", "a4e8"))],
        _epd(MATE_IN_2, "e1e8", "c8e8"): [LineEval("a4e8", M - 1, ("a4e8",))],
    })
    draft = generate_punish(chess.Board(MATE_IN_2), drop_cp=5000, engine=fake, cfg=CFG)
    assert draft is not None and draft.end_reason == "mate"
    assert [m.uci for m in draft.moves] == ["e1e8", "c8e8", "a4e8"]
    assert len(fake.calls) == 3  # a linha de mate termina no mate; não há extensão


def test_avoid_is_extended_too():
    script = _unique_script()
    script[chess.Board(HANGING_QUEEN).epd()] = [
        LineEval("c3d5", 900, ("c3d5", "e8d7")), LineEval("e1e2", 0, ("e1e2",)),
    ]
    fake = FakeEngine(script)
    draft = generate_avoid(chess.Board(HANGING_QUEEN), fake, CFG, played_uci="e1e2")
    assert draft is not None and draft.end_reason == "material_gain"
    assert [m.uci for m in draft.moves] == ["c3d5", "e8d7", "h2h4", "d7e6", "h4h5"]
    assert draft.solver_moves == 3


def test_only_the_last_move_of_the_solution_has_alternatives():
    fake = FakeEngine(_two_ways_script())
    draft = generate_punish(chess.Board(TWO_WAYS), drop_cp=900, engine=fake, cfg=CFG)
    assert draft is not None
    assert [m.uci for m in draft.moves] == ["c3d5", "e8d7", "h2h4"]
    # a captura deixou de ser o fim da linha: a alternativa Cexd5 sairia da continuação gravada
    assert [m.alternatives for m in draft.moves] == [[], [], []]


def test_the_capture_keeps_its_alternatives_when_there_is_nothing_to_extend():
    fake = FakeEngine(_two_ways_script(extensivel=False))
    draft = generate_punish(chess.Board(TWO_WAYS), drop_cp=900, engine=fake, cfg=CFG)
    assert draft is not None
    assert [m.uci for m in draft.moves] == ["c3d5"]
    assert draft.moves[-1].alternatives == ["e3d5"]  # último lance: aqui a alternativa vale


def test_the_validated_reply_is_reused_instead_of_a_second_search():
    fake = FakeEngine(_unique_script())
    draft = generate_punish(chess.Board(HANGING_QUEEN), drop_cp=900, engine=fake, cfg=CFG)
    assert draft is not None
    # a posição depois da solução é analisada uma vez só (a resposta do laço); a extensão
    # recebe essa resposta já validada e não busca de novo — outra busca poderia escolher
    # uma defesa diferente da que confirmou o ganho
    assert fake.calls.count(_epd(HANGING_QUEEN, "c3d5")) == 1
    assert [m.uci for m in draft.moves][:2] == ["c3d5", "e8d7"]


def test_without_known_reply_the_extension_searches_the_reply():
    """É assim que o job que alonga os exercícios já gravados chama a extensão."""
    fake = FakeEngine(_unique_script())
    board = _after(HANGING_QUEEN, "c3d5")
    extra = extend_unique_line(board, fake, CFG, chess.WHITE)
    assert [(m.uci, m.by) for m in extra] == [
        ("e8d7", "engine"), ("h2h4", "solver"), ("d7e6", "engine"), ("h4h5", "solver"),
    ]
    assert fake.calls[0] == board.epd() and fake.multipvs[0] == 1


def test_known_reply_out_of_the_board_stops_the_extension():
    fake = FakeEngine(_unique_script())
    extra = extend_unique_line(_after(HANGING_QUEEN, "c3d5"), fake, CFG, chess.WHITE,
                               known_reply=SolutionMove("a1a8", "engine"))
    assert extra == [] and fake.calls == []


def test_extension_stops_on_stalemate():
    board = chess.Board(STALEMATE_IN_1)
    fake = FakeEngine({board.epd(): [LineEval("g5g6", 900, ("g5g6",))]})
    extra = extend_unique_line(board, fake, CFG, chess.WHITE)
    assert [(m.uci, m.by) for m in extra] == [("g5g6", "solver")]
    # fim de jogo no topo do laço: nada é analisado depois do afogamento
    assert len(fake.calls) == 1


def test_endless_unique_line_stops_at_the_ceiling():
    fake = FakeEngine({
        chess.Board(ENDLESS).epd(): [LineEval("c3d5", 900, ("c3d5", "b7b6"))],
        _epd(ENDLESS, "c3d5"): [LineEval("b7b6", -900, ("b7b6",))],
    }, default=_torres_se_revezando)
    draft = generate_punish(chess.Board(ENDLESS), drop_cp=900, engine=fake, cfg=CFG)
    assert draft is not None and draft.end_reason == "material_gain"
    # a captura, a resposta e no máximo MAX_EXTENSION_PLIES lances de extensão
    assert len(draft.moves) <= MAX_EXTENSION_PLIES + 2
    assert len(draft.moves) > 10  # a linha realmente continuou até o teto, não parou antes
    assert draft.moves[-1].by == "solver"
