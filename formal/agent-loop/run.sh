#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

echo "== real Agent loop: bounded exhaustive check =="
uv run python formal/agent-loop/verify_agent_loop.py

version="1.7.4"
expected="936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88"
jar="${TLA2TOOLS:-$repo_root/formal/agent-loop/tla2tools-$version.jar}"
if [[ ! -f "$jar" ]]; then
    cache_root="${XDG_CACHE_HOME:-$HOME/.cache}/personal-agent-tla"
    mkdir -p "$cache_root"
    jar="$cache_root/tla2tools-$version.jar"
    tmp="$jar.part"
    echo "== downloading tla2tools $version =="
    curl -fsSL --retry 3 --retry-delay 2 \
        "https://github.com/tlaplus/tlaplus/releases/download/v$version/tla2tools.jar" -o "$tmp"
    echo "$expected  $tmp" | sha256sum -c -
    mv "$tmp" "$jar"
fi

echo "$expected  $jar" | sha256sum -c - >/dev/null

if ! command -v java >/dev/null 2>&1; then
    echo "java not found; install Java 17+ to run the TLA+ model check" >&2
    exit 2
fi

echo "== TLA+ model check =="
meta="$(mktemp -d)"
trap 'rm -rf "$meta"' EXIT
java -XX:+UseParallelGC -cp "$jar" tlc2.TLC \
    -metadir "$meta" \
    -config "$repo_root/formal/agent-loop/AgentLoop.cfg" \
    -workers 1 \
    "$repo_root/formal/agent-loop/AgentLoop.tla"
