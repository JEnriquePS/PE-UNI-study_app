# src/baseline.py
from __future__ import annotations
import re
from typing import Dict, List
import numpy as np

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .config import GRADE_THRESHOLD

# ----------------------
# Tiny text utilities
# ----------------------
_WORD_RE = re.compile(r"\b\w+\b", re.UNICODE)
STOPWORDS = {
    "the","a","an","and","or","of","to","in","on","for","by","with","at","as","is","are",
    "be","this","that","it","we","you","they","from","was","were","but","not","if","then"
}

def _tokens(s: str) -> List[str]:
    return [w.lower() for w in _WORD_RE.findall(s or "")]

def _keywords(s: str, min_len: int = 4) -> List[str]:
    return [t for t in _tokens(s) if len(t) >= min_len and t not in STOPWORDS]

def _jaccard(a: List[str], b: List[str]) -> float:
    A, B = set(a), set(b)
    if not A and not B:
        return 0.0
    return len(A & B) / max(1, len(A | B))

# ----------------------
# Baseline grader (no LLM)
# ----------------------
def baseline_grade(solution: str, student: str) -> Dict:
    """
    Fast, dependency-light baseline:
      - TF-IDF cosine similarity between solution and student answer
      - Token Jaccard overlap
      - Missing keywords = solution keywords not present in student answer
      - 'correct' if blended score >= GRADE_THRESHOLD
    Returns a dict compatible with your DB schema.
    """
    sol = solution or ""
    stu = student or ""

    # TF-IDF cosine
    vect = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
    X = vect.fit_transform([sol, stu])
    cos = float(cosine_similarity(X[0], X[1])[0, 0])

    # Jaccard over raw tokens
    jac = float(_jaccard(_tokens(sol), _tokens(stu)))

    # Blend score (simple mean)
    score = float(np.clip((cos + jac) / 2.0, 0.0, 1.0))
    correct = bool(score >= GRADE_THRESHOLD)

    # Simple keyword hint
    sol_kw = set(_keywords(sol))
    stu_kw = set(_keywords(stu))
    missing = sorted(list(sol_kw - stu_kw))[:10]

    reasons = f"Baseline similarity — cosine={cos:.2f}, jaccard={jac:.2f}."
    hint = "Revisa los conceptos clave ausentes: " + ", ".join(missing) if missing else ""

    return {
        "score": score,
        "correct": correct,
        "cosine": cos,
        "jaccard": jac,
        "missing_keywords": missing,
        "reasons": reasons,
        "hint": hint,
    }

# Optional alias to keep backward compatibility with older imports
grade_answer = baseline_grade
