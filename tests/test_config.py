from eca.config import get_sector, data_dir, skills_dir, quarter_dir, COMPANY_NAMES


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
