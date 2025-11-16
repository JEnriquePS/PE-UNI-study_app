# tests/conftest.py
import os
import pytest
from pathlib import Path

@pytest.fixture(scope="session")
def db_path(tmp_path_factory, monkeypatch):
    # temp DB for the whole test session
    p = tmp_path_factory.mktemp("data") / "exams.db"
    monkeypatch.setenv("DB_PATH", str(p))  # ensure app uses this DB
    return p

@pytest.fixture(scope="session")
def seeded_db(db_path):
    # Create schema and seed a tiny dataset
    from mqth_q.db import init_db, connect
    init_db()
    con = connect()
    cur = con.cursor()

    # seed one exam
    cur.execute("""
    INSERT OR IGNORE INTO exams (exam_id, exam_type, date, year)
    VALUES ('General_2025-08-29','General','2025-08-29',2025);
    """)

    # seed two questions
    cur.execute("""
    INSERT OR REPLACE INTO questions (exercise_id, exam_id, question, solution, topic_pred)
    VALUES
    ('General_2025-08-29_Exercise_1','General_2025-08-29',
     'Show f is contraction and apply Banach.',
     'Compute L<1 and apply Banach contraction principle.',
     'Banach contraction'),
    ('General_2025-08-29_Exercise_2','General_2025-08-29',
     'State Riesz representation in Hilbert spaces.',
     'Every bounded linear functional is <x,y> for unique y.',
     'linear functional');
    """)
    con.commit(); con.close()
    return str(db_path)

@pytest.fixture()
def client(seeded_db, monkeypatch):
    # Make LLM grading a no-op so tests are fast (fallback to baseline)
    import mqth_q.grading as grading
    monkeypatch.setattr(grading, "llm_grade_and_feedback", lambda *a, **k: None)

    # Import the FastAPI app AFTER env var/DB are ready
    from fastapi.testclient import TestClient
    import app as api_app
    return TestClient(api_app.app)
