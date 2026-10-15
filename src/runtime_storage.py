"""Seleciona SQLite local ou PostgreSQL/Neon conforme o ambiente."""

import os

if os.environ.get("DATABASE_URL"):
    try:
        from src.cloud_storage import *  # noqa: F403
    except ImportError:
        from cloud_storage import *  # noqa: F403
else:
    try:
        from src.storage import *  # noqa: F403
    except ImportError:
        from storage import *  # noqa: F403
