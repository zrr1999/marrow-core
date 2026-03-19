Legacy backups from the pre-service-split runtime live here.

These files are kept only as reference snapshots while `marrow-core`
is reduced to service/runtime responsibilities.

Rules:
- nothing under `marrow_core/` should import from `legacy/`
- tests should not rely on these backups
- task/work-item behavior is no longer part of the active core
