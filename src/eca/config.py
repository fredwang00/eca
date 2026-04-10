"""Project configuration: ticker mappings, directory resolution."""

from pathlib import Path

SECTOR_MAP: dict[str, str] = {
    # Insurtech
    "ROOT": "insurtech",
    "LMND": "insurtech",
    # Mega-cap / Core AI
    "NVDA": "base",
    "MSFT": "base",
    "GOOG": "base",
    "META": "base",
    "AMZN": "base",
    "AAPL": "base",
    "TSLA": "base",
    "PLTR": "base",
    # Alpha portfolio / Bitcoin-miner-to-AI
    "IREN": "base",
    "CIFR": "base",
    "HUT": "base",
    "WULF": "base",
    "NBIS": "base",
    "CRWV": "base",
    "MSTR": "base",
    "BMNR": "base",
    "COIN": "base",
    "GLXY": "base",
    "METAPLANET": "base",
    # Venture sleeve
    "ASTS": "base",
    "EOSE": "base",
    # Macro sensors
    "OPEN": "base",
    "RKLB": "base",
    "UBER": "base",
    "ABNB": "base",
    "SHOP": "base",
    "CRCL": "base",
    "WMT": "base",
    "COST": "base",
    "TGT": "base",
    "AFRM": "base",
    "SOFI": "base",
    "JPM": "base",
    "COF": "base",
    "AXP": "base",
    "NFLX": "base",
    # Discretionary bellwethers
    "NKE": "base",
    "RH": "base",
    "LULU": "base",
    # Other
    "HIMS": "base",
    "HOOD": "base",
    "SPOT": "base",
}

COMPANY_NAMES: dict[str, str] = {
    # Insurtech
    "ROOT": "Root, Inc.",
    "LMND": "Lemonade, Inc.",
    # Mega-cap / Core AI
    "NVDA": "NVIDIA Corporation",
    "MSFT": "Microsoft Corporation",
    "GOOG": "Alphabet Inc.",
    "META": "Meta Platforms, Inc.",
    "AMZN": "Amazon.com, Inc.",
    "AAPL": "Apple Inc.",
    "TSLA": "Tesla, Inc.",
    "PLTR": "Palantir Technologies Inc.",
    # Alpha portfolio / Bitcoin-miner-to-AI
    "IREN": "IREN (formerly Iris Energy)",
    "CIFR": "Cipher Digital (formerly Cipher Mining)",
    "HUT": "Hut 8 Corp.",
    "WULF": "TeraWulf Inc.",
    "NBIS": "Nebius Group N.V.",
    "CRWV": "CoreWeave, Inc.",
    "MSTR": "Strategy (formerly MicroStrategy)",
    "BMNR": "Bitmine Immersion Technologies",
    "COIN": "Coinbase Global, Inc.",
    "GLXY": "Galaxy Digital Holdings Ltd.",
    "METAPLANET": "Metaplanet Inc.",
    # Venture sleeve
    "ASTS": "AST SpaceMobile, Inc.",
    "EOSE": "Eos Energy Enterprises, Inc.",
    # Macro sensors
    "OPEN": "Opendoor Technologies Inc.",
    "RKLB": "Rocket Lab USA, Inc.",
    "UBER": "Uber Technologies, Inc.",
    "ABNB": "Airbnb, Inc.",
    "SHOP": "Shopify Inc.",
    "CRCL": "Circle Internet Group, Inc.",
    "WMT": "Walmart Inc.",
    "COST": "Costco Wholesale Corporation",
    "TGT": "Target Corporation",
    "AFRM": "Affirm Holdings, Inc.",
    "JPM": "JPMorgan Chase & Co.",
    "COF": "Capital One Financial Corporation",
    "AXP": "American Express Company",
    "NFLX": "Netflix, Inc.",
    # Other
    "NKE": "NIKE, Inc.",
    "RH": "RH (Restoration Hardware)",
    "LULU": "Lululemon Athletica Inc.",
    "HIMS": "Hims & Hers Health, Inc.",
    "HOOD": "Robinhood Markets, Inc.",
    "SOFI": "SoFi Technologies, Inc.",
    "SPOT": "Spotify Technology S.A.",
}


WATCHLIST_SECTORS: dict[str, list[str]] = {
    "ai":       ["NVDA", "MSFT", "GOOG", "META", "AMZN", "AAPL", "TSLA", "PLTR"],
    "infra":    ["IREN", "CIFR", "HUT", "WULF", "NBIS", "CRWV"],
    "crypto":   ["MSTR", "BMNR", "COIN", "GLXY", "CRCL"],
    "space":    ["RKLB", "ASTS"],
    "consumer": ["OPEN", "UBER", "ABNB", "SHOP", "LMND", "ROOT", "WMT", "COST", "TGT", "NKE", "RH", "LULU", "AFRM", "SOFI", "JPM", "COF", "AXP"],
    "venture":  ["EOSE"],
    "employer": ["SPOT", "NFLX"],
    "meme":     ["HIMS", "HOOD"],
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


def quarter_sort_key(slug: str) -> tuple[int, int]:
    """Convert a quarter slug like 'q3-2024' to (2024, 3) for chronological sorting."""
    parts = slug.split("-")
    if len(parts) == 2 and parts[0].startswith("q"):
        return (int(parts[1]), int(parts[0][1:]))
    return (0, 0)
