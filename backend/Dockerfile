# Tathabbut API — Docker image (build context = repo root).
#
#   docker build -f backend/Dockerfile -t tathabbut .                                   # tfidf-char (default, ~260 MB RAM)
#   docker build -f backend/Dockerfile --build-arg EMBEDDER=bge-m3 -t tathabbut .     # BGE-M3 (needs ~3 GB RAM)
#   docker run -p 7860:7860 tathabbut
#
# Render (free, 512 MB): Dockerfile path = backend/Dockerfile, context = repo root; listens on $PORT.
# If BGE-M3 cannot be installed or loaded, the build falls back to tfidf-char so the API still starts;
# GET /index/stats reports which embedder is live.
FROM python:3.11-slim

ARG EMBEDDER=tfidf-char
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY backend/requirements.txt backend/requirements-bge.txt ./backend/
RUN pip install -r backend/requirements.txt && \
    if [ "$EMBEDDER" = "bge-m3" ]; then \
      ( pip install torch --index-url https://download.pytorch.org/whl/cpu && \
        pip install -r backend/requirements-bge.txt ) || echo "!!! BGE-M3 dependencies failed to install"; \
    fi

# Non-root user; model cache lives in the user's home.
RUN useradd -m -u 1000 user
ENV HOME=/home/user HF_HOME=/home/user/.cache/huggingface
COPY --chown=user data ./data
COPY --chown=user backend ./backend
RUN mkdir -p data/index data/raw && chown -R user:user /app
USER user
WORKDIR /app/backend

# Full Quran: bundled data/quran/quran_full.json (or data/raw), else download from Tanzil, else seed sample.
RUN [ -f ../data/quran/quran_full.json ] || [ -f ../data/raw/quran_full.json ] || \
    python scripts/fetch_quran.py || echo "!!! Using Quran seed sample"
RUN python scripts/build_index.py --embedder "$EMBEDDER" || \
    ( echo "!!! $EMBEDDER index failed — falling back to tfidf-char" && \
      python scripts/build_index.py --embedder tfidf-char )

# Model (if any) is cached at build time: no network needed at runtime.
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TATHABBUT_CORS=*
EXPOSE 7860
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
