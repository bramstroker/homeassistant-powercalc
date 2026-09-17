# Measure package layout

The CLI and Home Assistant app share the same request, assembly and execution pipeline.

| Module or package | Responsibility |
| --- | --- |
| `request.py`, `tuning.py` | Validated measurement settings and sampling parameters. |
| `assembler.py` | Construct meters, controllers, samplers and runners. |
| `execution.py` | Run preparation, measurement, cleanup and profile generation. |
| `utils/sampling.py` | `PowerSampler`: readings, averaging, retries and dummy-load correction. |
| `runner/` | Device-specific measurement workflows; `interaction.py` defines progress and user interaction contracts. |
| `controller/`, `powermeter/` | Device control and power-meter adapters. |
| `home_assistant/` | Shared HA client, entity catalog and protocol constants. |
| `recording/` | Capture policy, recording filenames and ordered file discovery. |
| `analyser/` | Load recordings into analysis models, fit candidates, validate and write analysis results. |
| `profile/` | Profile models, metadata, preparation, validation and local/ZIP output. |
| `contribution/` | GitHub credentials, contribution jobs and pull-request submission. |
| `cli/` | Terminal questions, settings and interaction. |
| `ha_app/` | App dependencies, preflight, sessions, persistence and HTTP entry point. |
| `ha_app/routes/` | Measurement, session and contribution endpoints. |
| `ha_app/contribution/` | App-specific contribution drafts, authentication flows and submission state. |
| `visualization/`, `ocr/` | Plotting and optional optical meter capture. |
| `utils/clock.py`, `utils/files.py`, `utils/version.py` | Small shared helpers. |

## Dependency boundaries

- Runners report through `runner/interaction.py`; CLI and app adapters implement that contract.
- `recording/` owns shared file conventions. Analysis and storage both use it.
- `profile/` prepares artifacts; `contribution/` consumes them for GitHub submission.
- `home_assistant/` serves both frontends and device adapters. `ha_app/` owns the app lifecycle.
- `ha_app/api.py` creates the application and mounts routers. `context.py` constructs app
  dependencies; `api_models.py` defines payloads; `errors.py` translates failures to HTTP.
- Feature-specific constants stay with their owner. Root `const.py` contains shared
  measurement types, defaults and parameter bounds.

Workflow package initializers stay lightweight. Import coordinators and services directly
from their modules to avoid implicit dependencies and import-order cycles.

`tests/test_architecture.py` checks dependency boundaries and imports key modules in fresh
Python processes. See [Recorder and analyser architecture](RECORDER_ANALYSER_ARCHITECTURE.md)
for the recording and fitting flow.
