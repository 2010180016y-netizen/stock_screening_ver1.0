FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt pyproject.toml README.md ./
COPY vcb_alt ./vcb_alt
COPY data/snapshots.example.csv ./data/snapshots.example.csv

RUN python -m pip install --no-cache-dir -r requirements.txt

EXPOSE 8765

CMD ["python", "-m", "vcb_alt", "web", "--host", "0.0.0.0", "--port", "8765"]
