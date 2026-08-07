# Integration development

When you'd like to do development on the Powercalc integration, you can follow these steps to get started.

Powercalc uses a TDD (Test Driven Development) approach. This means that you write tests before you write the code. This ensures that the code is tested and regressions are prevented.
You can also write the tests after the code, but it's a requirement to have tests for the code you write before it can be merged into the main branch.
So it's highly recommended to use the tests to verify your changes. See the [Running the tests](#running-the-tests) section for more information.

## Setting up the development environment

### Using the dev container (recommended)

The repository ships a dev container that installs everything and runs Home Assistant with Powercalc already loaded, so you don't have to set up Home Assistant Core yourself.

1. Fork the repository, then open your fork either in VS Code with the [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension (**Reopen in Container**) or in a [GitHub Codespace](https://github.com/features/codespaces).
2. Wait for the container to build. It installs [uv](https://docs.astral.sh/uv/), the pinned Python version, all dependencies and the git hooks.
3. Start Home Assistant:

    ```bash
    script/develop.sh
    ```

    Home Assistant becomes available on [http://localhost:8123](http://localhost:8123) with debug logging enabled for Powercalc. The configuration lives in a `config/` directory that is not tracked by git. Restart Home Assistant to pick up code changes.

See [.devcontainer/README.md](https://github.com/bramstroker/homeassistant-powercalc/blob/master/.devcontainer/README.md) for more details.

### Manual setup

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

In order to run the tests, you need to install the dependencies.

Make sure you have uv installed:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Next install dependencies and enable virtual environment.

```bash
uv sync --locked --group=dev
tests/setup.sh
```

After the dependencies are installed, you can run the tests by executing the following command:

```bash
uv run pytest tests/
```

We strive at 100% test coverage, so please make sure to write tests for your code.
To check coverage you can run:

```bash
uv run pytest --cov custom_components.powercalc --cov-report xml:cov.xml --cov-report html tests/
```

This will generate a coverage report in the `htmlcov` directory.
