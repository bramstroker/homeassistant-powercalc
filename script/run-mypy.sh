#!/usr/bin/env bash

set -o errexit

uv run mypy custom_components/powercalc
