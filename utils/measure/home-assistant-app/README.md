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

Measure CLI and app releases share one version and are versioned from the main Powercalc repository with a plain `measure-v` git tag, for example `measure-v0.2.0`. The GitHub release itself is published in this app-store repository: HACS reads the published releases of the main repository to resolve Powercalc integration versions, so the main repository must never publish a `measure-v*` release (plain tags and draft releases are invisible to HACS).

Every pull request merged to master that touches `utils/measure` (or carries the `measure-tool` label) is appended to the rolling `measure-next` draft release in the main repository by the **Measure Release** workflow, and excluded from the main integration release notes. Keep the `## Unreleased` section in `powercalc_measure/CHANGELOG.md` empty; the draft is the single source of unreleased notes.

The next version is resolved automatically from the merged pull requests and shown in the draft title: breaking changes (a conventional-commit `!` marker or a `major`/`breaking` label) bump major, features (`feat:` titles or `feature`/`enhancement` labels) bump minor, and everything else bumps patch. Explicit `major`/`minor`/`patch` labels override the resolution per pull request.

To release:

1. Review the rolling `Powercalc Measure v<version> (unreleased)` draft in the main repository.
2. Run the **Prepare Measure Release** workflow. Leave the version empty to use the resolved version from the draft title, or pass one to override. Enable `dry_run` to preview and validate without creating a branch.
3. Review and merge the generated release pull request. Everything after the merge is automatic.

On merge, the **Measure Release** workflow detects the new changelog section, pushes the `measure-v0.2.0` tag, and dispatches the publish workflow on that tag. That builds both artifacts with distinct embedded versions (`v0.2.0:cli` for the CLI image, `v0.2.0:app` for the Home Assistant app), mirrors the app metadata to this repository after the images are pullable, creates the `v0.2.0` GitHub release here with the changelog notes, and finally deletes the rolling draft in the main repository so the next cycle starts empty. Measure pull requests merged while the publish pipeline is still running should be re-added to the fresh draft by hand if the draft deletion swallowed them.

For local troubleshooting, export the draft body to a file and run from `utils/measure`:

```shell
uv run python prepare_app_release.py 0.2.0 --notes-file /tmp/measure-app-release-notes.md --dry-run
uv run python prepare_app_release.py 0.2.0 --notes-file /tmp/measure-app-release-notes.md
```

The notes file must contain release notes only: use `###` headings for categories and do not include a release title or `#`/`##` headings. The script adds that Markdown as the exact body of the new changelog version and rejects empty or structurally invalid notes, duplicate changelog versions, and inconsistent current versions.
