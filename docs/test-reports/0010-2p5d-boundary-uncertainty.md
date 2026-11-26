# Test report 0010: 2.5D, Boundary Supervision, and Uncertainty

**Disclaimer: For research and teaching only. Not a medical device; not for clinical diagnosis; no diagnostic, treatment, or prognosis advice.**

## Scope and evidence boundary

This report covers the 2.5D dataset/model/loss path, ONNX manifest/runtime contracts, NIfTI artifact persistence, ABP result metadata/download authorization, and Angular aligned layer display. Unit fixtures use synthetic arrays, NIfTI headers, synthetic inference outputs, and HTTP test doubles. They do not represent BraTS results or research-weight inference.

## Verification matrix

| Requirement area | Command / evidence | Status | Data source |
| --- | --- | --- | --- |
| Python training, data, model, loss, metrics, and inference tests | `.\.venv\Scripts\python.exe -m pytest -q` | Pass after final rerun recorded below | Synthetic fixtures and existing unit tests |
| Python lint | `.\.venv\Scripts\ruff.exe check ml services tests` | Pass after final rerun recorded below | Source |
| Python format | `.\.venv\Scripts\ruff.exe format --check ml services tests` | Pass after final rerun recorded below | Source |
| ABP/.NET build | `dotnet build apps/backend/BrainSeg.slnx --no-restore` | Pass; no warnings at last run | Source |
| Backend unit/integration suite | `dotnet test apps/backend/tests/BrainSeg.Tests/BrainSeg.Tests.csproj --no-restore` | Pass; PostgreSQL-only tests skipped when no test database is configured | SQLite/test doubles; not PostgreSQL |
| EF migration generation | `dotnet ef migrations add AddSegmentationUncertaintyArtifacts --project apps/backend/src/BrainSeg.EntityFrameworkCore/BrainSeg.EntityFrameworkCore.csproj --startup-project apps/backend/src/BrainSeg.HttpApi.Host/BrainSeg.HttpApi.Host.csproj --output-dir Migrations` | Pass; migration generated, not applied to a live PostgreSQL server | EF model |
| Angular unit tests | `Set-Location apps/web; npm test` | Pass; fixture-based | Synthetic NIfTI and HTTP mocks |
| Angular lint/build | `Set-Location apps/web; npm run lint; npm run build` | Pass | Source |
| Angular formatting/types | `Set-Location apps/web; npm run format:check; npx tsc --noEmit --project tsconfig.json` | Pass | Source |
| Real 2.5D research-weight inference | No registered real model manifest or weights | NotRun | Requires verified research ONNX weights |
| Full training, formal test set, three-seed results | No real BraTS dataset in the workspace | NotRun | Requires authorized BraTS data and frozen runs |
| GPU timing, memory, or performance claims | No GPU experiment run | NotRun | Requires a declared hardware environment |
| PostgreSQL migration and full Compose flow | No live PostgreSQL/Compose run for this change | NotRun | Requires controlled integration environment |
| Browser E2E against a real model/service | No real model/service environment | NotRun | Existing E2E fixtures are not real inference |

## Final local rerun evidence

Commands were rerun locally on 2026-11-26.

| Area | Exit | Actual result |
| --- | ---: | --- |
| Python pytest | 0 | 106 passed, 1 deprecation warning |
| Python Ruff check | 0 | All checks passed |
| Python Ruff format check | 0 | 48 files already formatted |
| .NET build | 0 | 0 warnings, 0 errors |
| .NET tests | 0 | 82 passed, 4 PostgreSQL tests skipped, 0 failed |
| Angular unit tests | 0 | 7 files passed, 18 tests passed |
| Angular lint | 0 | ESLint passed after proxy import cleanup |
| Angular format check | 0 | All checked files matched Prettier |
| Angular TypeScript check | 0 | `tsc --noEmit` passed |
| Angular build | 0 | Production build succeeded |
| Official ABP proxy generation | 0 | Generated from the local development API definition |

Skipped PostgreSQL tests remain explicitly skipped, not passed. Earlier failing attempts were used only to locate defects and are not counted as final passes.

## Measured module size

Parameter counts were computed from the actual configured PyTorch modules using channels `[32,64,128,256,512]`. They are structural counts, not accuracy or performance measurements.

| Model module | Parameters | Delta from A1 |
| --- | ---: | ---: |
| A1: legacy 2D Attention U-Net | 7,850,709 | baseline |
| A2: 2.5D center attention | 7,854,166 | +3,457 (+0.044%) |
| A3: boundary + deep supervision | 7,854,456 | +3,747 (+0.048%) |

## Unreported research outcomes

Patient Dice/IoU/Precision/Recall, HD95/ASSD, tumor volumes from actual cases, calibration, uncertainty-error discrimination, retention curves, checkpoint sizes, GPU peak memory, and inference-time distributions remain `NotRun`. No synthetic fixture value is presented as a paper result.
