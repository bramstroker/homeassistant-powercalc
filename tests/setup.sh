SCRIPTPATH="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"

cd "$SCRIPTPATH/.."
pip install poetry
poetry install

cd "$SCRIPTPATH/../custom_components"
ln -sf ../tests/testing_config/custom_components/test test