# calificación base (text similarity)
# LLM para feedback + ajuste de nota
# expone entrypoint grade_best_with_feedback() -- combina ambos enfoques y luego guarda el intento

from __future__ import annotations
import json, requests
from typing import Dict, Optional
import numpy as np

from .config import OLLAMA_URL, OLLAMA_MODEL, LLM_OPTIONS
from .baseline import baseline_grade 

def llm_grade_and_feedback(question: str, solution: str, student: str, timeout: int = 60) -> Optional[Dict]:
    prompt = f"""You grade a student's short math answer. Be brief and do not reveal full solutions.

Question:
{question}

Reference solution:
{solution}

Student answer:
{student}

Return ONLY valid compact JSON with EXACT keys:
- "score": number 0..1
- "correct": true/false
- "explanation": one short sentence explaining the verdict
- "hint": one short hint the student can try next (do NOT reveal the full solution)
"""
    try:
        payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json", "options": LLM_OPTIONS}
        r = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=timeout)
        r.raise_for_status()
        raw = r.json().get("response", "").strip()
        data = json.loads(raw)

        score = float(np.clip(float(data.get("score", 0.0)), 0.0, 1.0))
        correct = bool(data.get("correct", False))
        reasons = (data.get("explanation") or "").strip()
        hint = (data.get("hint") or "").strip()

        return {
            "score": score,
            "correct": correct,
            "cosine": None,
            "jaccard": None,
            "missing_keywords": [],
            "reasons": reasons,
            "hint": hint,
        }
    except Exception:
        return None

def grade_best_with_feedback(question: str, solution: str, student: str) -> Dict:
    """Try LLM first; if it fails, fall back to the baseline grader."""
    g = llm_grade_and_feedback(question, solution, student)
    if g:
        return g
    return baseline_grade(solution, student)
