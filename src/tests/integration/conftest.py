import os

import pytest
from fastapi.testclient import TestClient

from rarest_blue.config import Settings
from rarest_blue.entrypoints.http.app import create_app
from rarest_blue.infrastructure import postgres

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def settings() -> Settings:
    if not TEST_DATABASE_URL:
        pytest.skip("set TEST_DATABASE_URL to run database tests")
    return Settings(database_url=TEST_DATABASE_URL, generator_model="gen-model", verifier_model="check-model")


@pytest.fixture
def database(settings):
    postgres.init_schema(settings.database_url)
    with postgres.connect(settings.database_url) as conn:
        conn.execute("TRUNCATE daily_prompts, guesses, finishes")
    return settings


@pytest.fixture
def uow(database):
    return lambda: postgres.PostgresUnitOfWork(database.database_url)


@pytest.fixture
def client(database):
    with TestClient(create_app(database)) as c:
        yield c
