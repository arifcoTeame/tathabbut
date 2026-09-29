# Build from the repo root:  docker build -f backend/Dockerfile --build-arg EMBEDDER=tfidf-char -t tathabbut .
# Hugging Face Spaces (Docker, port 7860) or Render.
# EMBEDDER=bge-m3 for HF Spaces (16 GB RAM); EMBEDDER=tfidf-char for Render free tier (512 MB).
FROM python:3.11-slim
ARG EMBEDDER=tfidf-char
WORKDIR /app
COPY backend/requirements.txt backend/requirements-bge.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt && \
    if [ "$EMBEDDER" = "bge-m3" ]; then \
      pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
      pip install --no-cache-dir -r backend/requirements-bge.txt; fi
COPY data ./data
COPY backend ./backend
WORKDIR /app/backend
RUN python scripts/build_index.py --embedder $EMBEDDER
ENV TATHABBUT_CORS=*
EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
