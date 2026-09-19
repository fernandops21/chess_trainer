"""Exportação do conjunto de ouro em JSONL, para treinar o classificador de golpes
fora do processo do servidor (spec golpes §8). Uso: `uv run python -m
chess_trainer.core.golpes.exportar_ouro [caminho.jsonl]`; sem argumento, grava em
`ml/golpes/gold/<AAAA-MM-DD>.jsonl` na raiz do repositório."""
from __future__ import annotations

from chess_trainer.core.golpes.votos import exportar_ouro


def main() -> None:
    import os, sys
    from datetime import date
    from pathlib import Path
    from chess_trainer.core.db import make_engine, make_session_factory
    caminho = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[4] / "ml" / "golpes" / "gold" / f"{date.today().isoformat()}.jsonl"
    # mesma derivação de `api/app.py::create_app` (BACKEND_DIR ali é `parents[2]` a partir de
    # `api/app.py`; daqui, três níveis acima chega ao mesmo `backend/`): caminho absoluto,
    # não relativo ao diretório de onde o comando é chamado
    backend_dir = Path(__file__).resolve().parents[3]
    data_dir = Path(os.environ.get("CHESS_TRAINER_DATA", str(backend_dir / "data")))
    db_path = os.environ.get("CHESS_TRAINER_DB", str(data_dir / "chess_trainer.db"))
    engine = make_engine(db_path)
    with make_session_factory(engine)() as db:
        texto = exportar_ouro(db)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto, encoding="utf-8")
    print(f"{texto.count(chr(10))} rótulos em {caminho}")


if __name__ == "__main__":
    main()
