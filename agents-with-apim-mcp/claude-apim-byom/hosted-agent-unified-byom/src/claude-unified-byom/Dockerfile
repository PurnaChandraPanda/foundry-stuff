FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 agent

COPY main.py .
USER agent

ENV PORT=8088
EXPOSE 8088
CMD ["python", "main.py"]
