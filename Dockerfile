FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# 1 worker: o estado de conversa (_ESTADOS em bot_logic.py) fica em memoria e
# nao e compartilhado entre processos. Com mais de 1 worker, mensagens do
# mesmo cliente podem cair em processos diferentes e perder o estado (ex: o
# modo de silencio pos-atendente). Trocar para mais workers exige antes mover
# esse estado para Redis/banco.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--timeout", "60", "-k", "uvicorn.workers.UvicornWorker", "main:app"]
