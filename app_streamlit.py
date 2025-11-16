import os, json, re, random, sqlite3, pandas as pd
import streamlit as st
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

DB_PATH =  "data\\temporal\\exams.db"

# ---------- DB helpers ----------
def connect(): return sqlite3.connect(DB_PATH)

def get_user_id(username:str):
    con = connect(); cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO users(username) VALUES(?)", (username,))
    con.commit()
    cur.execute("SELECT user_id FROM users WHERE username=?", (username,))
    uid = cur.fetchone()[0]; con.close(); return uid

def list_unseen(uid:int, k:int=10):
    con = connect(); cur = con.cursor()
    cur.execute("""
      SELECT q.exercise_id, q.topic_pred, e.date
      FROM questions q JOIN exams e USING(exam_id)
      WHERE q.exercise_id NOT IN (SELECT exercise_id FROM attempts WHERE user_id=?)
      ORDER BY e.date ASC LIMIT ?""", (uid, k))
    rows = cur.fetchall(); con.close()
    return [{"exercise_id": r[0], "topic": r[1], "date": r[2]} for r in rows]

def fetch_question(exercise_id:str):
    con = connect(); cur = con.cursor()
    cur.execute("""
      SELECT q.exercise_id, q.question, q.solution, q.topic_pred, e.date, e.exam_type
      FROM questions q JOIN exams e USING(exam_id) WHERE q.exercise_id=?""", (exercise_id,))
    r = cur.fetchone(); con.close()
    if not r: return None
    return {"exercise_id": r[0], "question": r[1], "solution": r[2], "topic": r[3], "date": r[4], "exam_type": r[5]}

def get_attempts(uid:int) -> pd.DataFrame:
    con = connect()
    df = pd.read_sql("""
      SELECT a.*, q.topic_pred AS topic
      FROM attempts a JOIN questions q ON a.exercise_id=q.exercise_id
      WHERE a.user_id=?
      ORDER BY a.ts DESC
    """, con, params=(uid,))
    con.close(); return df

def save_attempt(uid:int, exercise_id:str, g:dict, student_answer:str):
    con = connect(); cur = con.cursor()
    cur.execute("""
      INSERT INTO attempts(user_id, exercise_id, score, correct, cosine, jaccard, missing_keywords, student_answer)
      VALUES(?,?,?,?,?,?,?,?)
    """, (uid, exercise_id, g["score"], int(g["correct"]), g["cosine"], g["jaccard"],
          json.dumps(g.get("missing_keywords",[])), student_answer))
    con.commit(); con.close()

# ---------- Baseline grader (CPU-only) ----------
STOP = set("the a an and or of to for with from in on at is are be was were by as that this these those into over under if then else such".split())
def _clean(s:str)->str:
    s = (s or "").lower()
    s = re.sub(r"\(cid:\d+\)", " ", s)
    s = re.sub(r"[^a-z0-9\-\+\*/\^\=\(\)\[\]\{\}\., ]+"," ", s)
    return re.sub(r"\s+"," ", s).strip()

def _keywords(s:str):
    toks = re.findall(r"[a-z0-9\^\+\-\*/=]+", _clean(s))
    return {t for t in toks if len(t)>=2 and t not in STOP}

def grade_answer(solution:str, student:str):
    sol = _clean(solution); ans = _clean(student)
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3,5), min_df=1)
    X = vec.fit_transform([sol, ans]); X = normalize(X)
    cos = float((X[0] @ X[1].T).A[0,0]) if X.shape[1] else 0.0
    Ks, Ka = _keywords(sol), _keywords(ans)
    jac = len(Ks & Ka)/max(1, len(Ks | Ka))
    score = 0.6*cos + 0.4*jac
    return {
        "score": round(score,4),
        "correct": score >= 0.6,   # tune threshold here
        "cosine": round(cos,4),
        "jaccard": round(jac,4),
        "missing_keywords": list((Ks-Ka))[:8]
    }

# ---------- Simple recommender ----------
def recommend_next(uid:int, k:int=5):
    # weak-topic mix: 70% weak + 30% others
    con = connect()
    # topic performance
    perf = pd.read_sql("""
      SELECT q.topic_pred AS topic, AVG(a.score) AS avg_score, COUNT(*) n
      FROM attempts a JOIN questions q ON a.exercise_id=q.exercise_id
      WHERE a.user_id=?
      GROUP BY q.topic_pred
      ORDER BY avg_score ASC
    """, con, params=(uid,))
    # unseen pool
    unseen = pd.read_sql("""
      SELECT q.exercise_id, q.topic_pred AS topic
      FROM questions q
      WHERE q.exercise_id NOT IN (SELECT exercise_id FROM attempts WHERE user_id=?)
    """, con, params=(uid,))
    con.close()

    if unseen.empty: return []

    if perf.empty:
        return unseen.sample(min(k, len(unseen)))["exercise_id"].tolist()

    weak_topics = perf["topic"].tolist()
    pool_weak = unseen[unseen["topic"].isin(weak_topics[:max(1, len(weak_topics)//2)])]
    pool_other = unseen[~unseen["topic"].isin(pool_weak["topic"])]

    n_weak = max(1, int(0.7 * k))
    pick = []
    if not pool_weak.empty:
        pick += pool_weak.sample(min(n_weak, len(pool_weak)))["exercise_id"].tolist()
    if len(pick) < k and not pool_other.empty:
        pick += pool_other.sample(min(k-len(pick), len(pool_other)))["exercise_id"].tolist()
    return pick

# ---------- UI ----------
st.set_page_config(page_title="Exam Trainer", page_icon="🧪", layout="wide")
st.title("🧪 Exam Trainer (DB-backed)")

if not os.path.exists(DB_PATH):
    st.error(f"`{DB_PATH}` not found. Place this app next to your DB.")
    st.stop()

with st.sidebar:
    username = st.text_input("Username", value="student1")
    uid = get_user_id(username)
    st.success(f"User OK (id={uid})")
    if st.button("Recommend next"):
        st.session_state.recs = recommend_next(uid, k=5)

tab1, tab2 = st.tabs(["Practice", "Progress"])

with tab1:
    # unseen or recommended
    unseen = list_unseen(uid, k=20)
    recs = st.session_state.get("recs", [])
    colL, colR = st.columns(2)
    with colL:
        st.subheader("Unseen")
        options = [f"{r['exercise_id']} · {r['topic']} · {r['date']}" for r in unseen]
        choice = st.selectbox("Pick a question", options, index=0 if options else None)
        selected_id = choice.split(" · ")[0] if choice else None
    with colR:
        st.subheader("Recommended")
        st.write(recs if recs else "—")

    if selected_id:
        q = fetch_question(selected_id)
        st.markdown(f"**{q['exercise_id']}** · *{q['topic']}* · {q['date']} ({q['exam_type']})")
        st.write(q["question"])
        ans = st.text_area("Your answer", height=160)
        if st.button("Submit answer", type="primary"):
            g = grade_answer(q["solution"], ans)
            save_attempt(uid, q["exercise_id"], g, ans)
            st.success(f"Score: {g['score']:.2f} · {'✅ Correct' if g['correct'] else '❌ Not yet'}")
            st.caption(f"Missing keywords: {', '.join(g['missing_keywords']) if g['missing_keywords'] else '—'}")
            st.session_state.recs = recommend_next(uid, k=5)

with tab2:
    df_attempts = get_attempts(uid)
    if df_attempts.empty:
        st.info("No attempts yet.")
    else:
        st.dataframe(df_attempts[["ts","exercise_id","topic","score","correct"]], use_container_width=True, height=320)
        by_topic = df_attempts.groupby("topic")["score"].mean().sort_values()
        st.bar_chart(by_topic)
