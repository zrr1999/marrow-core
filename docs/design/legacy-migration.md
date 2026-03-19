# Legacy asset migration status

The following profile-coupled assets have been removed from `marrow-core` and should live in external repos:

- `lib.sh`
- `setup.sh`
- `context.d/`
- `prompts/`
- `marrow.toml`
- `roles.toml`

## Target state

### stays in core

- runtime scheduler
- CLI
- IPC
- health checks
- service rendering
- work-item contract
- plugin/background-service host contract

### moves out of core

- profile prompts and rules
- context providers
- role definitions and casting config
- deployment-specific sample config
- opinionated setup wrappers

## Current migration path

- `marrow-core` no longer needs in-repo prompt rules as the default prompt source.
- `install-service` now works from the provided runtime config path instead of assuming `marrow-core/marrow.toml`.
- new recommended flow is external-profile-first.

Compatibility is now expected to come from external runtime/profile repos rather than in-repo defaults.
