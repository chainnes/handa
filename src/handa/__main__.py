"""python -m handa"""

import os

import uvicorn

from handa.api import create_app
from handa.config import get_settings
from handa.logging_setup import setup_logging


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    port = int(os.environ["PORT"]) if os.environ.get("PORT") else settings.port
    uvicorn.run(create_app(), host=settings.host, port=port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    main()
