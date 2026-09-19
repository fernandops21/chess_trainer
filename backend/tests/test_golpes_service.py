import json

from chess_trainer.config import get_setting
from chess_trainer.core.golpes.assinatura import VERSAO_ASSINATURA, assinar
from chess_trainer.core.golpes.service import (
    Irmao,
    assinar_lichess,
    assinar_proprio,
    assinatura_de,
    cobertura,
    escolher_por_rating,
    espalhar,
    garantir_assinatura,
    irmaos,
    preparar,
)
from chess_trainer.core.models import LichessPuzzle, LichessPuzzleSignature, Position, Puzzle, PuzzleSignature
from tests.factories import make_puzzle
from tests.test_models import _game

# Puzzle do Lichess: `fen` é a posição ANTES do lance de preparação (moves[0]); quem soluciona joga depois dele.
# Aqui: pretas a jogar, o preparo é 8...Qb6xd4?? (toma o cavalo achando o peão de graça) e as brancas
# solucionam com 9.Bb5+ descobrindo a dama de d1 contra d4 — a armadilha da francesa.
FEN_FRANCESA_ANTES = "r1b1kbnr/pp3ppp/1q2p3/3pP3/3N4/3B4/PP3PPP/RNBQK2R b KQkq - 0 8"
MOVES_FRANCESA = "b6d4 d3b5 e8e7 d1d4"
# Mate do pastor: pretas a jogar, preparo 4...Nf6?? e Qxf7#
FEN_PASTOR_ANTES = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 4 4"
MOVES_PASTOR = "g8f6 h5f7"
FEN_PASTOR_START = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 5 5"


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


def test_gemeo_adotado_por_capitulo_recalcula_a_assinatura(db_session):
    """Um puzzle de estudo órfão (sem capítulo) com a mesma posição inicial de um capítulo
    novo é adotado por ele (`_upsert_puzzle`, ramo "gêmeo sem dono"); a solução pode ter
    mudado, então a assinatura antiga não pode sobreviver à adoção (achado do fix round 1)."""
    from chess_trainer.core.models import Study, StudyChapter, new_id
    from chess_trainer.core.studies.service import ImportReport, _upsert_puzzle

    fen = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
    sol_antiga = {"moves": [{"uci": "h5f7", "by": "solver", "alternatives": []}], "explanation_pv": []}
    orfao = make_puzzle(db_session, fen=fen, kind="punish", solution=sol_antiga)
    orfao.source = "study"
    orfao.chapter_id = None
    db_session.commit()
    antiga = garantir_assinatura(db_session, orfao)
    assert antiga.texto_completo == "Ke8 | Q h5-f7 xP #"

    study = Study(id=new_id(), title="E", author="", source_url="s", origin="local")
    db_session.add(study)
    db_session.flush()
    chapter = StudyChapter(id=new_id(), study_id=study.id, order=1, name="C", fen=fen)
    db_session.add(chapter)
    db_session.flush()

    sol_nova = {"moves": [{"uci": "h5e5", "by": "solver", "alternatives": []}], "explanation_pv": []}
    _upsert_puzzle(db_session, chapter, fen, sol_nova, ImportReport())

    assert chapter.puzzle_id == orfao.id
    atualizado = db_session.get(Puzzle, orfao.id)
    esperado = assinar_proprio(atualizado).completo()
    sig = db_session.get(PuzzleSignature, orfao.id)
    assert sig is not None and sig.texto_completo == esperado and sig.texto_completo != antiga.texto_completo


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
    # segunda rodada: só o "ruim" continua pendente (retentado, sem exclusão persistida)
    assert preparar(db_session, lambda *a: None) == 1
    # versão antiga: refaz p0, e o "ruim" segue retentado junto
    s = db_session.get(LichessPuzzleSignature, "p0"); s.versao = 0; db_session.commit()
    assert preparar(db_session, lambda *a: None) == 2


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


def test_persist_draft_grava_assinatura(db_session):
    from chess_trainer.core.puzzles.generator import PuzzleDraft, SolutionMove
    from chess_trainer.core.puzzles.service import persist_draft

    fen = "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
    game = _game()
    db_session.add(game)
    db_session.flush()
    pos = Position(game_id=game.id, ply=7, fen=fen, move_played="Nc6", move_uci="b8c6",
                   eval_before=0, eval_after=-900, best_move="h5f7", best_eval=900,
                   is_mistake=True, mistake_level="blunder", mistake_by="opponent")
    db_session.add(pos)
    db_session.flush()
    draft = PuzzleDraft(fen_start=fen, side_to_move="white", moves=[SolutionMove("h5f7", "solver")],
                        end_reason="mate", solver_moves=1)
    puzzle = persist_draft(db_session, pos, game, "punish", draft)
    assert puzzle is not None
    assert db_session.get(PuzzleSignature, puzzle.id) is not None


def test_espalhar_pega_do_facil_ao_dificil():
    assert espalhar(list(range(10)), 5) == [0, 2, 4, 7, 9]
    assert espalhar([1, 2, 3], 5) == [1, 2, 3]
    assert espalhar([], 3) == []


def test_escolher_por_rating_so_a_faixa():
    """Cabe tudo na faixa preferida: espalha (fácil ao difícil) sem sair dela."""
    cands = [(f"p{r}", r) for r in (800, 900, 1000, 1100, 1200)]
    assert escolher_por_rating(cands, 3, lo=800, hi=1400) == ["p800", "p1000", "p1200"]


def test_escolher_por_rating_completa_de_cima():
    """Faltando na faixa, completa primeiro com os de cima (subindo, mais perto primeiro)."""
    cands = [("baixo1", 500), ("dentro", 900), ("cima1", 1500), ("cima2", 1600)]
    assert escolher_por_rating(cands, 3, lo=800, hi=1400) == ["dentro", "cima1", "cima2"]


def test_escolher_por_rating_completa_de_cima_e_de_baixo():
    """De cima esgotado, completa de baixo (descendo, mais perto primeiro)."""
    cands = [("baixo1", 500), ("baixo2", 700), ("dentro", 900), ("cima1", 1500)]
    assert escolher_por_rating(cands, 4, lo=800, hi=1400) == ["dentro", "cima1", "baixo2", "baixo1"]


def test_escolher_por_rating_vazio():
    assert escolher_por_rating([], 3, lo=800, hi=1400) == []


def test_escolher_por_rating_k_maior_que_tudo():
    cands = [("a", 900), ("b", 1500)]
    assert escolher_por_rating(cands, 10, lo=800, hi=1400) == ["a", "b"]


def test_irmaos_ignora_rating_para_achar_a_camada(db_session):
    """Achado do bug: os irmãos exatos ('inteira') existem só bem acima da faixa preferida; a
    busca não pode declarar esse degrau vazio e cair para o esqueleto — quem decide o degrau é o
    golpe, o rating só escolhe quem aparece no bloco."""
    from chess_trainer.core.golpes.service import linha_de_assinatura
    for i in range(3):
        db_session.add(pastor(f"m{i}", rating=700 + 100 * i))  # 700, 800, 900: acima da faixa
    db_session.add(pastor("esq", rating=150))  # dentro da faixa, mas só esqueleto
    db_session.commit()
    a = assinar(FEN_PASTOR_START, ["h5f7"])
    for pid in ("m0", "m1", "m2"):
        db_session.add(linha_de_assinatura(a, LichessPuzzleSignature, pid))
    esq = linha_de_assinatura(a, LichessPuzzleSignature, "esq")
    esq.destinos, esq.destinos_esp = 12345, 54321  # mesmo esqueleto e zona, outras casas
    db_session.add(esq)
    db_session.commit()

    r = irmaos(db_session, FEN_PASTOR_START, ["h5f7"], rating=200, abaixo=100, acima=100, excluir=set(), k=3)
    assert [x.tier for x in r] == ["inteira"] * 3
    assert {x.row.id for x in r} == {"m0", "m1", "m2"}


def test_irmaos_prefere_a_faixa_e_fica_ascendente(db_session):
    """Seis 'mesmo golpe' (ratings 700..1200): com rating=900, abaixo=100, acima=500 a faixa
    preferida é 800..1400, então o bloco fica em 800..1200, ascendente."""
    from chess_trainer.core.golpes.service import linha_de_assinatura
    for i in range(6):
        db_session.add(pastor(f"m{i}", rating=700 + 100 * i))
    db_session.commit()
    a = assinar(FEN_PASTOR_START, ["h5f7"])
    for i in range(6):
        db_session.add(linha_de_assinatura(a, LichessPuzzleSignature, f"m{i}"))
    db_session.commit()

    r = irmaos(db_session, FEN_PASTOR_START, ["h5f7"], rating=900, abaixo=100, acima=500, excluir=set(), k=5)
    assert [x.row.rating for x in r] == [800, 900, 1000, 1100, 1200]
    assert "m0" not in {x.row.id for x in r}  # 700: fora da faixa e não precisou entrar


def test_irmaos_ordena_o_bloco_por_rating_mesmo_cruzando_camadas(db_session):
    """Um de cada degrau, ratings entrelaçados: a ordem final do bloco é por rating, não pela
    ordem em que a cascata visitou os degraus."""
    from chess_trainer.core.golpes.service import linha_de_assinatura
    db_session.add(pastor("m0", rating=1000))
    db_session.add(pastor("esp", rating=900))
    db_session.add(pastor("esq", rating=1100))
    db_session.commit()
    a = assinar(FEN_PASTOR_START, ["h5f7"])
    db_session.add(linha_de_assinatura(a, LichessPuzzleSignature, "m0"))
    db_session.add(linha_de_assinatura(a.espelhada(), LichessPuzzleSignature, "esp"))
    esq = linha_de_assinatura(a, LichessPuzzleSignature, "esq")
    esq.destinos, esq.destinos_esp = 12345, 54321  # mesmo esqueleto e zona, outras casas
    db_session.add(esq)
    db_session.commit()

    r = irmaos(db_session, FEN_PASTOR_START, ["h5f7"], rating=1000, abaixo=200, acima=200, excluir=set(), k=3)
    assert [x.row.id for x in r] == ["esp", "m0", "esq"]
    assert [x.tier for x in r] == ["espelho", "inteira", "esqueleto"]


def test_irmaos_respeita_popularidade(db_session):
    db_session.add(pastor("pop", popularity=10))
    db_session.commit()
    preparar(db_session, lambda *a: None)
    assert irmaos(db_session, FEN_PASTOR_START, ["h5f7"], rating=1500, abaixo=1500, acima=1500,
                  excluir=set()) == []


def test_irmaos_respeita_o_limite_de_candidatos(db_session, monkeypatch):
    """Com o limite baixo, só os mais próximos do centro da faixa preferida entram — mesmo pedindo
    mais e havendo mais no banco: o corte é feito na consulta (mais perto do centro), antes de
    espalhar e de carregar as linhas escolhidas."""
    from chess_trainer.core.golpes.service import linha_de_assinatura
    monkeypatch.setattr("chess_trainer.core.golpes.service.LIMITE_CANDIDATOS", 3)
    for i in range(6):
        db_session.add(pastor(f"lim{i}", rating=700 + 100 * i))  # 700..1200
    db_session.commit()
    a = assinar(FEN_PASTOR_START, ["h5f7"])
    for i in range(6):
        db_session.add(linha_de_assinatura(a, LichessPuzzleSignature, f"lim{i}"))
    db_session.commit()

    # faixa 650..1250, centro 950: os três mais próximos do centro são 900, 1000 e 800
    r = irmaos(db_session, FEN_PASTOR_START, ["h5f7"], rating=950, abaixo=300, acima=300, excluir=set(), k=6)
    assert [x.row.rating for x in r] == [800, 900, 1000]


# --- trechos na cascata (spec golpes trechos §5) -----------------------------

FEN_QXD4 = "r1b2bnr/pp2kppp/4p3/1B1pP3/3q4/8/PP3PPP/RNBQK2R w KQ - 2 10"  # francesa, só falta Qxd4
FEN_BEIJO_PUZZLE = "r1bq1rk1/pp1nbppp/2p1p3/3pP3/3P4/2PB1N2/PP3PPP/R1BQ1RK1 w - - 0 11"
MOVES_BEIJO = ["d3h7", "g8h7", "f3g5", "h7g8", "d1h5"]  # beijo grego: três lances do solucionador


def test_irmaos_acha_pelo_fim_do_trecho(db_session):
    """Âncora de um lance só: sem "inteira" nem "espelho"/"esqueleto" batendo, o degrau
    `trecho1` acha um candidato cujo ÚLTIMO lance do solucionador é o mesmo golpe — o trecho
    dele fica marcado "fim" (posição na solução DELE, não na da âncora)."""
    from chess_trainer.core.golpes.assinatura import Trecho
    from chess_trainer.core.golpes.service import linha_de_trecho
    ancora = assinar(FEN_QXD4, ["d1d4"])  # golpe de um lance só: Qxd4
    db_session.add(pastor("cand", rating=1000))  # sem NENHUMA assinatura inteira
    db_session.commit()
    # o candidato tem esse mesmo golpe como o lance FINAL de uma solução maior (inicio=1)
    db_session.add(linha_de_trecho(Trecho(inicio=1, n=1, posicao="fim", assinatura=ancora), "cand"))
    db_session.commit()

    r = irmaos(db_session, FEN_QXD4, ["d1d4"], rating=1000, abaixo=500, acima=500, excluir=set(), k=1)
    assert len(r) == 1 and r[0].row.id == "cand"
    assert r[0].procedencia.degrau == "trecho1" and r[0].tier == "trecho1"
    assert r[0].procedencia.posicao == "fim" and r[0].procedencia.nivel == "destinos" and r[0].procedencia.n == 1


def test_irmaos_acha_pelo_inicio_do_trecho(db_session):
    """O mesmo golpe de um lance, mas como o PRIMEIRO lance de uma solução maior do
    candidato: a procedência marca "inicio"."""
    from chess_trainer.core.golpes.assinatura import Trecho
    from chess_trainer.core.golpes.service import linha_de_trecho
    ancora = assinar(FEN_QXD4, ["d1d4"])
    db_session.add(pastor("cand2", rating=1000))
    db_session.commit()
    db_session.add(linha_de_trecho(Trecho(inicio=0, n=1, posicao="inicio", assinatura=ancora), "cand2"))
    db_session.commit()

    r = irmaos(db_session, FEN_QXD4, ["d1d4"], rating=1000, abaixo=500, acima=500, excluir=set(), k=1)
    assert len(r) == 1 and r[0].row.id == "cand2" and r[0].procedencia.posicao == "inicio"


def test_irmaos_tres_lances_cai_para_trecho2_depois_trecho1(db_session):
    """Âncora de três lances sem casamento inteiro nem de três: a cascata cai para `trecho2` e,
    faltando ainda, para `trecho1` (spec §5)."""
    from chess_trainer.core.golpes.assinatura import trechos
    from chess_trainer.core.golpes.service import linha_de_trecho
    meus = {t.n: t for t in trechos(FEN_BEIJO_PUZZLE, MOVES_BEIJO) if t.inicio == 0}
    db_session.add(pastor("t2", rating=1000))
    db_session.add(pastor("t1", rating=1100))
    db_session.commit()
    db_session.add(linha_de_trecho(meus[2], "t2"))
    db_session.add(linha_de_trecho(meus[1], "t1"))
    db_session.commit()

    r = irmaos(db_session, FEN_BEIJO_PUZZLE, MOVES_BEIJO, rating=1000, abaixo=500, acima=500, excluir=set(), k=2)
    assert {x.row.id: x.procedencia.degrau for x in r} == {"t2": "trecho2", "t1": "trecho1"}


def test_esqueleto_de_um_lance_nunca_e_gravado_nem_casa(db_session):
    """O esqueleto de um lance só é ruído (bate com quase tudo) e não entra na busca: a linha do
    trecho de tamanho 1 sempre tem `esqueleto` nulo."""
    from chess_trainer.core.golpes.service import linha_de_trecho, trechos_lichess
    row = lichess("um", FEN_PASTOR_ANTES, MOVES_PASTOR)
    ts = trechos_lichess(row)
    linha = linha_de_trecho(next(t for t in ts if t.n == 1), "um")
    assert linha.esqueleto is None


def test_espelho_trecho1_nunca_entra_no_bloco(db_session):
    """O trecho de um lance espelhado é ruído demais (bate com quase tudo) para o bloco: mesmo
    quando é a única coisa que bateria, `irmaos` nunca o usa (a cascata do bloco não tem esse
    degrau — ele só fazia sentido na rotulagem, removida com "o voto mora no bloco")."""
    from chess_trainer.core.golpes.assinatura import Trecho
    from chess_trainer.core.golpes.service import linha_de_trecho
    ancora = assinar(FEN_PASTOR_START, ["h5f7"])
    db_session.add(pastor("esp1", rating=1000))
    db_session.commit()
    # o candidato só tem o trecho espelhado da âncora, nada mais
    db_session.add(linha_de_trecho(Trecho(inicio=0, n=1, posicao="inicio", assinatura=ancora.espelhada()), "esp1"))
    db_session.commit()

    r = irmaos(db_session, FEN_PASTOR_START, ["h5f7"], rating=1000, abaixo=500, acima=500, excluir=set(), k=5)
    assert "esp1" not in {x.row.id for x in r}
