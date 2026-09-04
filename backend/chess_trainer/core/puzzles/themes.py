import chess

from chess_trainer.core.puzzles.generator import SolutionMove
from chess_trainer.core.puzzles.material import PIECE_VALUES


def _attack_pairs(board: chess.Board, attacker: chess.Color, exclude: set[int]) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for sq in chess.SquareSet(board.occupied_co[attacker]):
        if sq in exclude:
            continue
        for target in board.attacks(sq):
            piece = board.piece_at(target)
            if piece and piece.color != attacker and piece.piece_type != chess.PAWN:
                pairs.add((sq, target))
    return pairs


def infer_theme(fen_start: str, moves: list[SolutionMove], end_reason: str) -> str:
    if end_reason == "mate":
        return f"mate_in_{sum(1 for m in moves if m.by == 'solver')}"
    if not moves:
        return "tactic"

    board = chess.Board(fen_start)
    solver = board.turn
    enemy = not solver
    move = chess.Move.from_uci(moves[0].uci)

    if board.is_capture(move) and not board.is_attacked_by(enemy, move.to_square):
        return "hanging_piece"

    moved = board.piece_at(move.from_square)
    moved_value = PIECE_VALUES[moved.piece_type] if moved else 0
    after = board.copy()
    after.push(move)

    targets = 0
    for sq in after.attacks(move.to_square):
        piece = after.piece_at(sq)
        if piece and piece.color == enemy and (piece.piece_type == chess.KING or PIECE_VALUES[piece.piece_type] > moved_value):
            targets += 1
    if targets >= 2:
        return "fork"

    for sq in chess.SquareSet(after.occupied_co[enemy]):
        if after.is_pinned(enemy, sq) and not board.is_pinned(enemy, sq):
            return "pin"

    before_pairs = _attack_pairs(board, solver, exclude={move.from_square})
    after_pairs = _attack_pairs(after, solver, exclude={move.to_square})
    if after_pairs - before_pairs:
        return "discovered_attack"

    return "tactic"
