# Powercalc Apps

Home Assistant apps (add-ons) for [Powercalc](https://github.com/bramstroker/homeassistant-powercalc).

[![Add repository to my Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fbramstroker%2Fpowercalc-measure-app)

Or add the repository URL manually under **Settings > Apps > App store** in Home Assistant:

```
https://github.com/bramstroker/powercalc-measure-app
```

## Apps

### Powercalc Measure (experimental)

Create device power profiles from Home Assistant entities — lights, speakers, fans, charging robots, or any load with a power sensor — through an authenticated ingress UI. See the app's Documentation tab for setup and usage.

## Issues and contributing

This repository is generated from [`utils/measure/home-assistant-app`](https://github.com/bramstroker/homeassistant-powercalc/tree/master/utils/measure/home-assistant-app) in the main Powercalc repository; changes pushed here directly are overwritten on the next release. Report issues and open pull requests in [homeassistant-powercalc](https://github.com/bramstroker/homeassistant-powercalc).

## Development

The application source and the multi-architecture image build live in the main Powercalc repository. The published metadata references `ghcr.io/bramstroker/powercalc-measure-app:<version>`, where the image tag is taken from `powercalc_measure/config.yaml`.

For development with a pre-built image, copy `powercalc_measure/` to `/addons/powercalc_measure` on a Home Assistant OS host and reload the app store. The referenced image version must already exist in GHCR. Source builds use the `ha-app` target in `utils/measure/Dockerfile` and are tested from the main repository rather than by Supervisor cloning the full Powercalc source tree.

## Preparing a release

Add user-visible changes below `## Unreleased` in `powercalc_measure/CHANGELOG.md`. From `utils/measure`, preview and prepare the release with:

```shell
uv run python prepare_app_release.py 0.2.0 --dry-run
uv run python prepare_app_release.py 0.2.0
```

The script promotes the unreleased notes and keeps the app config, frontend package, and package lock versions in sync. Review and commit the resulting diff before publishing the Home Assistant app workflow.
