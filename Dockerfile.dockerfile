# Dockerfile
FROM python:3.11-slim

# System basics
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl tini && rm -rf /var/lib/apt/lists/*

# Workdir
WORKDIR /app

# Install deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
# Adjust if your package folder is named differently than "mqth_q"
COPY app.py streamlit.py ./
COPY mqth_q ./mqth_q

# Default envs (can be overridden by compose)
ENV DB_PATH=/data/temporal/exams.db \
    OLLAMA_URL=http://host.docker.internal:11434 \
    OLLAMA_MODEL=llama3.2:3b \
    PYTHONUNBUFFERED=1

# Expose commonly used ports
EXPOSE 8000 8501

# Use tini as init for better signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]

# Default command = API (compose will override for UI)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
