# Results and sessions

## GitHub contribution setup

GitHub authentication can be configured in **Settings** before starting a measurement. Device login is the recommended option and requests `public_repo` plus `workflow` access. Workflow access lets the app create a clean contribution branch from the latest upstream commit when the user's fork contains older GitHub Actions files. A personal access token with equivalent repository and workflow access is available as a fallback. The settings page shows the connected GitHub account and provides a disconnect action.

The credential is stored separately in the app's private `/data` directory and is never included in session diagnostics. Home Assistant may include it in app backups. Disconnect locally and revoke the OAuth authorization or token in GitHub when it is no longer needed.

After a completed light, speaker, fan, or charging measurement, the result page can prepare a profile contribution. Enter the marketed product name without repeating the manufacturer. When the manufacturer already exists, use the link to its library page to compare names and metadata with existing profiles. Review the manufacturer, model, exact file list, JSON, commit message, and pull-request text before explicitly creating the pull request. The app creates or reuses your fork and submits one device to the Powercalc `master` branch.

Manual contribution remains available at all times. You can still download every generated file and follow the contribution guide when GitHub is not configured, automatic contribution is unavailable, or an existing profile needs to be updated.

## Cancellation and resume

Cancellation is cooperative. A device request or configured wait already in progress may finish before the app stops changing the device. The app keeps complete output rows and does not mark partial output as completed.

Light LUT measurements can resume compatible partial output. Select **Resume** on the retained session to continue with the same light, meter, modes, and measurement settings. Other measurement types currently start a new session after interruption. If the dashboard does not offer resume, use **Duplicate config** to create a new draft with the stored measurement configuration. Duplication does not copy output or progress.

## Storage and backups

Requests, session state, events, and output are stored in the app's private `/data` directory. Completed, failed, and cancelled sessions remain available on the session dashboard until you explicitly confirm deletion. Home Assistant includes this directory in app backups. The app does not mount or write to the Home Assistant configuration directory.

Persisted GitHub credentials are also stored under `/data`, separately from preferences, sessions, and diagnostics. Treat app backups as sensitive while a GitHub account is connected.

The session dashboard provides per-session progress, file count, storage use, diagnostics, resume when compatible, configuration duplication, and explicit deletion. Opening a stopped session restores its result view, which provides:

- raw measurement and generated model files;
- interactive plots for supported output;
- high-resolution plot image downloads;
- a diagnostics download containing the session snapshot, request, events, logs, and file inventory for issue reports.

Entity IDs remain present in diagnostics because they are useful when troubleshooting entity selection and state updates. Download files through the authenticated ingress result view before removing the app or deleting its data.
