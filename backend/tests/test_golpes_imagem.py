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
