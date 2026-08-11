FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV TERM=xterm-256color
ENV PROC_ROOT=/proc

CMD ["python", "-m", "src.main"]
