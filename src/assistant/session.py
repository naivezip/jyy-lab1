"""Append-only JSONL session store under ~/.pa/projects/<hash>/sessions/."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from assistant.messages import Message


def project_dir(cwd: str) -> Path:
    digest = hashlib.sha1(str(Path(cwd).resolve()).encode()).hexdigest()[:12]
    return Path.home() / ".pa" / "projects" / digest / "sessions"


def new_session_path(cwd: str) -> Path:
    directory = project_dir(cwd)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return directory / f"{stamp}-{secrets.token_hex(2)}.jsonl"


def latest_session(cwd: str) -> Path | None:
    directory = project_dir(cwd)
    if not directory.is_dir():
        return None
    files = sorted(directory.glob("*.jsonl"))
    return files[-1] if files else None


def list_sessions(cwd: str) -> list[Path]:
    directory = project_dir(cwd)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.jsonl"), reverse=True)


@dataclass
class Compaction:
    summary: str
    replaced_upto: int


@dataclass
class Session:
    path: Path
    messages: list[Message] = field(default_factory=list)
    compactions: list[Compaction] = field(default_factory=list)

    @classmethod
    def create(cls, cwd: str) -> Session:
        return cls(path=new_session_path(cwd))

    @classmethod
    def load(cls, path: Path) -> Session:
        session = cls(path=path)
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("type") == "compaction":
                session.compactions.append(
                    Compaction(record["summary"], record["replaced_upto"])
                )
            elif record.get("type") == "message":
                session.messages.append(Message.from_dict(record["message"]))
        return session

    def active_messages(self) -> list[Message]:
        """The history a resumed session should continue from.

        Only the latest compaction matters: its summary already folds in any
        earlier ones.
        """
        if not self.compactions:
            return list(self.messages)
        last = self.compactions[-1]
        summary = Message(
            role="user",
            text=f"Summary of the earlier conversation:\n\n{last.summary}",
        )
        return [summary] + self.messages[last.replaced_upto:]

    def append(self, message: Message) -> None:
        self.messages.append(message)
        self._write({"type": "message", "message": message.to_dict()})

    def append_many(self, messages: list[Message]) -> None:
        for message in messages:
            self.append(message)

    def append_compaction(self, summary: str) -> None:
        self.compactions.append(Compaction(summary, len(self.messages)))
        self._write(
            {"type": "compaction", "summary": summary, "replaced_upto": len(self.messages)}
        )

    def _write(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
