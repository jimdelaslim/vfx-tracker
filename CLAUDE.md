# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Hard rules (non-negotiable)
- Existing .db files MUST remain backward compatible. Schema changes use ALTER TABLE ADD COLUMN with column-existence checks in app.py — never rename, drop, or change column types without explicit discussion.
- Never overwrite user-set start_frame during metadata import (find_metadata_by_cam_roll and related paths).
- ALE parsing: use rstrip(), never strip(), to preserve column alignment.
- isSwitchingDatabase flag must be set BEFORE closing picker windows on Windows (prevents premature app quit).
- Keyboard shortcuts: use e.code for Alt/Option (Mac Option+letter creates special chars), e.ctrlKey || e.metaKey for cross-platform Cmd/Ctrl.
- Python 3.13 required for OpenTimelineIO. Do NOT suggest upgrading to 3.14.
- Shot.start_frame is String(50) for legacy reasons — handle as int with try/except, don't change the column type.

## Workflow
- Develop and test on Mac with `npm start`
- Commit and push from Mac
- Pull on Windows and verify before considering a change done
- Build installers via build-mac.sh (Mac) and build-windows.ps1 (Windows)

## Session workflow
- Propose changes in prose before editing. Wait for explicit go-ahead. Show diffs only after approval of the plan.

## Don't touch unless asked
- *.backup, *.old files (app.py.backup, database.py.backup, index_new.html.backup, pdf_generator.py.old, etc.)
- One-off migration scripts: implement_new_features.py, migrate_add_internal_notes.py, migrate_cache_setting.py
- Empty vfx_tracker.db at repo root
- utils/pdf_generator.py is legacy — utils/pdf_playwright.py is the active PDF exporter

## Known latent issues (don't fix unless asked)
- VFXCode in models.py has duplicate `shots` relationship (one backref, one back_populates) — works but warns
- Mac venv is on Python 3.9.6 with OTIO 0.18.1 — verified working end-to-end in the 2.8.1 build (EDL import, Manual TC Override, Manual Frame Range Override all functional). The earlier "3.13 required" note appears to have been stale or preemptive. If a future OTIO release actually requires 3.13, rebuild the venv then.

## What This Is

A desktop app for VFX shot tracking and turnover management. The architecture is a hybrid: an **Electron shell** that spawns a **Flask/Python HTTP server** on localhost:5001, then loads it in a BrowserWindow. All business logic lives in Python; the Electron layer handles OS integration (window management, file dialogs, app lifecycle, recent projects).

## Development Setup

```bash
# Python backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# Node/Electron
npm install
```

### Running in Development

Two processes must run simultaneously:

```bash
# Terminal 1 — Flask backend
./venv/bin/python app.py

# Terminal 2 — Electron shell
npm start
```

`npm start` alone will also spawn Flask automatically via `main.js`, but running Flask separately gives you readable server logs.

### Building

```bash
# macOS DMG
./build-mac.sh

# Windows (run in PowerShell)
.\build-windows.ps1
```

## Architecture

### Process Model

```
Electron (main.js)
  └── spawns Flask via Python venv → localhost:5001
  └── Project Picker window (picker.html)
  └── Main App window (loads Flask URL)
        └── IPC bridge for native dialogs, file ops
```

`main.js` manages two window types: a **project picker** (shown at startup and when switching projects) and the **main app window** (the Flask-served UI). The Flask server URL is injected into the BrowserWindow; Electron also intercepts certain navigation to handle file downloads and dialogs natively.

### Backend (`app.py`)

The Flask app is ~4,100 lines covering:
- Project CRUD and switching
- Shot/plate CRUD with versioning (`ShotHistory`)
- EDL and ALE file import (delegates parsing to `database.py`)
- Metadata mapping and camera metadata
- Reference image uploads
- Export: Pull EDL, VFX report PDF, CSV, ALE
- **Auto-migrations** (ALTER TABLE ADD COLUMN with existence checks)

Database is SQLite, accessed via SQLAlchemy. The DB path is resolved from the `VFX_DB_PATH` environment variable (set by Electron for packaged builds) or falls back to platform-specific defaults.

### Data Model (`models.py`)

```
Project
  └── VFXCode   (e.g. WILD_038_0010 — a shot group)
        └── Shot  (individual plate/element)
              ├── CameraMetadata
              └── ShotHistory   (version snapshots)
```

Key helpers: `timecode_to_frames()` and `frames_to_timecode()` in `models.py` — used throughout the app for handle calculations.

### EDL / File Parsing (`database.py`)

Uses **OpenTimelineIO** to parse EDL and ALE files. Also handles Avid marker extraction, M2 motion effect parsing, and VFX code/plate name parsing from clip names.

### Export (`export.py`, `utils/`)

- `export.py` — Pull EDL generation with handles, VFX report structure
- `utils/pdf_generator.py` — ReportLab-based PDF (legacy)
- `utils/pdf_playwright.py` — Playwright/Chromium-based PDF (active, bundled in packaged builds)
- `utils/pdf_generator_weasy.py` — WeasyPrint alternative (not primary)

### Frontend

Jinja2 templates in `templates/`, static assets in `static/`. No frontend build step — plain HTML/CSS/JS served directly by Flask. The main shot list view is `templates/index_new.html`.

## Key Conventions

- The Flask server always runs on port **5001**.
- Shot clip names follow the pattern parsed in `database.py` — VFX code prefix + plate suffix.
- ALE exports must include `Tracks=V` to prevent Avid audio track import errors.
- `cam_roll` metadata is used as the full Tape name in ALE exports.
- There are no automated tests; verification is manual.
