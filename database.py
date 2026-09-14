"""Conexión compartida para usuarios y registro de actividad."""

from pathlib import Path

import psycopg2
import toml


CONFIG_PATH = Path(__file__).resolve().parent / ".streamlit" / "activity_db.toml"


class DatabaseConfigurationError(RuntimeError):
    pass


def get_connection():
    try:
        config = toml.load(CONFIG_PATH)
    except (OSError, ValueError) as exc:
        raise DatabaseConfigurationError(
            "Revisa la configuración en .streamlit/activity_db.toml."
        ) from exc
    config.setdefault("connect_timeout", 5)
    config.setdefault("client_encoding", "utf8")
    return psycopg2.connect(**config)
