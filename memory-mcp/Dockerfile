FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --require-hashes -r requirements.txt && \
    groupadd --gid 10001 memory && useradd --uid 10001 --gid 10001 --no-create-home memory && \
    mkdir /index && chown 10001:10001 /index
COPY src ./src
USER 10001:10001
EXPOSE 3001
ENTRYPOINT ["python", "-m", "silverbullet_memory.server"]
