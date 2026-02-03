from pathlib import Path

def _ensure_init():
    # init_db muss existieren; wenn nicht, ist das ein echter Bug im Persistence-Layer
    import gcu_v1.persistence.status_store as store
    assert hasattr(store, "init_db"), "status_store.init_db fehlt"
    store.init_db()
    return store

def test_persist_and_load_run_state(temp_db: Path):
    store = _ensure_init()

    run_id = "test-run-123"

    store.persist_run_state(
        run_id=run_id,
        status="needs_review",
        hitl_required=True,
        approval_required=True,
        approval_provided=False
    )

    state = store.load_run_state(run_id)
    assert state is not None
    assert state["run_id"] == run_id
    assert state["status"] == "needs_review"
    assert state["hitl_required"] is True
    assert state["approval_required"] is True
    assert state["approval_provided"] is False

def test_load_nonexistent_run_returns_none(temp_db: Path):
    store = _ensure_init()
    state = store.load_run_state("does-not-exist")
    assert state is None

def test_update_existing_run_overwrites_fields(temp_db: Path):
    store = _ensure_init()

    run_id = "test-run-456"

    # initial
    store.persist_run_state(run_id, "needs_review", True, True, False)

    # update
    store.persist_run_state(run_id, "approved", True, True, True)

    state = store.load_run_state(run_id)
    assert state is not None
    assert state["run_id"] == run_id
    assert state["status"] == "approved"
    assert state["approval_provided"] is True

def test_idempotent_init_db(temp_db: Path):
    import gcu_v1.persistence.status_store as store
    store.init_db()
    store.init_db()  # darf nicht crashen
