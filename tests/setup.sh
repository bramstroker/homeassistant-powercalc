SCRIPTPATH="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"

python3 -m pip install -r ${SCRIPTPATH}/../requirements.test.txt

cd "$SCRIPTPATH/../custom_components"
ln -sf ../tests/testing_config/custom_components/test test