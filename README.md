# IPTV Manager

Local-first IPTV M3U playlist analyzer and optimizer.

## Development

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -e ".[dev]"
alembic upgrade head
pytest
uvicorn app.main:app --reload
```
