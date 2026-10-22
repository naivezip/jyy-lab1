from __future__ import annotations

import os

import pytest

from assistant.tools import default_registry
from assistant.tools.base import MAX_TOOL_OUTPUT


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return default_registry(str(tmp_path))


def run(registry, name, **kwargs):
    tool = registry.get(name)
    assert tool is not None
    return tool.run(kwargs)


def test_registry_exposes_five_tools(registry):
    assert [s.name for s in registry.specs] == ["read", "write", "bash", "fd", "grep"]


def test_read_returns_numbered_lines(registry, tmp_path):
    (tmp_path / "a.txt").write_text("one\ntwo\nthree\n")
    content, is_error = run(registry, "read", path="a.txt")
    assert not is_error
    assert content.splitlines() == ["     1\tone", "     2\ttwo", "     3\tthree"]


def test_read_offset_and_limit(registry, tmp_path):
    (tmp_path / "a.txt").write_text("\n".join(str(i) for i in range(10)) + "\n")
    content, _ = run(registry, "read", path="a.txt", offset=3, limit=2)
    assert "3\t2" in content
    assert "5\t4" not in content
    assert "more lines" in content


def test_read_missing_file_is_error(registry):
    content, is_error = run(registry, "read", path="nope.txt")
    assert is_error
    assert "No such file" in content


def test_read_refuses_binary(registry, tmp_path):
    (tmp_path / "b.bin").write_bytes(b"\x00\x01\x02")
    _, is_error = run(registry, "read", path="b.bin")
    assert is_error


def test_write_creates_parents(registry, tmp_path):
    content, is_error = run(registry, "write", path="deep/nested/f.txt", content="hi")
    assert not is_error
    assert (tmp_path / "deep/nested/f.txt").read_text() == "hi"
    assert "2 bytes" in content


def test_write_overwrites(registry, tmp_path):
    (tmp_path / "f.txt").write_text("old")
    run(registry, "write", path="f.txt", content="new")
    assert (tmp_path / "f.txt").read_text() == "new"


def test_bash_captures_stdout_stderr_and_code(registry):
    content, is_error = run(registry, "bash", command="echo out; echo err >&2; exit 3")
    assert not is_error
    assert "exit code: 3" in content
    assert "out" in content
    assert "err" in content


def test_bash_runs_in_cwd(registry, tmp_path):
    content, _ = run(registry, "bash", command="pwd")
    assert str(tmp_path) in content


def test_bash_timeout_is_error(registry):
    content, is_error = run(registry, "bash", command="sleep 5", timeout=1)
    assert is_error
    assert "timed out" in content.lower()


def test_fd_regex_and_glob(registry, tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.txt").write_text("")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "c.py").write_text("")

    by_regex, _ = run(registry, "fd", pattern=r"\.py$")
    assert by_regex.splitlines() == ["a.py"]

    by_glob, _ = run(registry, "fd", pattern="*.txt", glob=True)
    assert by_glob.splitlines() == ["b.txt"]


def test_fd_limit(registry, tmp_path):
    for i in range(5):
        (tmp_path / f"f{i}.txt").write_text("")
    content, _ = run(registry, "fd", pattern=r"\.txt$", limit=2)
    assert "stopped at limit=2" in content


def test_grep_reports_path_line_text(registry, tmp_path):
    (tmp_path / "x.py").write_text("alpha\nbeta\n")
    content, _ = run(registry, "grep", pattern="beta")
    assert content == "x.py:2: beta"


def test_grep_include_filter(registry, tmp_path):
    (tmp_path / "x.py").write_text("needle\n")
    (tmp_path / "x.txt").write_text("needle\n")
    content, _ = run(registry, "grep", pattern="needle", include="*.py")
    assert content == "x.py:1: needle"


def test_grep_skips_binary_and_git(registry, tmp_path):
    (tmp_path / "bin.dat").write_bytes(b"\x00needle")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "cfg").write_text("needle")
    content, _ = run(registry, "grep", pattern="needle")
    assert "No matches" in content


def test_grep_invalid_regex_is_error(registry):
    content, is_error = run(registry, "grep", pattern="[")
    assert is_error
    assert "Invalid regular expression" in content


def test_output_truncation(registry, tmp_path):
    (tmp_path / "big.txt").write_text("x" * (MAX_TOOL_OUTPUT + 100))
    content, _ = run(registry, "read", path="big.txt", limit=10_000)
    assert "truncated" in content
    assert len(content) < MAX_TOOL_OUTPUT + 200


def test_absolute_paths_allowed(registry, tmp_path):
    target = tmp_path / "abs.txt"
    target.write_text("absolute\n")
    content, _ = run(registry, "read", path=str(target))
    assert "absolute" in content
