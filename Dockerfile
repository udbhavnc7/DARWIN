FROM python:3.11-slim
WORKDIR /app
COPY requirements.lock.txt pyproject.toml ./
COPY backend ./backend
RUN pip install --no-cache-dir -r requirements.lock.txt && pip install --no-cache-dir --no-deps .
RUN useradd --create-home darwin
USER darwin
CMD ["python", "-m", "uvicorn", "darwin.shop.services:api", "--host", "0.0.0.0", "--port", "8000"]
