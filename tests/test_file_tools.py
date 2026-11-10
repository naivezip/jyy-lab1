"""Contract tests for the workspace-confined file tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from personal_agent.tools import EditTool, ReadTool, WriteTool


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


def test_read_returns_header_and_six_width_numbered_lines(workspace: Path) -> None:
    (workspace / "notes.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    content, is_error = ReadTool(str(workspace)).run({"path": "notes.txt"})

    assert is_error is False
    assert content == "lines 1-3 of 3\n     1\talpha\n     2\tbeta\n     3\tgamma\n"


def test_read_pages_by_inclusive_line_range(workspace: Path) -> None:
    (workspace / "notes.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    content, is_error = ReadTool(str(workspace)).run({"path": "notes.txt", "start": 2, "end": 3})

    assert is_error is False
    assert content == "lines 2-3 of 3\n     2\tbeta\n     3\tgamma\n"


def test_read_preserves_original_line_endings(workspace: Path) -> None:
    (workspace / "crlf.txt").write_bytes(b"alpha\r\nbeta\r\n")

    content, _ = ReadTool(str(workspace)).run({"path": "crlf.txt"})

    assert content.startswith("lines 1-2 of 2\n")
    assert "     1\talpha\r\n" in content
    assert "     2\tbeta\r\n" in content


def test_read_reports_missing_and_binary_files(workspace: Path) -> None:
    (workspace / "binary.dat").write_bytes(b"\x00\x01")
    tool = ReadTool(str(workspace))

    missing, missing_error = tool.run({"path": "missing.txt"})
    binary, binary_error = tool.run({"path": "binary.dat"})

    assert missing_error is True
    assert "No such file" in missing
    assert binary_error is True
    assert "UTF-8" in binary


def test_write_creates_new_file_and_parents(workspace: Path) -> None:
    content, is_error = WriteTool(str(workspace)).run(
        {"path": "deep/nested/created.txt", "content": "created\n"}
    )

    assert is_error is False
    assert content == "Wrote 8 bytes to deep/nested/created.txt"
    assert (workspace / "deep/nested/created.txt").read_text(encoding="utf-8") == "created\n"


def test_write_refuses_to_modify_existing_file(workspace: Path) -> None:
    target = workspace / "notes.txt"
    target.write_text("alpha\n", encoding="utf-8")

    content, is_error = WriteTool(str(workspace)).run(
        {"path": "notes.txt", "content": "replacement\n"}
    )

    assert is_error is True
    assert "already exists" in content
    assert "use edit" in content
    assert target.read_text(encoding="utf-8") == "alpha\n"


def test_edit_replaces_inclusive_line_range(workspace: Path) -> None:
    target = workspace / "notes.txt"
    target.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    content, is_error = EditTool(str(workspace)).run(
        {"path": "notes.txt", "start": 2, "end": 2, "content": "BETA\n"}
    )

    assert is_error is False
    assert content == "Edited notes.txt: replaced lines 2-2 of 3"
    assert target.read_text(encoding="utf-8") == "alpha\nBETA\ngamma\n"


def test_edit_preserves_crlf_style(workspace: Path) -> None:
    target = workspace / "crlf.txt"
    target.write_bytes(b"alpha\r\nbeta\r\ngamma\r\n")

    _, is_error = EditTool(str(workspace)).run(
        {"path": "crlf.txt", "start": 2, "end": 2, "content": "BETA"}
    )

    assert is_error is False
    assert target.read_bytes() == b"alpha\r\nBETA\r\ngamma\r\n"


def test_edit_missing_file_points_to_write(workspace: Path) -> None:
    content, is_error = EditTool(str(workspace)).run(
        {"path": "missing.txt", "start": 1, "end": 1, "content": "x"}
    )

    assert is_error is True
    assert "does not exist" in content
    assert "use write" in content


@pytest.mark.parametrize("tool_name", ["read", "write", "edit"])
def test_file_tools_reject_parent_directory_escape(workspace: Path, tool_name: str) -> None:
    outside = workspace.parent / f"{workspace.name}-outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    try:
        tool = {"read": ReadTool, "write": WriteTool, "edit": EditTool}[tool_name](str(workspace))
        arguments = {"path": "../" + outside.name}
        if tool_name == "write":
            arguments["content"] = "nope"
        elif tool_name == "edit":
            arguments.update({"start": 1, "end": 1, "content": "nope"})

        content, is_error = tool.run(arguments)

        assert is_error is True
        assert "outside the workspace" in content
        assert outside.read_text(encoding="utf-8") == "outside\n"
    finally:
        outside.unlink()


def test_file_tools_reject_symlink_target_outside_workspace(workspace: Path) -> None:
    outside = workspace.parent / f"{workspace.name}-linked.txt"
    outside.write_text("outside\n", encoding="utf-8")
    link = workspace / "link.txt"
    link.symlink_to(outside)
    try:
        content, is_error = ReadTool(str(workspace)).run({"path": "link.txt"})

        assert is_error is True
        assert "outside the workspace" in content
    finally:
        link.unlink()
        outside.unlink()


def test_absolute_path_inside_workspace_is_allowed(workspace: Path) -> None:
    target = workspace / "absolute.txt"
    target.write_text("absolute\n", encoding="utf-8")

    content, is_error = ReadTool(str(workspace)).run({"path": str(target)})

    assert is_error is False
    assert "absolute" in content
