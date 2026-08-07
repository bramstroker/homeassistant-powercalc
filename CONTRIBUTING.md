# Contributing to Powercalc

Thanks for helping out. Powercalc is community driven, and there is more than one way to contribute.

The full guides live at **[docs.powercalc.nl/contributing](https://docs.powercalc.nl/contributing/)**. This page is the short version.

## Ways to contribute

| I want to... | Start here |
| --- | --- |
| Add a device to the profile library | [Measuring and submitting power profiles](https://docs.powercalc.nl/contributing/measure/) |
| Fix a bug or build a feature | [Integration development](https://docs.powercalc.nl/contributing/integration-development/) |
| Translate Powercalc | [Translating](https://docs.powercalc.nl/contributing/translating/) |
| Report a bug | [Open an issue](https://github.com/bramstroker/homeassistant-powercalc/issues/new/choose) |
| Ask a question | [Discussions](https://github.com/bramstroker/homeassistant-powercalc/discussions) |

New device profiles are the most valuable contribution of all: they are what makes Powercalc accurate for everyone.

## Development setup

Powercalc uses [uv](https://docs.astral.sh/uv/) and targets the Python version pinned in `pyproject.toml`.

```bash
uv sync --locked --group dev
tests/setup.sh
uv run pytest tests/
```

A ready-made [dev container](.devcontainer/README.md) is available if you would rather not set up Home Assistant by hand — open the repository in VS Code or a Codespace and it starts a Home Assistant instance with Powercalc already loaded.

Full instructions, including running Powercalc against a local Home Assistant, are in [Integration development](https://docs.powercalc.nl/contributing/integration-development/).

## Before you open a pull request

- **Write tests.** Powercalc follows a test-driven approach and enforces **100% coverage** on `custom_components/powercalc`. CI will fail below that.
- **Run the checks.** `uv run prek run --all-files` runs the same lint, format, type and schema checks CI does.
- **Use [Conventional Commits](https://docs.powercalc.nl/contributing/commits/)** for commit messages, for example `fix(discovery): prevent duplicate device proposals`. Pull request titles do not need a prefix.
- **Keep it focused.** One concern per pull request is much easier to review than a mixed bag.
- **Do not hand-edit generated files.** `profile_library/library.json` is produced by CI.

## Reporting security issues

Please do not open a public issue. See [SECURITY.md](SECURITY.md) for how to report privately.

## Code of conduct

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
