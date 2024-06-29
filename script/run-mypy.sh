#!/usr/bin/env bash

set -o errexit

# other common virtualenvs
my_path=$(git rev-parse --show-toplevel)

if [ -f "${my_path}/venv/bin/activate" ]; then
  . "${my_path}/venv/bin/activate"
fi

mypy custom_components/powercalc
