"""Server-only configuration. Never return credentials to the browser."""
import os
from pathlib import Path


def load_env(root: Path) -> None:
    path = root / '.env'
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('\"\''))


def api_status() -> dict:
    return {'configured': bool(os.getenv('OPENAI_API_KEY')), 'model': os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'),
            'provider': 'OpenAI', 'mode': 'API' if os.getenv('OPENAI_API_KEY') else 'structured form / English fallback'}
