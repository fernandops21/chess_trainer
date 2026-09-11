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
