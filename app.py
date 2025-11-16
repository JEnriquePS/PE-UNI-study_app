# from dotenv import load_dotenv, find_dotenv
# load_dotenv(find_dotenv(usecwd=True))   # searches for .env upward from your current working dir

# from mqth_q import config
# print(config.explain())  # sanity: shows what was loaded

# from mqth_q.db import init_db, get_user_id, list_unseen, fetch_question
# init_db()
# uid = get_user_id("student1")
# print("User:", uid)
# print("Unseen (first 3):", list_unseen(uid, 3))

#from mqth_q.baseline import baseline_grade
#print(baseline_grade("Show that the operator is a contraction", "Use Banach contraction to get unique fixed point"))
#from mqth_q.grading import grade_best_with_feedback
#print(grade_best_with_feedback("Q", "S", "A"))

# app.py
from __future__ import annotations
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query

# Load .env BEFORE imports that read env
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True))

from mqth_q import config
from mqth_q.db import init_db
from mqth_q.service import (
    next_questions_for, get_question_card, submit_answer,
    get_user_summary, get_recent_attempts, list_topics, pick_random_by_topic
)

from pydantic import BaseModel, Field

app = FastAPI(title="Math Trainer API", version="0.2.0")

# ---- Schemas (I/O) ----
class QuestionCard(BaseModel):
    exercise_id: str
    question: str
    topic: Optional[str] = None
    date: Optional[str] = None
    exam_type: Optional[str] = None

class AttemptsIn(BaseModel):
    username: str = Field(..., min_length=1)
    exercise_id: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)

class AttemptsOut(BaseModel):
    exercise_id: str
    topic: Optional[str] = None
    date: Optional[str] = None
    score: float
    correct: bool
    reasons: str = ""
    hint: str = ""

# ---- Lifecycle ----
@app.on_event("startup")
def _startup():
    init_db()
    print("CONFIG:", config.explain())

# ---- Health ----
@app.get("/health")
def health():
    return {"ok": True, "model": config.OLLAMA_MODEL, "db": config.DB_PATH}

# ---- Existing practice endpoints ----
@app.get("/questions/next", response_model=List[QuestionCard])
def api_next_questions(username: str, k: int = config.RECS_K):
    try:
        return next_questions_for(username, k=k)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/questions/{exercise_id}", response_model=QuestionCard)
def api_get_question(exercise_id: str):
    try:
        return get_question_card(exercise_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/attempts", response_model=AttemptsOut)
def api_submit_attempt(body: AttemptsIn):
    try:
        return submit_answer(body.username, body.exercise_id, body.answer)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---- NEW: Dashboard endpoints ----
@app.get("/users/{username}/summary")
def api_user_summary(username: str):
    try:
        return get_user_summary(username)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users/{username}/attempts")
def api_user_attempts(username: str, limit: int = Query(20, ge=1, le=1000)):
    try:
        return get_recent_attempts(username, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/topics")
def api_topics():
    try:
        return list_topics()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/questions/random")
def api_random_by_topic(username: str, topic: str, only_unseen: bool = True):
    try:
        row = pick_random_by_topic(username, topic, only_unseen=only_unseen)
        if not row:
            raise HTTPException(status_code=404, detail="No question found for topic.")
        return row
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
