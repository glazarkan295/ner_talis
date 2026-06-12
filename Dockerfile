FROM node:20-slim AS web-builder

WORKDIR /web
COPY web/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
COPY web/ ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV PUBLIC_UPLOADS_ASSETS_DIR=data/public_uploads/assets

COPY ner_talis_game_project/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY timeweb_start.py ./timeweb_start.py
COPY data ./data
COPY ner_talis_game_project ./ner_talis_game_project
COPY --from=web-builder /web/dist ./web/dist
RUN mkdir -p ./data/public_uploads/assets/admin_uploads/items

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=6 CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT', '8080'), timeout=3).read()"

CMD ["python", "timeweb_start.py"]
