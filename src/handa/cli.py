"""Price one of the six sample requests without opening the browser."""

import argparse
import json

from handa.config import get_settings
from handa.logging_setup import setup_logging
from handa.sample_data.generate import generate_catalog
from handa.service import Desk


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one synthetic Mesa Clara request through the desk.")
    parser.add_argument("sample", nargs="?", default="town-hall")
    args = parser.parse_args()
    settings = get_settings()
    setup_logging(settings.log_level)
    text = next(item["text"] for item in generate_catalog()["requests"] if item["id"] == args.sample)
    desk = Desk.create(settings)
    view = desk.wait(desk.begin(text))
    print(json.dumps({key: view[key] for key in ("run_id", "status", "revision", "pricing", "agent_messages")}, indent=2, default=str))


if __name__ == "__main__":
    main()
