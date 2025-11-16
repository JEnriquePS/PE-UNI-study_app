# ===== Golden set evaluation (baseline + optional LLM) =====
import time, os, warnings
import numpy as np
import pandas as pd
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True))

from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix, classification_report, roc_auc_score

# --- project imports ---
from .db import fetch_question
from .baseline import baseline_grade
from .grading import llm_grade_and_feedback  # optional

# ------------- config -------------
GOLDEN_PATH = Path("data/golden/golden.csv")  # move/adjust if needed
THRESHOLDS = np.round(np.linspace(0.30, 0.85, 23), 2)  # sweep range for baseline
RUN_LLM = False        # set True to evaluate a small LLM subset
LLM_SUBSET = 8         # how many rows to test with LLM (keep small)
LLM_TIMEOUT = 30       # seconds per call

# ------------- load & join with solutions -------------
assert GOLDEN_PATH.exists(), f"Golden file not found at {GOLDEN_PATH}"
df = pd.read_csv(GOLDEN_PATH)

# map labels to binary: correct=1, partial/incorrect=0
label_map = {"correct": 1, "partial": 0, "incorrect": 0}
if not set(df["label"]).issubset(label_map.keys()):
    raise ValueError(f"Unexpected labels in golden set: {set(df['label']) - set(label_map)}")

df["y_true"] = df["label"].map(label_map).astype(int)

# attach question & solution (warn if any exercise_id is missing)
solutions, questions, missing = [], [], []
for ex in df["exercise_id"]:
    q = fetch_question(str(ex))
    if q is None:
        solutions.append(None); questions.append(None); missing.append(ex)
    else:
        solutions.append(q["solution"]); questions.append(q["question"])

if missing:
    warnings.warn(f"{len(missing)} exercise_id not found in DB. They will be dropped:\n{missing}")

df["solution"] = solutions
df["question"] = questions
df = df.dropna(subset=["solution"]).reset_index(drop=True)
assert len(df) > 0, "No rows left after matching solutions. Fix exercise_id values."

print(f"Golden rows ready: {len(df)}")

# ------------- baseline scores -------------
def _safe_baseline_score(sol, stu):
    try:
        return float(baseline_grade(sol, stu)["score"])
    except Exception as e:
        warnings.warn(f"Baseline failed on a row: {e}")
        return np.nan

t0 = time.perf_counter()
df["baseline_score"] = [ _safe_baseline_score(sol, ans) for sol, ans in zip(df["solution"], df["student_answer"]) ]
dt = time.perf_counter() - t0
df = df.dropna(subset=["baseline_score"]).reset_index(drop=True)
print(f"Computed baseline scores for {len(df)} rows in {dt:.2f}s")

# ------------- threshold sweep -------------
def evaluate_threshold(y_true, scores, thr):
    y_pred = (scores >= thr).astype(int)
    acc = accuracy_score(y_true, y_pred)
    pr, rc, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0,1]).ravel()
    return dict(threshold=float(thr), accuracy=acc, precision=pr, recall=rc, f1=f1, tp=int(tp), fp=int(fp), tn=int(tn), fn=int(fn))

sweep = [evaluate_threshold(df["y_true"].values, df["baseline_score"].values, t) for t in THRESHOLDS]
sweep_df = pd.DataFrame(sweep).sort_values("f1", ascending=False).reset_index(drop=True)

best = sweep_df.iloc[0].to_dict()
print("\n=== Baseline threshold selection (tuned on golden) ===")
print(f"Best threshold: {best['threshold']:.2f}")
print(f"Accuracy: {best['accuracy']:.3f} | Precision: {best['precision']:.3f} | Recall: {best['recall']:.3f} | F1: {best['f1']:.3f}")
print(f"Confusion (tn fp fn tp): {best['tn']} {best['fp']} {best['fn']} {best['tp']}")

# optional: ROC-AUC of baseline score (threshold-free)
try:
    auc = roc_auc_score(df["y_true"].values, df["baseline_score"].values)
    print(f"ROC-AUC (baseline score): {auc:.3f}")
except Exception:
    pass

# show a compact classification report at best threshold
y_pred_best = (df["baseline_score"].values >= best["threshold"]).astype(int)
print("\nClassification report @ best threshold:")
print(classification_report(df["y_true"].values, y_pred_best, target_names=["not-correct","correct"], zero_division=0))

# ------------- suggestion -------------
print("\n>>> Suggested GRADE_THRESHOLD for .env:", best["threshold"])

# ------------- OPTIONAL: quick LLM spot-check on a subset -------------
if RUN_LLM:
    print("\n=== LLM spot-check (subset) ===")
    sub = df.sample(min(LLM_SUBSET, len(df)), random_state=42).copy()
    preds, latencies = [], []

    for i, row in sub.iterrows():
        t0 = time.perf_counter()
        g = llm_grade_and_feedback(
            question=row["question"] or "",
            solution=row["solution"] or "",
            student=row["student_answer"] or "",
            timeout=LLM_TIMEOUT
        )
        lat = time.perf_counter() - t0
        latencies.append(lat)

        if g is None:
            preds.append(None)
        else:
            preds.append(1 if g.get("correct") else 0)

    sub["y_pred_llm"] = preds
    sub = sub.dropna(subset=["y_pred_llm"]).astype({"y_pred_llm": int})
    if len(sub) == 0:
        print("No LLM predictions returned (timeouts or errors).")
    else:
        acc = accuracy_score(sub["y_true"], sub["y_pred_llm"])
        pr, rc, f1, _ = precision_recall_fscore_support(sub["y_true"], sub["y_pred_llm"], average="binary", zero_division=0)
        print(f"LLM subset n={len(sub)} | Acc={acc:.3f} P={pr:.3f} R={rc:.3f} F1={f1:.3f}")
        if latencies:
            print(f"LLM latency: median={np.median(latencies):.2f}s, p95={np.percentile(latencies,95):.2f}s")

    # show 2 examples
    with pd.option_context('display.max_colwidth', 120):
        print("\nSample rows (golden vs LLM correctness):")
        print(sub[["exercise_id","label","student_answer","y_true","y_pred_llm"]].head(2))
