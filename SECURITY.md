# Security Policy

## Supported Versions

Only the **latest release** of PowerCalc receives security fixes. Please reproduce issues against the most recent version on [HACS](https://hacs.xyz/) or [GitHub Releases](https://github.com/bramstroker/homeassistant-powercalc/releases) before reporting.

## Reporting a Vulnerability

**Do not open a public issue for security problems.**

Report privately via [GitHub Security Advisories](https://github.com/bramstroker/homeassistant-powercalc/security/advisories/new), or email `bgerritsen@gmail.com` with the subject `[powercalc-security]`.

Please include:

- PowerCalc and Home Assistant versions
- Steps to reproduce and impact
- Logs or a proof-of-concept (with secrets redacted)

## What to Expect

PowerCalc is maintained by volunteers, so responses are best-effort. You can expect an acknowledgement within a few days and a coordinated fix and disclosure once the issue is confirmed. Reporters are credited in the advisory unless they prefer to stay anonymous.

## Scope

In scope: code in this repository, the remote profile loader, and configuration handling.

Out of scope: bugs in Home Assistant itself, third-party dependencies (report upstream), and functional bugs such as inaccurate power estimates — please use regular [issues](https://github.com/bramstroker/homeassistant-powercalc/issues) for those.
