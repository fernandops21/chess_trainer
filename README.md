# Chess Trainer

> **Status: personal project, under active development and testing.** I use it daily to train, but it
> changes often, comes with no warranty, has no user accounts and is meant to run locally for a single
> person. It is public so anyone can read the code or run it for themselves.
>
> Documentação completa em português: [docs/manual.pt-BR.md](docs/manual.pt-BR.md).

Chess Trainer is a local-first chess training app built around **your own games**. Think of it as
"Chessable, but the course is you": it turns your mistakes into spaced-repetition puzzles, lets you
read and build annotated studies, and trains tactics with a local rating.

## What it does

- **Your mistakes become puzzles.** Imports your games from chess.com, analyses them with Stockfish and
  creates puzzles from your blunders and your opponents' (punish the mistake, or avoid the one you made),
  scheduled with spaced repetition.
- **Refutation on the board.** Play a wrong move and the engine answers it, shows the evaluation drop
  and the line that follows; then you try again. The result screen is a full analysis board, with a
  card showing what you actually played in the game and what you missed.
- **Studies.** Imports Lichess studies and PGN files (books and game collections you own), detects
  which chapters are exercises and which side the student plays, and includes a study editor with
  variations, comments, arrows and NAGs. A **book mode** reads annotated games one move per page,
  and moves written inside the prose are clickable (with move numbers in the old "12 Nf3" style too).
- **Tactics.** Trains from the public Lichess puzzle database with a local Elo-style rating and theme
  filters; puzzles you want to keep go into the spaced-repetition queue.
- **Analysis board.** Stockfish lines, evaluation bar, automatic move classification (brilliant, best,
  inaccuracy, blunder…), masters opening book, position setup, save as study chapter.
- **Progress.** Rating over time, reviews per day, accuracy by theme and by source, streaks. Light and
  dark themes, sounds, keyboard navigation, mobile layout.

## Screenshots

| Puzzle from your own game | Analysis board | Progress |
| --- | --- | --- |
| ![Puzzle](docs/screenshots/exercicio.png) | ![Analysis](docs/screenshots/analise.png) | ![Progress](docs/screenshots/progresso.png) |

## Running it

    cd frontend && npm install && npm run build
    cd ../backend && uv sync && uv run python -m chess_trainer

Open http://127.0.0.1:8000. You need a Stockfish binary (see `backend/README.md`) and a chess.com
username in the settings page; a Lichess API token is optional (opening book). The interface is in
Portuguese.

## Stack

Python 3.13, FastAPI, SQLAlchemy, SQLite and python-chess on the backend; React 19, TypeScript, Vite,
chessground and chess.js on the frontend; Stockfish as the engine. Around 500 backend tests (pytest)
and 600 frontend tests (Vitest + Testing Library).

## How it was built

The project was built with AI coding agents (Claude Code) driven by written specs and plans that live in
`docs/superpowers`: each feature starts as a design conversation, becomes a plan with tasks, is
implemented by an agent, reviewed by another, fixed, reviewed as a whole and only then merged. The
product decisions, the specs, the reviews of the reviews and the daily testing are mine.

## License

AGPL-3.0 (see `LICENSE`). The board (chessground) is GPL-3.0 and the sounds come from Lichess
(AGPL-3.0), which sets the license of the whole. Studies, games and books you import stay yours: the
app ships no third-party content, and the study test fixture uses only moves and synthetic text.
