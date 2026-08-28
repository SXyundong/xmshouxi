FROM node:20-bookworm-slim AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
ENV BACKEND_URL=http://127.0.0.1:8000
RUN npm run build


FROM node:20-bookworm-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NODE_ENV=production \
    BACKEND_URL=http://127.0.0.1:8000 \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv \
    && python3 -m venv /opt/venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./

WORKDIR /app/frontend
COPY --from=frontend-builder /build/frontend/package.json ./package.json
COPY --from=frontend-builder /build/frontend/package-lock.json ./package-lock.json
COPY --from=frontend-builder /build/frontend/node_modules ./node_modules
COPY --from=frontend-builder /build/frontend/.next ./.next
COPY --from=frontend-builder /build/frontend/public ./public

COPY docker-start.sh /app/docker-start.sh
RUN chmod +x /app/docker-start.sh

EXPOSE 3000

CMD ["/app/docker-start.sh"]
