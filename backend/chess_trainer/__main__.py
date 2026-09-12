import logging
import os

import uvicorn

from chess_trainer.api.app import create_app


def main() -> None:
    host = os.environ.get("CHESS_TRAINER_HOST", "0.0.0.0")
    port = int(os.environ.get("CHESS_TRAINER_PORT", "8000"))
    # sem isto os logs do próprio app (o tempo de cada explicação, por exemplo) não saem:
    # o uvicorn configura só os loggers dele
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
