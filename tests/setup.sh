#!/usr/bin/env bash

SCRIPTPATH="$(cd -- "$(dirname "$0")" >/dev/null 2>&1 || exit; pwd -P)"

cd "$SCRIPTPATH/../custom_components" || exit
ln -sf ../tests/testing_config/custom_components/test test
