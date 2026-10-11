
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

ALIASES = {
    "num_workers": "workers",
}

app = FastAPI(title="Effective Config API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def coerce(key, value):
    if key in ("port", "workers"):
        return int(value)

    if key == "debug":
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if normalized in ("true", "1", "yes", "on"):
            return True
        if normalized in ("false", "0", "no", "off"):
            return False
        raise ValueError(f"Invalid boolean: {value}")

    return str(value)


def normalize(mapping):
    result = {}
    for key, value in mapping.items():
        key = str(key).strip().lower()
        key = ALIASES.get(key, key)
        if key in DEFAULTS:
            result[key] = coerce(key, value)
    return result


def get_effective_config(overrides):
    # Layer 1: defaults
    config = DEFAULTS.copy()

    # Layer 2: environment-specific YAML
    env_name = os.getenv("APP_ENV", "development")
    yaml_path = BASE_DIR / f"config.{env_name}.yaml"

    if yaml_path.exists():
        with yaml_path.open(encoding="utf-8") as file:
            yaml_config = yaml.safe_load(file) or {}
        config.update(normalize(yaml_config))

    # Layer 3: .env file
    file_env = dotenv_values(BASE_DIR / ".env")
    file_config = {
        key.removeprefix("APP_").lower(): value
        for key, value in file_env.items()
        if key.startswith("APP_") and value is not None
    }

    # Special alias: NUM_WORKERS -> workers
    if file_env.get("NUM_WORKERS") is not None:
        file_config["workers"] = file_env["NUM_WORKERS"]

    config.update(normalize(file_config))

    # Layer 4: actual OS environment variables
    os_config = {
        key.removeprefix("APP_").lower(): value
        for key, value in os.environ.items()
        if key.startswith("APP_")
    }

    if "NUM_WORKERS" in os.environ:
        os_config["workers"] = os.environ["NUM_WORKERS"]

    config.update(normalize(os_config))

    # Layer 5: dynamic CLI-style query overrides
    config.update(normalize(overrides))

    # Never expose the actual secret
    config["api_key"] = "*****"

    return config


@app.get("/effective-config")
def effective_config(
    set: list[str] | None = Query(default=None)
):
    overrides = {}

    for item in set or []:
        if "=" not in item:
            continue

        key, value = item.split("=", 1)
        key = key.strip().lower()
        key = ALIASES.get(key, key)

        if key in DEFAULTS:
            overrides[key] = value

    return get_effective_config(overrides)


@app.get("/")
def root():
    return {"status": "ok", "endpoint": "/effective-config"}
