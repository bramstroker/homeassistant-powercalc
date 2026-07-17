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

The application source and the multi-architecture image build live in the main Powercalc repository. The published metadata references `ghcr.io/bramstroker/powercalc-measure-app:<version>`, where the image tag is taken from `powercalc_measure/config.yaml`. Release images are built with the official Home Assistant Builder actions and signed keylessly with Cosign through GitHub Actions OIDC.

For development with a pre-built image, copy `powercalc_measure/` to `/addons/powercalc_measure` on a Home Assistant OS host and reload the app store. The referenced image version must already exist in GHCR. Source builds use the `ha-app` target in `utils/measure/Dockerfile` and are tested from the main repository rather than by Supervisor cloning the full Powercalc source tree.

## Preparing a release

Measure CLI and app releases share one version and are drafted and published from the main Powercalc repository with a `measure-v` tag, for example `measure-v0.2.0`. This generated app-store repository does not have its own releases.

All changes below `utils/measure` are collected in the dedicated Measure Release Drafter draft and excluded from the main integration release notes. Keep the `## Unreleased` section in `powercalc_measure/CHANGELOG.md` empty.

To prepare a release:

1. Review the `Powercalc Measure` draft release in the main repository.
2. Run the **Prepare Measure Release** workflow with the unprefixed version from that draft, for example `0.2.0`. Enable `dry_run` to preview and validate without creating a branch.
3. Review and merge the generated release pull request.
4. Publish the existing draft release. Its `measure-v0.2.0` tag must match the version in the merged app config.

The workflow copies the shared Measure draft notes into the Home Assistant changelog, synchronizes every app version source, and opens a release pull request labelled `skip-changelog`. Publishing the draft builds both artifacts with distinct embedded versions: `v0.2.0:cli` for the CLI image and `v0.2.0:app` for the Home Assistant app. The app-store repository is updated only after the app image is available.

For local troubleshooting, export the draft body to a file and run from `utils/measure`:

```shell
uv run python prepare_app_release.py 0.2.0 --notes-file /tmp/measure-app-release-notes.md --dry-run
uv run python prepare_app_release.py 0.2.0 --notes-file /tmp/measure-app-release-notes.md
```

The notes file must contain release notes only: use `###` headings for categories and do not include a release title or `#`/`##` headings. The script adds that Markdown as the exact body of the new changelog version and rejects empty or structurally invalid notes, duplicate changelog versions, and inconsistent current versions.

For the one-time `0.1.0` bootstrap, align the initial draft body with the existing `0.1.0` changelog and publish `measure-v0.1.0` from the already-versioned source without running the preparation workflow. This establishes the independent Measure version history for future drafts.
