"""Tools exposed to the model."""

from __future__ import annotations

from .bash import BASH_TOOL_SPEC, BashTool
from .edit import EDIT_TOOL_SPEC, EditTool
from .read import READ_TOOL_SPEC, ReadTool
from .write import WRITE_TOOL_SPEC, WriteTool

TOOL_SPECS: tuple[dict[str, object], ...] = (
    BASH_TOOL_SPEC,
    READ_TOOL_SPEC,
    WRITE_TOOL_SPEC,
    EDIT_TOOL_SPEC,
)

__all__ = [
    "BASH_TOOL_SPEC",
    "EDIT_TOOL_SPEC",
    "READ_TOOL_SPEC",
    "TOOL_SPECS",
    "WRITE_TOOL_SPEC",
    "BashTool",
    "EditTool",
    "ReadTool",
    "WriteTool",
]
