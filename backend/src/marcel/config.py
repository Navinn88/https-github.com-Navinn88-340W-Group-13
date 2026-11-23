import os
from logging.config import dictConfig
from pathlib import Path

DATA_ROOT = Path(os.environ.get("DATA_ROOT", ""))
DATA_PATH = DATA_ROOT / os.environ.get("DATA_PATH", "")
FAQ_PATH = DATA_ROOT / os.environ.get("FAQ_PATH", "")
ADMINS_PATH = DATA_ROOT / os.environ.get("ADMINS_PATH", "")

LLM_BASE_URL = os.environ.get("LLM_BASE_URL")
LLM_API_KEY = os.environ.get("LLM_API_KEY")
MODEL_NAME = os.environ.get("MODEL_NAME")

SECRET_KEY = os.environ["SECRET_KEY"]
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"])

DATABASE_URI = os.environ.get("DATABASE_URI")


def _env(name: str, default: str) -> str:
    # docker compose passes unset variables as empty strings
    return os.environ.get(name) or default


# Hallucination detection with Kernel Language Entropy (see marcel/uncertainty.py)
KLE_ENABLED = _env("KLE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
KLE_NUM_SAMPLES = int(_env("KLE_NUM_SAMPLES", "5"))
KLE_TEMPERATURE = float(_env("KLE_TEMPERATURE", "1.0"))
KLE_HEAT_T = float(_env("KLE_HEAT_T", "1.0"))
KLE_THRESHOLD = float(_env("KLE_THRESHOLD", "0.4"))
KLE_NLI_MODEL = _env("KLE_NLI_MODEL", "cross-encoder/nli-deberta-v3-small")
KLE_SAMPLE_MODEL = _env("KLE_SAMPLE_MODEL", MODEL_NAME or "")
KLE_TIMEOUT = float(_env("KLE_TIMEOUT", "45"))


def setup_logging():
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s [%(processName)s: %(process)d] [%(levelname)s] %(name)s: %(message)s"
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
            "uvicorn_access": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
            "uvicorn_error": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
        },
        "loggers": {
            "uvicorn": {
                "handlers": ["uvicorn_error"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["uvicorn_access"],
                "level": "INFO",
                "propagate": False,
            },
            "marcel": {
                "handlers": ["default"],
                "level": "DEBUG",
                "propagate": False,
            },
            "__main__": {
                "handlers": ["default"],
                "level": "DEBUG",
                "propagate": False,
            },
            "": {
                "handlers": ["default"],
                "level": "WARNING",
                "propagate": False,
            },
        },
    }
    dictConfig(config)
