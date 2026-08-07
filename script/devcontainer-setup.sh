#!/usr/bin/env bash
#
# Provision the dev container. Run automatically as the postCreateCommand.

set -o errexit
set -o nounset
set -o pipefail

SCRIPTPATH="$(cd -- "$(dirname "$0")" >/dev/null 2>&1 && pwd -P)"
cd "$SCRIPTPATH/.."

# uv installs itself into ~/.local/bin, which is already on PATH in the base image.
if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# uv resolves and downloads the Python version pinned in pyproject.toml itself,
# so the base image does not need to ship a matching interpreter.
echo "Installing dependencies..."
uv sync --locked --group dev

echo "Linking test integration..."
tests/setup.sh

echo "Installing git hooks..."
uv run prek install

echo
echo "Ready. Run 'script/develop.sh' to start Home Assistant with Powercalc loaded."
