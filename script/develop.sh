#!/usr/bin/env bash
#
# Start Home Assistant with Powercalc loaded from the working tree.
# The config directory is created on first run and is not tracked by git,
# so anything you configure in the UI survives restarts.

set -o errexit
set -o nounset
set -o pipefail

SCRIPTPATH="$(cd -- "$(dirname "$0")" >/dev/null 2>&1 && pwd -P)"
cd "$SCRIPTPATH/.."

CONFIG_DIR="config"

mkdir -p "$CONFIG_DIR/custom_components"
ln -sfn ../../custom_components/powercalc "$CONFIG_DIR/custom_components/powercalc"

if [ ! -f "$CONFIG_DIR/configuration.yaml" ]; then
  echo "Creating $CONFIG_DIR/configuration.yaml"
  cat >"$CONFIG_DIR/configuration.yaml" <<'YAML'
default_config:

logger:
  default: info
  logs:
    custom_components.powercalc: debug
YAML
fi

echo "Starting Home Assistant on http://localhost:8123"
exec uv run hass --config "$CONFIG_DIR" --debug
