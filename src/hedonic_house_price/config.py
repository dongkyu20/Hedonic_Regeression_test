from __future__ import annotations

import os
from pathlib import Path


SERVICE_KEY_ENV = "PUBLIC_DATA_SERVICE_KEY"


def load_env_file(path: str | Path = ".env") -> dict[str, str]:
    env_path = Path(path)
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def get_service_key(env: dict[str, str] | None = None, env_path: str | Path = ".env") -> str:
    merged: dict[str, str] = {}
    merged.update(load_env_file(env_path))
    merged.update(os.environ)
    if env is not None:
        merged.update(env)

    service_key = merged.get(SERVICE_KEY_ENV, "").strip()
    if not service_key:
        raise RuntimeError(f"{SERVICE_KEY_ENV} is required. Put it in .env or export it.")
    return service_key
