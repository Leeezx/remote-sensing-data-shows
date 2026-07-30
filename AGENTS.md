# Repository Guidelines

## Project Structure & Module Organization

- `backend/` contains the FastAPI application, API routers, raster/data services, and Python tests in `backend/tests/`.
- `frontend/` contains the React + TypeScript + Vite app. Reusable UI lives in `frontend/src/components/`, page views in `frontend/src/pages/`, API calls in `frontend/src/services/`, and shared types in `frontend/src/types/`.
- `data/` stores checked-in metadata, time-series, statistics, and other application data. Processing utilities are in `scripts/`; documentation and design notes are in `docs/`.
- Keep large local rasters and generated tiles under the ignored `data/rasters/` and `data/tiles/` paths.

## Build, Test, and Development Commands

Run from the repository root unless noted:

- `npm install` installs root tooling; `npm run install:all` installs frontend and backend dependencies.
- `npm run dev` starts the Vite frontend and reload-enabled FastAPI backend together.
- `npm run build` type-checks and builds the frontend into `frontend/dist/`.
- `npm test` runs the backend and frontend test suites.
- `npm run test:backend` runs `pytest backend/tests/ -v`; `npm run test:frontend` runs Vitest once.
- `cd frontend; npm run lint` runs Oxlint.

## Coding Style & Naming Conventions

Use four spaces and standard imports in Python; use two spaces, single quotes, and no semicolons in TypeScript/TSX, matching existing code. Name Python modules and functions with `snake_case`, React components and types with `PascalCase`, and variables/functions with `camelCase`. Keep API boundaries typed through `frontend/src/types/` and place route-specific backend logic in `backend/routers/`.

## Testing Guidelines

Backend tests use pytest and are named `test_*.py`; frontend tests use Vitest + Testing Library and are named `*.test.ts` or `*.test.tsx`. Add regression coverage for changed API, data-processing, or UI behavior. Run `npm test` and the frontend lint command before submitting; no project-wide coverage threshold is currently configured.

## Commit & Pull Request Guidelines

Use concise Conventional Commit messages, for example `feat: add region averages endpoint` or `fix: handle zero as nodata`. Pull requests should explain the behavior change, list validation commands, link any issue or design note, and include screenshots for visible UI changes. For API or data changes, document affected endpoints, fixtures, or generated files.

## Security & Configuration

Copy `.env.example` to a local `.env`; never commit credentials, JWT secrets, or local raster data. Review CORS and authentication changes carefully, and keep generated artifacts out of commits unless they are intentional application fixtures.
