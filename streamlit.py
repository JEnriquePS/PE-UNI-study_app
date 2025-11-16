# streamlit_app.py
# ------------------------------------------------------------
# UI con:
#  - Sidebar: ID del estudiante, carga de resumen + intentos + temas
#  - Tabs:    📊 Dashboard  |  📝 Practice
#  - Practice: modo Recomendación o Aleatorio por tema
# ------------------------------------------------------------

import os
import requests
import pandas as pd
import streamlit as st

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
TIMEOUT = 30

# -------------------- Helpers HTTP --------------------
def api_health():
    return requests.get(f"{API_URL}/health", timeout=TIMEOUT).json()

def api_summary(username: str):
    r = requests.get(f"{API_URL}/users/{username}/summary", timeout=TIMEOUT); r.raise_for_status(); return r.json()

def api_attempts(username: str, limit: int = 20):
    r = requests.get(f"{API_URL}/users/{username}/attempts", params={"limit": limit}, timeout=TIMEOUT); r.raise_for_status(); return r.json()

def api_topics():
    r = requests.get(f"{API_URL}/topics", timeout=TIMEOUT); r.raise_for_status(); return r.json()

def api_get_next(username: str, k: int = 3):
    r = requests.get(f"{API_URL}/questions/next", params={"username": username, "k": k}, timeout=TIMEOUT); r.raise_for_status(); return r.json()

def api_random_by_topic(username: str, topic: str, only_unseen: bool = True):
    r = requests.get(f"{API_URL}/questions/random", params={"username": username, "topic": topic, "only_unseen": str(only_unseen).lower()}, timeout=TIMEOUT); r.raise_for_status(); return r.json()

def api_get_question(exercise_id: str):
    r = requests.get(f"{API_URL}/questions/{exercise_id}", timeout=TIMEOUT); r.raise_for_status(); return r.json()

def api_submit(username: str, exercise_id: str, answer: str):
    payload = {"username": username, "exercise_id": exercise_id, "answer": answer}
    r = requests.post(f"{API_URL}/attempts", json=payload, timeout=TIMEOUT); r.raise_for_status(); return r.json()

# -------------------- Estado global --------------------
if "username" not in st.session_state:
    st.session_state.username = "student1"
if "summary" not in st.session_state:
    st.session_state.summary = None
if "attempts" not in st.session_state:
    st.session_state.attempts = []
if "topics" not in st.session_state:
    st.session_state.topics = []
if "practice_mode" not in st.session_state:
    st.session_state.practice_mode = "Recomendar"
if "selected_topic" not in st.session_state:
    st.session_state.selected_topic = None
if "current_q" not in st.session_state:
    st.session_state.current_q = None
if "last_feedback" not in st.session_state:
    st.session_state.last_feedback = None
if "suggestions" not in st.session_state:
    st.session_state.suggestions = []

# -------------------- Sidebar (Estudiante) --------------------
st.sidebar.title("👤 Estudiante")
st.sidebar.caption("Define el ID del estudiante y carga sus datos.")

st.session_state.username = st.sidebar.text_input("ID de estudiante", st.session_state.username)

colA, colB = st.sidebar.columns([1,1])
with colA:
    if st.button("Cargar datos"):
        try:
            st.session_state.summary = api_summary(st.session_state.username)
            st.session_state.attempts = api_attempts(st.session_state.username, limit=50)
            st.session_state.topics = api_topics()
            st.success("Datos del estudiante cargados.")
        except requests.HTTPError as e:
            st.error(f"Error servidor: {e.response.text}")
        except Exception as e:
            st.error(f"No se pudo cargar: {e}")

with colB:
    if st.button("Salud (API)"):
        try:
            h = api_health()
            st.info(f"API OK: {h}")
        except Exception as e:
            st.error(f"API no responde: {e}")

st.sidebar.markdown("---")
st.sidebar.caption(f"API_URL = {API_URL}")

# -------------------- Tabs --------------------
tab_dash, tab_practice = st.tabs(["📊 Dashboard", "📝 Practice"])

# -------------------- 📊 Dashboard --------------------
with tab_dash:
    st.header("Resumen del estudiante")
    if not st.session_state.summary:
        st.info("Presiona **Cargar datos** en la barra lateral.")
    else:
        overall = st.session_state.summary["overall"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Intentos", overall["attempts"])
        c2.metric("Correctness", f"{overall['correct_rate']*100:.0f}%")
        c3.metric("Puntaje medio", f"{overall['avg_score']:.2f}")

        st.subheader("Rendimiento por tema")
        df_topics = pd.DataFrame(st.session_state.summary["by_topic"])
        if df_topics.empty:
            st.write("Sin intentos aún.")
        else:
            st.dataframe(df_topics, use_container_width=True)
            # Gráfico simple (promedio por tema)
            chart_df = df_topics[["topic","avg_score"]].set_index("topic")
            st.bar_chart(chart_df)

        st.subheader("Intentos recientes")
        df_attempts = pd.DataFrame(st.session_state.attempts)
        if df_attempts.empty:
            st.write("Sin intentos aún.")
        else:
            df_attempts_disp = df_attempts[["ts","exercise_id","topic","score","correct"]]
            st.dataframe(df_attempts_disp, use_container_width=True)

# -------------------- 📝 Practice --------------------
with tab_practice:
    st.header("Práctica")

    # Modo de práctica
    st.session_state.practice_mode = st.radio("Modo:", ["Recomendar", "Aleatorio por tema"], horizontal=True)

    # Recomendar
    if st.session_state.practice_mode == "Recomendar":
        cols = st.columns([1,1,2])
        with cols[0]:
            k = st.number_input("¿Cuántas sugerencias?", min_value=1, max_value=10, value=3, step=1)
        with cols[1]:
            if st.button("🔄 Recomendar"):
                try:
                    st.session_state.suggestions = api_get_next(st.session_state.username, k=k)
                    st.session_state.current_q = None
                    st.session_state.last_feedback = None
                    st.success(f"Sugerencias: {len(st.session_state.suggestions)}")
                except Exception as e:
                    st.error(f"No se pudo recomendar: {e}")

        # Elegir de sugerencias
        if st.session_state.suggestions:
            options = [
                (f"{row['exercise_id']} · {row.get('topic','?')} · {row.get('date','?')}", row["exercise_id"])
                for row in st.session_state.suggestions
            ]
            labels = [o[0] for o in options]
            values = {o[0]: o[1] for o in options}
            picked = st.selectbox("Elige un ejercicio sugerido:", labels, index=0, key="suggest_pick")
            if st.button("📖 Mostrar ejercicio", key="show_suggest"):
                try:
                    ex_id = values[picked]
                    st.session_state.current_q = api_get_question(ex_id)
                    st.session_state.last_feedback = None
                except Exception as e:
                    st.error(f"No se pudo traer el ejercicio: {e}")

    # Aleatorio por tema
    else:
        # Selección de tema de la lista cargada en sidebar
        topics = st.session_state.topics or []
        st.session_state.selected_topic = st.selectbox("Tema:", topics, index=0 if topics else None)
        only_unseen = st.checkbox("Solo no vistos", value=True)
        if st.button("🎲 Obtener aleatorio"):
            if not st.session_state.selected_topic:
                st.warning("Primero carga los temas en la barra lateral y selecciona uno.")
            else:
                try:
                    row = api_random_by_topic(st.session_state.username, st.session_state.selected_topic, only_unseen=only_unseen)
                    st.session_state.current_q = api_get_question(row["exercise_id"])
                    st.session_state.last_feedback = None
                    st.success("Ejercicio cargado.")
                except requests.HTTPError as e:
                    st.error(f"Error: {e.response.text}")
                except Exception as e:
                    st.error(f"No se pudo obtener: {e}")

    # Mostrar ejercicio actual (si existe)
    if st.session_state.current_q:
        q = st.session_state.current_q
        st.subheader(f"Ejercicio: {q['exercise_id']}")
        meta = f"_Tema:_ **{q.get('topic','?')}** · _Fecha:_ **{q.get('date','?')}** · _Tipo:_ **{q.get('exam_type','?')}**"
        st.markdown(meta)
        st.markdown("---")
        st.markdown("**Enunciado:**")
        st.write(q["question"])
        st.markdown("---")

        answer = st.text_area("Tu respuesta (breve):", height=160, key="answer_box")

        colA, colB = st.columns([1,3])
        with colA:
            if st.button("✅ Enviar y evaluar"):
                if not answer.strip():
                    st.warning("Escribe una respuesta antes de enviar.")
                else:
                    try:
                        fb = api_submit(st.session_state.username, q["exercise_id"], answer.strip())
                        st.session_state.last_feedback = fb
                        # refrescar dashboard (resumen + intentos) tras enviar
                        try:
                            st.session_state.summary = api_summary(st.session_state.username)
                            st.session_state.attempts = api_attempts(st.session_state.username, limit=50)
                        except Exception:
                            pass
                        st.success("Respuesta evaluada.")
                    except requests.HTTPError as e:
                        st.error(f"Error del servidor: {e.response.text}")
                    except Exception as e:
                        st.error(f"No se pudo enviar: {e}")

        if st.session_state.last_feedback:
            fb = st.session_state.last_feedback
            st.markdown("### 🧠 Feedback")
            icon = "✅" if fb.get("correct") else "❌"
            st.markdown(f"{icon} **Puntaje:** {fb.get('score', 0):.2f}")
            if fb.get("reasons"):
                st.markdown(f"**Por qué:** {fb['reasons']}")
            if fb.get("hint"):
                st.markdown(f"**Pista:** {fb['hint']}")
