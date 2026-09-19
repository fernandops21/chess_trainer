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


def test_svg_realca_casas_com_cor_e_nao_com_x():
    """O X padrão do `chess.svg` em cima do rei adversário lia como "riscado/capturado": as casas
    da assinatura (rei adversário, chegadas) são realçadas com cor, sem marca nenhuma por cima."""
    import re
    from chess_trainer.core.golpes.imagem import COR_CHEGADA, COR_REI
    svg = svg_do_golpe(FEN_FRANCESA, ["d3b5", "e8e7", "d1d4"])
    assert 'href="#xx"' not in svg and 'id="xx"' not in svg
    # o chess.svg separa "#rrggbbaa" em tom + opacidade: um retângulo translúcido por casa
    realces = re.findall(r'<rect[^>]*fill="(#[0-9a-f]{6})" opacity="([0-9.]+)"', svg)
    tons = [tom for tom, _ in realces]
    assert tons.count(COR_REI[:7]) == 1            # a casa do rei adversário (e8)
    assert tons.count(COR_CHEGADA[:7]) == 2        # as chegadas dos dois lances (b5 e d4)
    assert all(0 < float(op) < 1 for _, op in realces)  # translúcido: a peça continua visível


def test_rei_so_e_realcado_quando_o_golpe_da_xeque():
    """Num final de torre em que a jogada é a torre e a promoção, o rei adversário é cenário:
    realçá-lo sugere que ele participa do golpe. Só entra quando algum lance dá xeque ou mate."""
    import re
    from chess_trainer.core.golpes.imagem import COR_REI
    tons = lambda svg: [t for t, _ in re.findall(r'<rect[^>]*fill="(#[0-9a-f]{6})" opacity="([0-9.]+)"', svg)]
    # torre b2-d2 e peão a2-a1=Q, sem xeque nenhum: rei branco em e4 não é realçado
    sem_xeque = svg_do_golpe("8/3P4/1R6/6P1/1p2K3/4P2P/pr4k1/8 b - - 0 1", ["b2d2", "b6b8", "a2a1q"])
    assert COR_REI[:7] not in tons(sem_xeque)
    # a francesa: 9.Bb5+ dá xeque, o rei de e8 faz parte do golpe
    assert tons(svg_do_golpe(FEN_FRANCESA, ["d3b5", "e8e7", "d1d4"])).count(COR_REI[:7]) == 1
