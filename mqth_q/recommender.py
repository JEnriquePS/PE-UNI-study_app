# revisa resultados por pregunta, historial de intentos
# Calcular recomendaciones basadas en desempeño y errores recientes
# Calcula nivel de conocimiento por tópico
# Recomienda próximas preguntas a intentar

from __future__ import annotations
from typing import Dict, List, Optional, Iterable
from collections import defaultdict

from .config import RECS_K
from .db import get_user_id, get_attempts, list_unseen, fetch_question

# ---------------------------
# Helpers over attempts
# ---------------------------
def _latest_per_exercise(attempts: Iterable[Dict]) -> Dict[str, Dict]:
    """Keep only the last attempt per exercise_id (by ts)."""
    latest: Dict[str, Dict] = {}
    for a in attempts:
        ex = a["exercise_id"]
        if ex not in latest or a["ts"] > latest[ex]["ts"]:
            latest[ex] = a
    return latest

def recent_mistakes(user_id: int, limit: int = 10) -> List[str]:
    """Exercises whose latest attempt is incorrect, most recent first."""
    attempts = get_attempts(user_id, limit=10_000)  # safe upper bound
    latest = _latest_per_exercise(attempts).values()
    mistakes = [a for a in latest if int(a.get("correct", 0)) == 0]
    mistakes.sort(key=lambda x: x["ts"], reverse=True)
    return [m["exercise_id"] for m in mistakes[:limit]]

def topic_performance(user_id: int) -> List[Dict]:
    """
    Returns a list of {topic, avg_score, n} sorted by avg_score ASC (weak → strong).
    """
    attempts = get_attempts(user_id, limit=10_000)
    by_topic: Dict[str, List[float]] = defaultdict(list)
    for a in attempts:
        topic = a.get("topic")
        score = a.get("score")
        if topic is not None and score is not None:
            by_topic[topic].append(float(score))

    perf = [
        {"topic": t, "avg_score": (sum(xs) / len(xs)), "n": len(xs)}
        for t, xs in by_topic.items() if xs
    ]
    perf.sort(key=lambda d: d["avg_score"])  # weakest first
    return perf

# ---------------------------
# Main recommendation logic
# ---------------------------
def recommend_next(user_id: int, k: int = RECS_K) -> List[str]:
    """
    Blend of:
      - ~40% recent mistakes to review (latest attempt incorrect)
      - ~60% unseen items, prioritizing weak topics
    Returns a list of exercise_id.
    """
    # 1) recent mistakes (review)
    review_take = max(1, int(0.4 * k))
    review_ids = recent_mistakes(user_id, limit=10)[:review_take]

    # 2) unseen pool (ordered by exam date ASC from DB)
    unseen = list_unseen(user_id, k=500)  # [{'exercise_id','topic','date',...}, ...]
    unseen_map = {row["exercise_id"]: row for row in unseen}

    # weak topics (bottom half)
    perf = topic_performance(user_id)
    weak_topics = {p["topic"] for p in perf[: max(1, len(perf)//2)]} if perf else set()

    # prioritize unseen in weak topics, keep stable order by date
    unseen_weak = [r["exercise_id"] for r in unseen if r.get("topic") in weak_topics]
    unseen_other = [r["exercise_id"] for r in unseen if r.get("topic") not in weak_topics]

    picks: List[str] = []
    seen: set[str] = set()

    def _add(seq: Iterable[str], need: int):
        nonlocal picks, seen
        for ex_id in seq:
            if len(picks) >= need:
                break
            if ex_id not in seen:
                picks.append(ex_id); seen.add(ex_id)

    # Start with reviews, then unseen-weak, then unseen-other
    _add(review_ids, review_take)
    _add(unseen_weak, k)
    _add(unseen_other, k)

    return picks[:k]

# ---------------------------
# Convenience wrappers
# ---------------------------
def recommend_next_for_username(username: str, k: int = RECS_K) -> List[str]:
    uid = get_user_id(username)
    return recommend_next(uid, k)

def questions_with_metadata(exercise_ids: List[str]) -> List[Dict]:
    """Optional: enrich ids with question/topic/date if you need to display them."""
    out = []
    for ex in exercise_ids:
        meta = fetch_question(ex)
        if meta:
            out.append(meta)
    return out
