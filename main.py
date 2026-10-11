
import os
from pathlib import Path

import yaml
from dotenv import dotenv_values
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

BASE_DIR = Path(__file__).resolve().parent

DEFAULTS = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

ALIASES = {"num_workers": "workers"}

app = FastAPI(title="Effective Config API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def normalize_key(key):
    key = str(key).strip().lower()
    return ALIASES.get(key, key)


def coerce(key, value):
    if key in ("port", "workers"):
        return int(value)

    if key == "debug":
        if isinstance(value, bool):
            return value
        value = str(value).strip().lower()
        if value in ("true", "1", "yes", "on"):
            return True
        if value in ("false", "0", "no", "off"):
            return False
        raise ValueError(f"Invalid boolean: {value}")

    return str(value)


def normalize(mapping):
    result = {}
    for raw_key, value in mapping.items():
        key = normalize_key(raw_key)
        if key in DEFAULTS and value is not None:
            result[key] = coerce(key, value)
    return result


def get_effective_config(overrides):
    config = DEFAULTS.copy()

    # 1. Environment-specific YAML
    env_name = os.getenv("APP_ENV", "development")
    yaml_path = BASE_DIR / f"config.{env_name}.yaml"

    if yaml_path.exists():
        with yaml_path.open(encoding="utf-8") as f:
            config.update(normalize(yaml.safe_load(f) or {}))

    # 2. .env file
    file_env = dotenv_values(BASE_DIR / ".env")
    file_config = {}

    for key, value in file_env.items():
        if value is None:
            continue
        if key.startswith("APP_"):
            file_config[key[4:]] = value
        elif key == "NUM_WORKERS":
            file_config["workers"] = value

    config.update(normalize(file_config))

    # 3. OS-level APP_* variables
    os_config = {
        key[4:]: value
        for key, value in os.environ.items()
        if key.startswith("APP_")
    }

    if "NUM_WORKERS" in os.environ:
        os_config["workers"] = os.environ["NUM_WORKERS"]

    config.update(normalize(os_config))

    # 4. CLI-style query overrides
    config.update(normalize(overrides))

    # Return exactly the required keys and types
    return {
        "port": int(config["port"]),
        "workers": int(config["workers"]),
        "debug": config["debug"],
        "log_level": str(config["log_level"]),
        "api_key": "*****",
    }


@app.get("/effective-config")
def effective_config(set: list[str] | None = Query(default=None)):
    overrides = {}

    for item in set or []:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = normalize_key(key)

        if key in DEFAULTS:
            overrides[key] = value

    return get_effective_config(overrides)


@app.get("/")
def root():
    return {"status": "ok", "endpoint": "/effective-config"}
