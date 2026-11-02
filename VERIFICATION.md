# Verification — 3 November 2026
Python 3.12.14; dependencies installed using `uv sync --frozen --extra dev`.

- `uv run pytest -q`: 9 passed.
- `uv run ruff check .`: passed.
- `uv run mypy app --ignore-missing-imports`: passed (not strict; missing third-party stubs ignored).
- `uv run pip-audit`: no known vulnerabilities reported for the tested environment. Advisory absence does not prove security.

Docker engine was unavailable, so image build/startup was not executed. Ollama and downloaded model weights were not configured; model adapters were reviewed and offline boundary tests ran, but model output quality is unverified. No load, browser, external integration or adversarial security certification was performed.
