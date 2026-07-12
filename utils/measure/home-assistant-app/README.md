# Powercalc Apps repository metadata

This directory is the source-controlled, mirror-ready Home Assistant app repository. `repository.yaml` must become the root file when this directory is published as the dedicated lightweight app repository; `powercalc_measure/` is the app folder consumed by Supervisor.

The application source and multi-architecture image build remain in the main Powercalc repository. The published metadata references `ghcr.io/bramstroker/powercalc-measure-app:<version>`, where the image tag is taken from `powercalc_measure/config.yaml`.

For development with a pre-built image, copy `powercalc_measure/` to `/addons/powercalc_measure` on a Home Assistant OS host and reload the app store. The referenced image version must already exist in GHCR. Source builds use the `ha-app` target in `utils/measure/Dockerfile` and are tested from this repository rather than by Supervisor cloning the full Powercalc source tree.
