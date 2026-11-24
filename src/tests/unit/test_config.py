from rarest_blue.config import DEFAULT_DATABASE_URL, Settings


def test_blank_env_values_fall_back_to_defaults():
    s = Settings.from_env({"DATABASE_URL": "", "CORS_ORIGINS": "https://a.example, https://b.example"})
    assert s.database_url == DEFAULT_DATABASE_URL
    assert s.cors_origins == ["https://a.example", "https://b.example"]


def test_repr_hides_secrets():
    s = Settings(database_url="postgresql://u:hunter2@h/db", openrouter_api_key="sk-secret")
    assert "hunter2" not in repr(s) and "sk-secret" not in repr(s)
