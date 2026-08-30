FROM python:3.12-slim

WORKDIR /app
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt
COPY web ./web

EXPOSE 8080
CMD ["python", "-m", "flask", "--app", "web.app", "run", "--host", "0.0.0.0", "--port", "8080"]
