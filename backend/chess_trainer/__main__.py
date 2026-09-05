import os

import uvicorn

from chess_trainer.api.app import create_app


def main() -> None:
    host = os.environ.get("CHESS_TRAINER_HOST", "0.0.0.0")
    port = int(os.environ.get("CHESS_TRAINER_PORT", "8000"))
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
