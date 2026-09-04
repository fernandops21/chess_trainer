import chess
def chk(name, fen, cond): print(("OK  " if cond else "FAIL"), name)
b=chess.Board("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3"); chk("fools mate", b.fen(), b.is_checkmate())
b=chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"); chk("stalemate", b.fen(), b.is_stalemate())
# hanging queen
b=chess.Board("4k3/8/8/3q4/8/2N5/8/4K3 w - - 0 1"); chk("hq valid", b.fen(), b.is_valid()); m=chess.Move.from_uci("c3d5"); chk("hq Nxd5 legal", 0, m in b.legal_moves); chk("hq d5 undefended", 0, not b.is_attacked_by(chess.BLACK, chess.D5)); b.push(m); chk("hq e8d7 legal",0, chess.Move.from_uci("e8d7") in b.legal_moves)
# mate in 2
b=chess.Board("2r3k1/5ppp/8/8/Q7/8/8/4R1K1 w - - 0 1"); chk("m2 valid",0,b.is_valid()); b.push_uci("e1e8"); chk("m2 check",0,b.is_check()); chk("m2 only Rxe8",0,[x.uci() for x in b.legal_moves]==["c8e8"]); b.push_uci("c8e8"); b.push_uci("a4e8"); chk("m2 mate",0,b.is_checkmate())
# two captures
b=chess.Board("4k3/8/8/3q4/8/2N1N3/8/4K3 w - - 0 1"); chk("tc valid",0,b.is_valid()); chk("tc both legal",0, all(chess.Move.from_uci(u) in b.legal_moves for u in ("c3d5","e3d5")))
# recapture
b=chess.Board("8/8/4k3/3q4/8/8/8/3RK3 w - - 0 1"); chk("rc valid",0,b.is_valid()); b.push_uci("d1d5"); chk("rc Kxd5 legal",0,chess.Move.from_uci("e6d5") in b.legal_moves); b.push_uci("e6d5"); chk("rc insufficient -> game over",0,b.is_game_over())
# vague
b=chess.Board("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"); chk("vague valid",0,b.is_valid()); chk("vague e1d1 legal",0,chess.Move.from_uci("e1d1") in b.legal_moves)
# mate in 1
b=chess.Board("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1"); chk("m1 valid",0,b.is_valid()); b.push_uci("a1a8"); chk("m1 mate",0,b.is_checkmate())
b=chess.Board("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1"); chk("m1 a1a7 legal",0,chess.Move.from_uci("a1a7") in b.legal_moves)
# fork
b=chess.Board("3k4/8/8/q1N5/8/8/8/6K1 w - - 0 1"); chk("fork valid",0,b.is_valid()); chk("fork not in check",0,not b.is_check()); b.push_uci("c5b7"); chk("fork check",0,b.is_check()); chk("fork attacks a5",0,chess.A5 in b.attacks(chess.B7)); chk("fork Kc8 legal",0,chess.Move.from_uci("d8c8") in b.legal_moves); b.push_uci("d8c8"); chk("fork Nxa5",0,chess.Move.from_uci("b7a5") in b.legal_moves)
# pin
b=chess.Board("4k3/8/2n5/8/8/8/8/4KB2 w - - 0 1"); chk("pin valid",0,b.is_valid()); chk("pin not before",0,not b.is_pinned(chess.BLACK,chess.C6)); b.push_uci("f1b5"); chk("pin after",0,b.is_pinned(chess.BLACK,chess.C6))
# discovered
b=chess.Board("7k/4q3/8/8/8/4B3/8/4R1K1 w - - 0 1"); chk("disc valid",0,b.is_valid()); chk("disc not check",0,not b.is_check()); b.push_uci("e3d4"); chk("disc check",0,b.is_check()); chk("disc rook attacks e7",0,chess.E7 in b.attacks(chess.E1)); chk("disc d4 attacks h8 only king",0,chess.H8 in b.attacks(chess.D4) and chess.E7 not in b.attacks(chess.D4)); chk("disc queen not pinned",0,not b.is_pinned(chess.BLACK,chess.E7)); chk("disc Qf6 legal",0,chess.Move.from_uci("e7f6") in b.legal_moves); b.push_uci("e7f6"); chk("disc Bxf6",0,chess.Move.from_uci("d4f6") in b.legal_moves)
# avoid fen
b=chess.Board("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"); chk("avoid valid",0,b.is_valid() and chess.Move.from_uci("f1b5") in b.legal_moves)
# scholar pgn
import chess.pgn, io
g=chess.pgn.read_game(io.StringIO("1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0")); mv=list(g.mainline_moves()); chk("scholar 7 plies",0,len(mv)==7); bb=g.board(); [bb.push(m) for m in mv]; chk("scholar mate",0,bb.is_checkmate())
# fixture PGNs parse
for p in ["[White \"a\"]\n[Result \"0-1\"]\n\n1. f3 e5 2. g4 Qh4# 0-1\n", "[White \"a\"]\n[Result \"1/2-1/2\"]\n[Variant \"Chess960\"]\n\n1. e4 e5 1/2-1/2\n"]:
    h=chess.pgn.read_headers(io.StringIO(p)); chk("headers "+h["Result"],0,True)
# epd stable key
b=chess.Board(); print("epd:", b.epd())
# material
from collections import Counter
b=chess.Board("4k3/8/8/3q4/8/2N5/8/4K3 w - - 0 1"); print("pieces white knight:", len(b.pieces(chess.KNIGHT, chess.WHITE)))
