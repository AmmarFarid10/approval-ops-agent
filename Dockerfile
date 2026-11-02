FROM python:3.12-slim
WORKDIR /srv
COPY pyproject.toml uv.lock README.md ./
COPY app ./app
RUN pip install --no-cache-dir uv==0.13.4 && uv sync --frozen --no-dev --no-editable && useradd --uid 10001 --create-home app && mkdir /data && chown app /data
USER app
ENV DATA_PATH=/data/app.sqlite3
ENV PATH="/srv/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
