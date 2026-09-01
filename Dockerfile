FROM node:22-alpine AS frontend

WORKDIR /build
COPY package.json package-lock.json tsconfig.json vite.config.ts ./
COPY frontend ./frontend
COPY web/static/app.css ./web/static/app.css
RUN npm ci && npm run build

FROM python:3.12-slim

WORKDIR /app
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt
COPY web ./web
COPY --from=frontend /build/web/static/dist ./web/static/dist

EXPOSE 8080
CMD ["python", "-m", "flask", "--app", "web.app", "run", "--host", "0.0.0.0", "--port", "8080"]
