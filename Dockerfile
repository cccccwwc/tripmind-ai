FROM node:22-alpine AS frontend-build

WORKDIR /app/frontend
ARG VITE_AMAP_WEB_JS_KEY
ARG VITE_AMAP_SECURITY_JS_CODE
ENV VITE_AMAP_WEB_JS_KEY=${VITE_AMAP_WEB_JS_KEY} \
    VITE_AMAP_SECURITY_JS_CODE=${VITE_AMAP_SECURITY_JS_CODE}
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

WORKDIR /app/backend
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
