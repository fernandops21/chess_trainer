"""Exportação do conjunto de ouro em JSONL, para treinar o classificador de golpes
fora do processo do servidor (spec golpes §8). Uso: `uv run python -m
chess_trainer.core.golpes.exportar_ouro [caminho.jsonl]`; sem argumento, grava em
`ml/golpes/gold/<AAAA-MM-DD>.jsonl` na raiz do repositório."""
from __future__ import annotations

from chess_trainer.core.golpes.rotulagem import exportar_ouro


def main() -> None:
    import os, sys
    from datetime import date
    from pathlib import Path
    from chess_trainer.core.db import make_engine, make_session_factory
    caminho = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[4] / "ml" / "golpes" / "gold" / f"{date.today().isoformat()}.jsonl"
    engine = make_engine(os.environ.get("CHESS_TRAINER_DB", "data/chess_trainer.db"))
    with make_session_factory(engine)() as db:
        texto = exportar_ouro(db)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto, encoding="utf-8")
    print(f"{texto.count(chr(10))} rótulos em {caminho}")


if __name__ == "__main__":
    main()
