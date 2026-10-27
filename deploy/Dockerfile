FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.lock /app/backend/requirements.lock
RUN pip install --no-cache-dir -r backend/requirements.lock
COPY backend /app/backend
COPY config /app/config
COPY knowledge /app/knowledge
RUN pip install --no-deps -e /app/backend
WORKDIR /app/backend
ENV TZ=Asia/Shanghai PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
CMD ["python", "-m", "uvicorn", "lottery.api:app", "--host", "0.0.0.0", "--port", "8000"]
