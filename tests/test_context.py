from __future__ import annotations

from pathlib import Path

from assistant.context import build_system_prompt, find_agents_files


def make_git_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    return root


def test_outside_git_only_reads_cwd(tmp_path, monkeypatch):
    (tmp_path / "AGENTS.md").write_text("outer rules")
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text("inner rules")

    files = find_agents_files(str(project))
    assert files == [project / "AGENTS.md"]


def test_outside_git_without_file_reads_nothing(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    assert find_agents_files(str(project)) == []


def test_inside_git_collects_outside_in(tmp_path):
    root = make_git_root(tmp_path)
    (root / "AGENTS.md").write_text("root rules")
    nested = root / "pkg" / "sub"
    nested.mkdir(parents=True)
    (nested / "AGENTS.md").write_text("nested rules")

    files = find_agents_files(str(nested))
    assert files == [root / "AGENTS.md", nested / "AGENTS.md"]


def test_stops_at_git_root(tmp_path):
    outside = tmp_path / "AGENTS.md"
    outside.write_text("must not load")
    root = make_git_root(tmp_path)
    assert find_agents_files(str(root)) == []


def test_system_prompt_includes_rules_in_order(tmp_path):
    root = make_git_root(tmp_path)
    (root / "AGENTS.md").write_text("root rules")
    nested = root / "sub"
    nested.mkdir()
    (nested / "AGENTS.md").write_text("nested rules")

    prompt = build_system_prompt(str(nested))
    assert prompt.index("root rules") < prompt.index("nested rules")
    assert "pa" in prompt
