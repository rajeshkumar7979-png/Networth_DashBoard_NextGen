# Holdings dossier — load the last known-good page body from git history.
# A prior empty push wiped this file; this bootstrap restores behaviour without
# embedding the full 50KB source in the deploy path. Replace with the in-repo
# body once the full tape-table + Interpret patch is committed normally.
from __future__ import annotations

import ast
import pathlib
import urllib.request

_COMMIT = "e1840d9"
_PATH = "pages/3_Asset_Detail.py"
_URL = (
    f"https://raw.githubusercontent.com/rajeshkumar7979-png/"
    f"Networth_DashBoard_NextGen/{_COMMIT}/{_PATH}"
)
_CACHE = pathlib.Path(__file__).resolve().parents[1] / "data" / "_asset_detail_body.py"


def _load_body() -> str:
    if _CACHE.exists() and _CACHE.stat().st_size > 1000:
        return _CACHE.read_text(encoding="utf-8")
    with urllib.request.urlopen(_URL, timeout=30) as resp:
        text = resp.read().decode("utf-8")
    if "Interpret this instrument" not in text:
        raise RuntimeError("restored Holdings body failed sanity check")
    # Strip this bootstrap if the remote ever points at itself.
    if text.lstrip().startswith("# Holdings dossier — load the last known-good"):
        raise RuntimeError("refusing to exec bootstrap as body")
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE.write_text(text, encoding="utf-8")
    return text


_body = _load_body()
# Compile first so a bad fetch fails closed instead of partial exec.
ast.parse(_body)
exec(compile(_body, str(_CACHE), "exec"), globals())
