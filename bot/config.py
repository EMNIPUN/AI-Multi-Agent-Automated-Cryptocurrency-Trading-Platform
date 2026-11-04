import os

from dotenv import load_dotenv

load_dotenv()


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}


API_KEY = os.getenv("BYBIT_API_KEY", "").strip()
API_SECRET = os.getenv("BYBIT_API_SECRET", "").strip()
USE_TESTNET = _flag("BYBIT_TESTNET", "true")
USE_DEMO = _flag("BYBIT_DEMO", "false")


def env_label() -> str:
    if USE_DEMO:
        return "Demo Trading"
    return "Testnet" if USE_TESTNET else "Mainnet"


def is_live_mainnet() -> bool:
    return not USE_TESTNET and not USE_DEMO
