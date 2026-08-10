FROM python:3.12-slim

WORKDIR /app

ARG BUILD_GIT_SHA
LABEL org.opencontainers.image.revision=$BUILD_GIT_SHA

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["python", "standings.py", "serve"]
