from eca.config import get_sector, data_dir, skills_dir, quarter_dir, quarter_sort_key, COMPANY_NAMES
from eca.config import WATCHLIST_SECTORS


def test_get_sector_insurtech():
    assert get_sector("ROOT") == "insurtech"
    assert get_sector("LMND") == "insurtech"


def test_get_sector_default():
    assert get_sector("SPOT") == "base"
    assert get_sector("UNKNOWN") == "base"


def test_get_sector_case_insensitive():
    assert get_sector("root") == "insurtech"


def test_data_dir_resolves():
    d = data_dir()
    assert d.name == "data"


def test_skills_dir_resolves():
    d = skills_dir()
    assert d.name == "skills"


def test_quarter_dir():
    d = quarter_dir("ROOT", "q3-2025")
    assert d.parts[-1] == "q3-2025"
    assert d.parts[-2] == "root"


def test_company_names():
    assert "ROOT" in COMPANY_NAMES
    assert "LMND" in COMPANY_NAMES


def test_quarter_sort_key():
    assert quarter_sort_key("q1-2025") == (2025, 1)
    assert quarter_sort_key("q4-2024") == (2024, 4)


def test_quarter_sort_key_chronological_order():
    quarters = ["q1-2025", "q4-2024", "q3-2023", "q2-2026", "q2-2024"]
    result = sorted(quarters, key=quarter_sort_key)
    assert result == ["q3-2023", "q2-2024", "q4-2024", "q1-2025", "q2-2026"]


def test_quarter_sort_key_malformed():
    assert quarter_sort_key("bad") == (0, 0)


def test_watchlist_sectors_has_infra():
    assert "infra" in WATCHLIST_SECTORS
    assert "IREN" in WATCHLIST_SECTORS["infra"]
    assert "CIFR" in WATCHLIST_SECTORS["infra"]


def test_watchlist_sectors_all_tickers_in_sector_map():
    from eca.config import SECTOR_MAP
    for sector, tickers in WATCHLIST_SECTORS.items():
        for ticker in tickers:
            assert ticker in SECTOR_MAP, f"{ticker} in WATCHLIST_SECTORS[{sector}] but not in SECTOR_MAP"
