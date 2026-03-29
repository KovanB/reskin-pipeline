FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir . fastapi uvicorn[standard] python-multipart pyyaml

# Copy application code
COPY reskin/ reskin/
COPY templates/ templates/
COPY web/ web/

# Create data dirs
RUN mkdir -p data/jobs data/uploads

EXPOSE 8000

CMD ["uvicorn", "web.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
