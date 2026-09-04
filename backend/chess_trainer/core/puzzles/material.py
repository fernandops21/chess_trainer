import chess

PIECE_VALUES: dict[int, int] = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0,
}


def material(board: chess.Board, color: chess.Color) -> int:
    return sum(
        PIECE_VALUES[piece_type] * len(board.pieces(piece_type, color))
        for piece_type in PIECE_VALUES
    )


def material_balance(board: chess.Board, color: chess.Color) -> int:
    return material(board, color) - material(board, not color)


def floor_to_piece(pawns: float) -> int:
    for value in (9, 5, 3, 1):
        if pawns >= value:
            return value
    return 0
