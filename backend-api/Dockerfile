# Backend container recipe. Only used at DEPLOY time (Render/Railway).
# You do NOT need Docker for local dev — just run uvicorn in the venv.

FROM python:3.13-slim

# System libs OpenCV needs at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render/Railway inject $PORT; default to 8000 locally.
ENV PORT=8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
