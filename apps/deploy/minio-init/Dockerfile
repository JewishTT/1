FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir boto3==1.40.54

COPY init-buckets.py /usr/local/bin/init-buckets.py

ENTRYPOINT ["python", "/usr/local/bin/init-buckets.py"]
