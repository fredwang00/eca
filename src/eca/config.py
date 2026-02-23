"""Project configuration: ticker mappings, directory resolution."""

from pathlib import Path

SECTOR_MAP: dict[str, str] = {
    "ROOT": "insurtech",
    "LMND": "insurtech",
    "HIMS": "base",
    "SPOT": "base",
    "GOOG": "base",
    "TSLA": "base",
}

COMPANY_NAMES: dict[str, str] = {
    "ROOT": "Root, Inc.",
    "LMND": "Lemonade, Inc.",
    "HIMS": "Hims & Hers Health, Inc.",
    "SPOT": "Spotify Technology S.A.",
    "GOOG": "Alphabet Inc.",
    "TSLA": "Tesla, Inc.",
}


def project_root() -> Path:
    """Walk up from this file to find pyproject.toml."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    raise FileNotFoundError("Could not find project root")


def data_dir() -> Path:
    return project_root() / "data"


def skills_dir() -> Path:
    return project_root() / "skills"


def quarter_dir(ticker: str, quarter: str) -> Path:
    return data_dir() / ticker.lower() / quarter


def get_sector(ticker: str) -> str:
    return SECTOR_MAP.get(ticker.upper(), "base")
