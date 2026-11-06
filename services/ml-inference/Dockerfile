FROM ghcr.io/astral-sh/uv:0.13.7 AS uv
FROM python:3.12.10-slim-bookworm AS runtime
WORKDIR /app
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY pyproject.toml uv.lock .python-version ./
COPY services/ml-inference/brainseg_inference/ services/ml-inference/brainseg_inference/
COPY services/ml-inference/logging.json /app/logging.json
COPY ml/training/ ml/training/
COPY ml/configs/ ml/configs/
RUN uv sync --frozen --no-dev --no-editable
RUN useradd --uid 10001 --create-home app
ENV PATH=/app/.venv/bin:$PATH
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=12 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()"
CMD ["uvicorn", "brainseg_inference.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--log-config", "/app/logging.json"]