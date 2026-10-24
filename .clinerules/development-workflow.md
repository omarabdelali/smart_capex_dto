## Brief overview

Development workflow preferences for the Smart CAPEX project. Focus on implementation over planning, minimal human interaction for routine tasks, and autonomous execution through multiple development phases.

## Communication style

- Skip planning phases dedicated to human review when working on well-defined implementation tasks
- Proceed directly to implementation when requirements are clear
- Work through multiple phases (Phase 1 through Phase 6+) autonomously without stopping for approval between phases
- Update progress tracking files silently without announcing updates
- Provide technical, direct responses without conversational fluff (avoid "Great", "Certainly", "Okay", "Sure")

## Development workflow

- Execute implementation phases sequentially without pausing for human approval between phases
- Work autonomously through Phase 1 (Django foundation) → Phase 2 (Data loaders) → Phase 3 (Launch detection) → Phase 4 (Feature computation) → Phase 5 (Similarity engine) → Phase 6 (REST API) without stopping
- Only pause for human input when encountering actual blockers or ambiguities
- Update `.tracking/progress.md` after completing each milestone
- Proceed with implementation immediately when data sources are verified and requirements are clear

## Task execution

- When told to "work on all phases", execute them sequentially in a single session
- Do not create separate planning documents for each phase - move directly to code implementation
- Verify data availability first, then implement without additional planning cycles
- Focus on writing functional code rather than creating architectural documentation
- Test implementations as you go but don't wait for approval to proceed to next phase

## Progress tracking

- Maintain `.tracking/progress.md` with current status
- Update task progress parameter in tool calls to reflect completion
- Mark items complete as they finish, don't wait to update until end of session
- Progress updates are for system tracking, not for announcing to user

## Project context

- Smart CAPEX Phase 1: Django + Vue.js + Leaflet web application
- Database: SQLite + SpatiaLite (configurable for PostgreSQL)
- All geographic data already present (DEM, WorldCover, OSM, GHSL)
- MAOS monthly KPI data available for launch detection
- 56 Phase 1 features documented in data catalog
- Work confined to `project_smart_capex` directory