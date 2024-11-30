# Integration development

When you'd like to do development on the Powercalc integration, you can follow these steps to get started.

Powercalc uses a TDD (Test Driven Development) approach. This means that you write tests before you write the code. This ensures that the code is tested and regressions are prevented.
You can also write the tests after the code, but it's a requirement to have tests for the code you write before it can be merged into the main branch.
So it's highly recommended to use the tests to verify your changes. See the [Running the tests](#running-the-tests) section for more information.

## Setting up the development environment

1. Setup a development environment for Home Assistant Core. Follow the instructions on the [Home Assistant Developer Documentation](https://developers.home-assistant.io/docs/development_environment).
2. Fork and clone the Powercalc repository:

    ```bash
    git clone https://github.com/YOUR_GIT_USERNAME/homeassistant-powercalc
    cd homeassistant-powercalc
    git remote add upstream https://github.com/bramstroker/homeassistant-powercalc.git
    ```

3. Copy or symlink the `custom_components/powercalc` directory to your Home Assistant configuration directory:

    ```bash
    ln -s $(pwd)/custom_components/powercalc /path/to/your/homeassistant/config/custom_components/powercalc
    ```

4. Start Home Assistant Core in development mode:

    ```bash
    hass -c /path/to/your/homeassistant/config --dev
    ```

## Running the tests

In order to run the tests, you need to install the dependencies. You can do this by running the following command:

```bash
poetry env use 3.13
tests/setup.sh
poetry install --no-root
```

After the dependencies are installed, you can run the tests by executing the following command:

```bash
poetry run pytest tests/
```

We strive at 100% test coverage, so please make sure to write tests for your code.
To check coverage you can run:

```bash
poetry run pytest --cov custom_components.powercalc --cov-report xml:cov.xml --cov-report html tests/
```

This will generate a coverage report in the `htmlcov` directory.
