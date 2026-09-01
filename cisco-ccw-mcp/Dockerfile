FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Render/Fly/Railway injetam a porta via variável de ambiente PORT em alguns
# casos — MCP_PORT é a que este projeto lê (ver app/config.py). Se sua
# plataforma usar $PORT, ajuste MCP_PORT=$PORT no comando de start ou nas
# env vars do serviço.
ENV MCP_TRANSPORT=streamable-http
EXPOSE 8000

CMD ["python", "-m", "app.main"]
