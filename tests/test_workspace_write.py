"""workspace_write — anchor-based atomic replace for agent workspace sections."""
import pytest

from workspace_write import WorkspaceAnchorNotFound, workspace_write

WS = """\
# workspace — payments API review
## findings
### tech-architect
*(populated by TA)*

### product-strategist
*(populated by PS)*
"""


@pytest.fixture
def ws(tmp_path):
    path = tmp_path / "workspace.md"
    path.write_text(WS, encoding="utf-8")
    return path


def test_replaces_own_section_only(ws):
    workspace_write(str(ws), "### tech-architect\n*(populated by TA)*",
                    "### tech-architect\nF[TA-1] |HIGH |idempotency keys |source:independent-research|")
    text = ws.read_text()
    assert "F[TA-1]" in text
    assert "*(populated by TA)*" not in text
    assert "### product-strategist\n*(populated by PS)*" in text


def test_missing_anchor_raises_and_leaves_file(ws):
    with pytest.raises(WorkspaceAnchorNotFound):
        workspace_write(str(ws), "### security-specialist\n*(populated)*", "anything")
    assert ws.read_text() == WS


def test_noop_replace_raises(ws):
    anchor = "### tech-architect\n*(populated by TA)*"
    with pytest.raises(WorkspaceAnchorNotFound):
        workspace_write(str(ws), anchor, anchor)
    assert ws.read_text() == WS


def test_only_first_occurrence_replaced(tmp_path):
    path = tmp_path / "workspace.md"
    path.write_text("A\nmarker\nB\nmarker\n")
    workspace_write(str(path), "marker", "done")
    assert path.read_text() == "A\ndone\nB\nmarker\n"


def test_unicode_anchor(ws):
    path = ws
    path.write_text("### devils-advocate\nΣComm ¬ résumé → ✓\n", encoding="utf-8")
    workspace_write(str(path), "ΣComm ¬ résumé → ✓", "DA[#1] ✓ done")
    assert path.read_text(encoding="utf-8") == "### devils-advocate\nDA[#1] ✓ done\n"


def test_expands_user(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "ws.md").write_text("old\n")
    workspace_write("~/ws.md", "old", "new")
    assert (tmp_path / "ws.md").read_text() == "new\n"


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        workspace_write(str(tmp_path / "absent.md"), "a", "b")
