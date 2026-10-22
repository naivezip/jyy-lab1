"""Networking environment fixes required by the HTTP clients we use.

httpx2 (the transport under openai>=3 and anthropic>=2) builds proxy mount keys
from NO_PROXY entries. A bracketed IPv6 entry such as ``[::1]`` becomes the mount
key ``all://*[::1]``, which the same library then rejects with
``Invalid port: ':1]'`` while constructing any client. Normalising the entry to
its unbracketed form avoids the crash without disabling proxy support.
"""

from __future__ import annotations

import os

_PROXY_VARS = ("NO_PROXY", "no_proxy")


def sanitize_proxy_env() -> None:
    """Rewrite bracketed IPv6 entries in NO_PROXY in place. Idempotent."""
    for name in _PROXY_VARS:
        raw = os.environ.get(name)
        if not raw or "[" not in raw:
            continue
        entries = []
        for entry in raw.split(","):
            entry = entry.strip()
            if entry.startswith("[") and "]" in entry:
                host, _, port = entry.partition("]")
                entry = host[1:] + (port if port.startswith(":") else "")
            entries.append(entry)
        os.environ[name] = ",".join(entries)
