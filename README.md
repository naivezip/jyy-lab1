# personal-agent

[![CI](https://github.com/naivezip/jyy-lab1/actions/workflows/ci.yml/badge.svg)](https://github.com/naivezip/jyy-lab1/actions/workflows/ci.yml)

A personal agent for the terminal. The project is being refactored; this
repository currently contains the CI foundation only.

## CI

| Command | Purpose |
| --- | --- |
| `make lint` | Ruff lint plus formatting check |
| `make test` | Pytest (prints a notice while no test files exist) |
| `make ci` | `lint` + `test` |

GitHub Actions runs the same targets on every push to `main` and every pull
request; `workflow_dispatch` is available for manual runs.

The six acceptance criteria for the refactor are tracked in
[docs/ACCEPTANCE.md](docs/ACCEPTANCE.md).
