FROM python:3.11-slim

WORKDIR /app

ARG INCLUDE_TESTS=0

# Install minimal OS deps and upgrade pip
RUN apt-get update && apt-get install -y --no-install-recommends git wget curl \
 && rm -rf /var/lib/apt/lists/*

ENV PIP_ROOT_USER_ACTION=ignore
RUN pip install --no-cache-dir --upgrade pip

# Install all orchestrator deps early for better cache reuse
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy orchestrator code after deps are installed
COPY . /app/orchestrator

# Optionally include tests in the image (when not using bind-mount)
RUN if [ "$INCLUDE_TESTS" = "1" ]; then mkdir -p /app/tests && \
    if [ -d "/app/orchestrator/../tests" ]; then cp -r /app/orchestrator/../tests /app/; fi; \
    fi

ENV PYTHONUNBUFFERED=1
ENV PORT=8000
CMD ["uvicorn", "orchestrator.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
