FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HANDA_LLM_PROVIDER=mock \
    ANONYMIZED_TELEMETRY=False \
    PORT=43123

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

EXPOSE 43123
CMD ["python", "-m", "handa"]
