import json
from functools import lru_cache

@lru_cache(maxsize=1)
def load_config():
    """Load and cache configuration from config.json."""
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

config = load_config()
SITES = config["sites"]
SCORING_RULES = config["scoring_rules"]
