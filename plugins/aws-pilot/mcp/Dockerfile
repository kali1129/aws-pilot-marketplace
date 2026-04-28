FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install AWS CLI v2 (some skills shell out to it)
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip \
    && unzip -q awscliv2.zip \
    && ./aws/install \
    && rm -rf awscliv2.zip aws

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

# Audit log volume
VOLUME ["/data"]
ENV AWS_PILOT_AUDIT_LOG=/data/audit.jsonl
ENV PYTHONUNBUFFERED=1

# For VPS deployment, run as MCP-over-HTTP (FastMCP supports SSE/streamable-http)
# For local dev, MCP runs over stdio (override CMD: python server.py)
EXPOSE 8080
CMD ["python", "server.py", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8080"]
