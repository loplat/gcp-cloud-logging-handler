FROM python:3.11-slim AS base

WORKDIR /app
COPY Pipfile ./
COPY Pipfile.lock ./

RUN apt update \
    && apt install -y gcc \
    && pip install --no-cache-dir pipenv \
    && PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy \
    && rm -f Pipfile* \
    && apt clean \
    && rm -rf /root/.cache/* && rm -rf /var/cache/*

FROM python:3.11-slim AS venv
COPY --from=base /app/.venv /app/.venv
COPY --from=base /usr/local /usr/local
ENV PATH="/app/.venv/bin:$PATH"

FROM venv AS code
WORKDIR /app
COPY . /app
# ENTRYPOINT [ "/bin/bash"]
ENV PYTHONUNBUFFERED=1
CMD uvicorn --host 0.0.0.0 --port 8080 main:app --no-proxy-headers --no-access-log --log-level $LOG_LEVEL