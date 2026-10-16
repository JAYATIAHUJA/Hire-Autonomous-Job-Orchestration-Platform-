# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/api

COPY requirements.txt .
# The pip cache lives in a BuildKit cache mount, not in the image: editing requirements.txt
# only downloads what changed instead of every wheel again. `locked` because compose builds
# api and worker from this file in parallel, and two pips sharing one cache read half-written wheels.
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked pip install -r requirements.txt

# Only the worker gets a browser (it fills application forms); the API image stays small.
ARG WITH_BROWSER=false
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    if [ "$WITH_BROWSER" = "true" ]; then \
      pip install "playwright>=1.45,<2" \
      && playwright install --with-deps chromium \
      && chmod -R a+rX /ms-playwright; \
    fi

COPY . .

RUN useradd --create-home --uid 10001 hire && chown -R hire /srv/api
USER hire

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
