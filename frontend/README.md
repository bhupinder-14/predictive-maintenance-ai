# Predictive Maintenance Command Center frontend

## Requirements

- Node.js 22.12.0 or newer (the supported engine range is declared in `package.json`).
- npm, using the checked-in `package-lock.json` (lockfile version 3).
- Chromium installed by Playwright for browser tests.

The project pins direct dependencies to exact versions. Do not use a global Vite, Vitest, TypeScript, or Playwright installation.

## Install and run

From this directory:

```powershell
npm ci
npm run dev
```

Vite listens on `127.0.0.1:5173`. Browser API calls use same-origin `/api`. The development proxy strips that prefix and forwards to `http://127.0.0.1:8000` by default. To point it at a different local backend in PowerShell:

```powershell
$env:API_PROXY_TARGET = "http://127.0.0.1:8000"
npm run dev
```

`API_PROXY_TARGET` is Vite development-server configuration, not a browser secret or production API URL.

## Checks

```powershell
npm run typecheck
npm test -- --configLoader runner --reporter=dot
npm run build -- --configLoader runner
npm ls --depth=0
```

The project does not currently configure a Vitest coverage provider. CI therefore runs the full unit suite without producing coverage output.

## Playwright end-to-end tests

Install the Chromium build pinned by the Playwright package lock, then run the browser suite:

```powershell
npm ci
npx playwright install chromium
npm run test:e2e
```

Use `npm run test:e2e:headed` to run Chromium with a visible window. Playwright always starts its own local Vite server on `127.0.0.1:4175`; that port must be free. It never reuses an existing server. The tests intercept same-origin `/api/*` requests and return controlled fixtures shaped like the FastAPI contracts. They cover navigation, equipment and paginated history, prediction results and errors, drift, readiness, mobile navigation, and accessible chart tables. They do not require credentials, a running backend, or access to a project database.

These mocked browser tests exercise the frontend behavior. They do not verify FastAPI integration, the Vite-to-backend proxy at runtime, persistence, or deployment. No optional backend-connected smoke mode is provided because prediction and drift operations write data; a future smoke mode would need an explicitly isolated disposable database.

## CI

`.github/workflows/frontend-ci.yml` runs for pull requests into `master`, pushes to `master`, and manual dispatch. It uses Node.js 22.12.0, runs `npm ci`, typecheck, all Vitest tests, the production build, `npm ls --depth=0`, installs Playwright Chromium, and runs the mocked API browser suite. Failures fail the job; test screenshots/traces and the HTML report are uploaded only after a job failure.

The CI job does not connect to a real backend and does not establish complete WCAG conformance. Automated browser and unit tests complement manual browser, keyboard, screen-reader, and backend integration checks.
