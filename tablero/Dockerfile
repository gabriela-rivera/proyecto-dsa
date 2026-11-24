# Imagen del tablero. Contexto de construcción: la carpeta tablero/
#   docker build -t flota-tablero ./tablero
#   docker run -p 8050:8050 -e API_URL=http://<ip-de-la-api>:8001 flota-tablero
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PORT=8050 \
    API_URL=http://3.18.4.17:8001

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8050
# "/" solo devuelve la página base: no depende de que la API esté encendida
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:%s/' % os.environ['PORT'])"
# Render y otros servicios entregan el puerto en la variable PORT
CMD ["sh", "-c", "gunicorn app:server --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 120"]
