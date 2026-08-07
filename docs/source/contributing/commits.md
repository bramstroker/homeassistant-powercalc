# Commit messages

Powercalc uses [Conventional Commits](https://www.conventionalcommits.org/) for commit messages.
Pull request titles should remain concise and human-readable; they do not need a Conventional Commit prefix.

Use this format:

```text
<type>[optional scope][optional !]: <description>
```

Write the type and scope in lowercase. Keep the description short, imperative, and without a trailing period.

## Types

| Type | Use for |
| --- | --- |
| `feat` | A new user-visible capability |
| `fix` | A user-visible bug fix |
| `perf` | A performance improvement |
| `refactor` | An internal code change that neither fixes a bug nor adds a feature |
| `docs` | Documentation-only changes |
| `test` | Adding or correcting tests without changing production behavior |
| `build` | Build tooling, packaging, or artifact creation |
| `ci` | CI configuration and workflow changes |
| `chore` | Maintenance that does not fit another type, including generated files and release preparation |
| `style` | Formatting-only changes with no behavior change |

Following Conventional Commits, `feat` indicates a minor change and `fix` indicates a patch change. Add `!` before the colon for a breaking change, for example `feat!: remove YAML configuration support`. Explain the migration or impact in the commit body.

## Scopes

Scopes are optional. Use one when it identifies a stable subsystem more clearly than the description alone.

| Scope | Area |
| --- | --- |
| `profile` | Power profiles and profile-library generation |
| `measure` | The measurement utility and Home Assistant Measure app |
| `translations` | Translation resources and Crowdin synchronization |
| `deps` | Dependency and lock-file updates |
| `agents` | Agent instructions and repository skills |
| `discovery` | Integration discovery |
| `configuration` | Integration configuration flows and validation |
| `sensors` | Power, energy, cost, utility-meter, and group sensors |
| `strategies` | Calculation strategies |

For a change spanning the main integration, omit the scope rather than using a generic `integration` scope. Do not use filenames, issue numbers, device model names, or temporary project names as scopes.

## Examples

```text
feat: add standby energy sensor
fix(discovery): prevent duplicate device proposals
feat(profile): add signify LCT010
fix(measure): stop runs after repeated zero readings
chore(deps): update GitHub Actions
docs: explain commit message conventions
ci: validate profile JSON
```
