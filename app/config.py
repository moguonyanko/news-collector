import os
try:
    import tomllib
except ImportError:
    import tomli as tomllib
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

def load_config():
    config_path = BASE_DIR / "config.toml"
    with open(config_path, "rb") as f:
        config = tomllib.load(f)
    return config

def get_settings():
    config = load_config()
    settings = config.get("settings", {})
    return {
        "urls": settings.get("urls", []),
        "default_days": settings.get("default_days", 7),
        "default_summary_length": settings.get("default_summary_length", 1000),
        "default_target": settings.get("default_target", "Beginner"),
        "gemini_model": settings.get("gemini_model", "gemini-2.5-flash"),
        "default_gemini_model": settings.get("default_gemini_model", "gemini-2.5-flash"),
        "max_articles": settings.get("max_articles", 10),
        "gemini_api_key": os.getenv("GEMINI_API_KEY")
    }
