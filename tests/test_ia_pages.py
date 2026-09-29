from pathlib import Path
import pytest
from lib.ui import PAGE_FILES

ROOT = Path(__file__).resolve().parents[1]


def _all_slugs():
    return sorted(PAGE_FILES.keys())


EMPTY_STATE = {
    "holdings": "Open the Command Center first",
    "funds": "Open the Command Center once so your funds",
    "intelligence": "Intelligence hasn't been computed in this session yet.",
    "pulse": "No news in this session yet",
    "outlook": "No FD book in this session yet.",
    "desk": "Nothing to show until the Command Center runs.",
    "asset-intelligence": "Open the Command Center first",
    "decisions": "Money to move",
}

STANDALONE = [
    ("2_Deep_Health.py", "decisions"),
    ("3_Asset_Detail.py", "holdings"),
    ("4_News.py", "pulse"),
    ("5_MF_Health.py", "funds"),
    ("6_Intelligence.py", "intelligence"),
    ("7_Outlook.py", "outlook"),
    ("8_Desk.py", "desk"),
    ("9_Asset_Intelligence.py", "asset-intelligence"),
]


def test_nav_groups_cover_all_pages():
    files = sorted(p.name for p in (ROOT / "pages").glob("*.py"))
    assert len(files) == 9, files
    slugs = _all_slugs()
    assert len(slugs) == 9, slugs
    for slug, file in PAGE_FILES.items():
        assert (ROOT / "pages" / Path(file).name).exists(), f"{slug} -> {file}"
    covered = {Path(PAGE_FILES[s]).name for s in slugs}
    assert {f for f in files if f != "1_Command_Center.py"} <= covered


def test_app_registers_all_nav_pages_with_hidden_position():
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'position="hidden"' in src
    for slug, file in PAGE_FILES.items():
        assert f'"{file}"' in src, f"app.py must register {slug} -> {file}"
    assert 'url_path="command"' in src


def _main_and_sidebar_md(at):
    main = [m.value for m in at.markdown]
    sidebar = [m.value for m in at.sidebar.markdown]
    return main, sidebar


@pytest.mark.parametrize("page_name,slug", STANDALONE)
def test_pages_render_empty_state_without_network(page_name, slug):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "pages" / page_name))
    at.run(timeout=180)
    assert not at.exception, f"{page_name} raised: {at.exception}"
    main, sidebar = _main_and_sidebar_md(at)
    all_md = main + sidebar
    assert any('aria-current="page"' in r for r in all_md)
    assert any("nb-group-label" in r for r in sidebar)
    for label, r in [("main", main), ("sidebar", sidebar)]:
        assert not any('href="../' in x for x in r)
    assert any(EMPTY_STATE[slug] in r for r in main)
