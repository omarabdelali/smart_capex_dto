## Brief overview

Change management and specification tracking guidelines for the Smart CAPEX project. This ensures all requirement changes, scope modifications, and feature updates are properly documented with version control.

## Requirement tracking

- Track all new user requirements or scope changes during development sessions
- Document requirement changes in a dedicated tracking file or changelog
- Never assume a requirement is minor - always log it for traceability
- Include the date, requirement description, and rationale for changes

## Specification versioning

- Update project specification documents when requirements change
- Use semantic versioning for specification files (e.g., smart_capex_spec_v1.md → v2.md)
- Maintain version history in specification file header with change log
- Include what changed, why it changed, and when it changed
- Major changes (feature additions/removals) increment major version
- Minor changes (parameter adjustments, clarifications) increment minor version

## Documentation updates

- When user provides new requirements mid-session, update relevant documentation files:
  - Project specification (spec/smart_capex_spec_vX.md)
  - Data catalog if features change (spec/smart_capex_data_catalog_phase1.md)
  - Progress tracking (.tracking/progress.md)
  - README.md if project scope changes
- Create changelog entries with timestamp and description
- Keep old specification versions for reference (don't delete, rename with version suffix)

## Examples of trackable changes

- Feature additions or removals (e.g., "building height excluded from features")
- Parameter value changes (e.g., "alpha shape parameter fixed at 0.05")
- Data source modifications (e.g., "use Overture instead of OSM buildings")
- Algorithm changes (e.g., "noise points treated as single-site clusters")
- Model schema updates (e.g., "added cluster_id field to Site model")
- Performance or validation target changes (e.g., "MAPE target reduced to 12%")

## Version control workflow

- Create new specification version file when significant changes accumulate
- Add version header block to specification:
  ```markdown
  # Smart CAPEX Specification v2.0
  
  ## Version History
  - v2.0 (2026-10-24): Excluded building height feature, added cluster_id to Site model, fixed alpha=0.05
  - v1.0 (2026-10-23): Initial specification
  ```
- Update references to specification version in code comments and documentation
- Commit specification changes with clear commit messages describing what changed

## Change notification

- When updating specifications, briefly notify user of documentation updates
- Include which files were updated and what version number was assigned
- Provide summary of key changes documented