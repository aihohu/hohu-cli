import json
from pathlib import Path

# 全局配置目录：~/.hohu/
CONFIG_DIR = Path.home() / ".hohu"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {"language": "auto"}


def load_config():
    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG


def save_config(config: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def get_lang():
    return load_config().get("language", "auto")
