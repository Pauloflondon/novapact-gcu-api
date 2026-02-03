import tempfile
from pathlib import Path
import pytest

@pytest.fixture
def temp_db(monkeypatch):
    """
    Windows-sicher: trackt alle sqlite3.connect() Connections im status_store
    und schließt sie im Teardown. Damit keine File-Locks auf der temp DB bleiben.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_gcu_state.db"

        import gcu_v1.persistence.status_store as s

        # DB_PATH wird im status_store als Path verwendet (.parent), daher Path patchen
        monkeypatch.setattr(s, "DB_PATH", db_path)

        # --- Track all sqlite connections created by status_store ---
        created_conns = []

        # status_store nutzt sehr wahrscheinlich "import sqlite3" -> s.sqlite3.connect(...)
        if hasattr(s, "sqlite3") and hasattr(s.sqlite3, "connect"):
            real_connect = s.sqlite3.connect

            def tracked_connect(*args, **kwargs):
                conn = real_connect(*args, **kwargs)
                created_conns.append(conn)
                return conn

            monkeypatch.setattr(s.sqlite3, "connect", tracked_connect)

        # Falls get_conn() gecached ist (lru_cache), vor dem Test leeren
        if hasattr(s, "get_conn") and hasattr(s.get_conn, "cache_clear"):
            try:
                s.get_conn.cache_clear()
            except Exception:
                pass

        yield db_path

        # --- TEARDOWN: alles schließen, was offen sein könnte ---
        # 1) gecachte get_conn schließen + cache clear
        if hasattr(s, "get_conn"):
            try:
                conn = s.get_conn()
                try:
                    conn.close()
                except Exception:
                    pass
            except Exception:
                pass

            if hasattr(s.get_conn, "cache_clear"):
                try:
                    s.get_conn.cache_clear()
                except Exception:
                    pass

        # 2) alle während des Tests erzeugten conns schließen
        for c in created_conns:
            try:
                c.close()
            except Exception:
                pass
