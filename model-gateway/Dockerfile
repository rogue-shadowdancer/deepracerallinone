FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir .

ENV GATEWAY_DATA_DIR=/data
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "model_gateway.app:app", "--host", "0.0.0.0", "--port", "8080"]
