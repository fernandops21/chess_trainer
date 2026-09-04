import chess

from chess_trainer.core.puzzles.material import floor_to_piece, material, material_balance


def test_material_and_balance():
    board = chess.Board("4k3/8/8/3q4/8/2N5/8/4K3 w - - 0 1")
    assert material(board, chess.WHITE) == 3 and material(board, chess.BLACK) == 9
    assert material_balance(board, chess.WHITE) == -6
    assert material_balance(board, chess.BLACK) == 6
    assert material_balance(chess.Board(), chess.WHITE) == 0


def test_floor_to_piece():
    assert floor_to_piece(0.5) == 0
    assert floor_to_piece(1.0) == 1
    assert floor_to_piece(2.9) == 1
    assert floor_to_piece(3.0) == 3
    assert floor_to_piece(4.5) == 3
    assert floor_to_piece(5.0) == 5
    assert floor_to_piece(8.9) == 5
    assert floor_to_piece(9.0) == 9
    assert floor_to_piece(20.0) == 9
