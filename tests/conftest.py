import os

os.environ.setdefault("HANDA_LLM_PROVIDER", "mock")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")

import pytest


@pytest.fixture(scope="session")
def desk(tmp_path_factory):
    os.environ["HANDA_DATA_DIR"] = str(tmp_path_factory.mktemp("handa"))
    os.environ["HANDA_LLM_PROVIDER"] = "mock"
    from handa.config import get_settings

    get_settings.cache_clear()
    from handa.service import Desk

    return Desk.create()


@pytest.fixture(scope="session")
def client(desk):
    from fastapi.testclient import TestClient

    from handa.api import create_app

    with TestClient(create_app(desk=desk)) as test_client:
        yield test_client
