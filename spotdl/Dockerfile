FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir spotdl requests mutagen

WORKDIR /app
COPY cache.py .

ENV O2M_URL=http://o2m:6681
ENV SPOTDL_CACHE_DIR=/music/cache
ENV SPOTDL_CACHE_DAYS=30
ENV SPOTDL_CACHE_HOUR=3
ENV SPOTDL_BOX_UIDS=

CMD ["python", "-u", "cache.py"]
