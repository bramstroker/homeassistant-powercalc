# Dev container

A ready-to-use development environment for the Powercalc integration. It saves you from setting up Home Assistant Core by hand.

## Getting started

- **VS Code**: install the [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension, open this repository and choose **Reopen in Container**.
- **GitHub Codespaces**: click **Code → Codespaces → Create codespace** on the repository page.

The first build installs [uv](https://docs.astral.sh/uv/), which fetches the Python version pinned in `pyproject.toml`, syncs the locked dependencies and installs the git hooks. This takes a few minutes; later starts are quick.

## Running Home Assistant

```bash
script/develop.sh
```

This creates a `config/` directory on first run, links `custom_components/powercalc` into it and starts Home Assistant on <http://localhost:8123> with debug logging for Powercalc. Port 8123 is forwarded automatically.

Add Powercalc from **Settings → Devices & Services → Add Integration**. The `config/` directory is not tracked by git, so whatever you configure there stays between restarts and never ends up in a pull request.

Restart Home Assistant to pick up code changes.

## Running the checks

```bash
uv run pytest tests/                 # test suite
uv run prek run --all-files          # everything CI lints
```

See [CONTRIBUTING.md](../CONTRIBUTING.md) for what is expected before opening a pull request.
