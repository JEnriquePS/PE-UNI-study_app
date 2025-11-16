# CONECTA API/UI A SERVICIOS SIN CONTACTAR DIRECTAMENTE CON DB O LLM
# Obtiene usuario, recomienda preguntas, califica, y guarda intentos
# Recomienda la siguiente mejor pregunta
# Retorna diccionarios simples 

from __future__ import annotations
from typing import Dict, List, Optional
import logging
from statistics import mean

from .config import RECS_K
from .db import (
    get_user_id, fetch_question, save_attempt, get_attempts,
    list_topics as db_list_topics,
    pick_unseen_by_topic, pick_any_by_topic
)
from .recommender import recommend_next
from .grading import grade_best_with_feedback

log = logging.getLogger(__name__)

# ---------------- Read helpers ----------------
def get_question_card(exercise_id: str) -> Dict:
    q = fetch_question(exercise_id)
    if not q:
        raise ValueError(f"Unknown exercise_id: {exercise_id}")
    return {
        "exercise_id": q["exercise_id"],
        "question": q["question"],
        "topic": q.get("topic"),
        "date": q.get("date"),
        "exam_type": q.get("exam_type"),
    }

def next_questions_for(username: str, k: int = RECS_K) -> List[Dict]:
    uid = get_user_id(username)
    ids = recommend_next(uid, k=k)
    out: List[Dict] = []
    for ex in ids:
        try:
            out.append(get_question_card(ex))
        except Exception as e:
            log.warning("Skipping %s: %s", ex, e)
    return out

def list_topics() -> List[str]:
    return db_list_topics()

def get_recent_attempts(username: str, limit: int = 20) -> List[Dict]:
    uid = get_user_id(username)
    atts = get_attempts(uid, limit=limit)
    # compact
    return [
        {
            "ts": a["ts"],
            "exercise_id": a["exercise_id"],
            "topic": a.get("topic"),
            "score": a.get("score"),
            "correct": bool(a.get("correct")),
        }
        for a in atts
    ]

def get_user_summary(username: str) -> Dict:
    uid = get_user_id(username)
    atts = get_attempts(uid, limit=10_000)
    if not atts:
        return {
            "username": username,
            "overall": {"attempts": 0, "correct_rate": 0.0, "avg_score": 0.0, "last_attempt_ts": None},
            "by_topic": []
        }
    scores = [float(a["score"]) for a in atts if a["score"] is not None]
    correct = [int(a["correct"]) for a in atts if a["correct"] is not None]
    last_ts = max(a["ts"] for a in atts if a["ts"] is not None)

    by_topic: Dict[str, List[float]] = {}
    by_topic_corr: Dict[str, List[int]] = {}
    for a in atts:
        t = a.get("topic") or "unknown"
        by_topic.setdefault(t, []).append(float(a["score"]) if a["score"] is not None else 0.0)
        by_topic_corr.setdefault(t, []).append(int(a["correct"]) if a["correct"] is not None else 0)

    per_topic = []
    for t in sorted(by_topic.keys()):
        xs = by_topic[t]
        cs = by_topic_corr[t]
        per_topic.append({
            "topic": t,
            "n": len(xs),
            "avg_score": round(mean(xs), 3) if xs else 0.0,
            "correct_rate": round(sum(cs)/len(cs), 3) if cs else 0.0
        })

    return {
        "username": username,
        "overall": {
            "attempts": len(scores),
            "correct_rate": round(sum(correct)/len(correct), 3) if correct else 0.0,
            "avg_score": round(mean(scores), 3) if scores else 0.0,
            "last_attempt_ts": last_ts
        },
        "by_topic": per_topic
    }

# --------------- Pick random by topic ---------------
def pick_random_by_topic(username: str, topic: str, only_unseen: bool = True) -> Optional[Dict]:
    uid = get_user_id(username)
    row = None
    if only_unseen:
        row = pick_unseen_by_topic(uid, topic)
    if not row:
        row = pick_any_by_topic(topic)
    return row

# ---------------- Write (grade + save) ----------------
def submit_answer(username: str, exercise_id: str, student_answer: str) -> Dict:
    if not student_answer or not student_answer.strip():
        raise ValueError("Empty answer.")

    uid = get_user_id(username)
    q = fetch_question(exercise_id)
    if not q:
        raise ValueError(f"Unknown exercise_id: {exercise_id}")

    result = grade_best_with_feedback(q["question"], q["solution"], student_answer)

    try:
        save_attempt(uid, exercise_id, result, student_answer)
    except Exception as e:
        log.error("Failed to save attempt for %s/%s: %s", username, exercise_id, e)

    return {
        "exercise_id": exercise_id,
        "topic": q.get("topic"),
        "date": q.get("date"),
        "score": float(result.get("score", 0.0)),
        "correct": bool(result.get("correct", False)),
        "reasons": result.get("reasons", ""),
        "hint": result.get("hint", ""),
    }
