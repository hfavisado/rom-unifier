# ROM Unifier

ROM Unifier discovers incoming ROM collections and safely merges them into one canonical `destination/{platform}` archive. Its normal workflow has only three concepts: inventory, plan, and run.

Inputs are not modified while planning or selection occurs. A run stages and independently verifies every result before moving anything, then moves previous destinations and processed source folders into a timestamped, restorable backup.

## Install

Python 3.11+ is required. Runtime code uses only the Python standard library.

```bash
bash bootstrap.sh
# If macOS `python3` is older:
PYTHON_BIN=/opt/homebrew/bin/python3 bash bootstrap.sh
```

Copy and edit the configuration:

```bash
cp config.example.toml config.toml
```

Only two paths are required:

```toml
[paths]
source = "/absolute/path/to/incoming-roms"
destination = "/absolute/path/to/final-archive"
```

The program refuses to operate when these values are empty, relative, `/`, identical, or otherwise unsafe. Processing, staging, backups, tools, and DAT paths derive beside the destination unless overridden.

Configured executable paths are optional. An empty IGIR path means `<paths.tools>/igir`:

```toml
[tools.igir]
path = ""
url = ""
sha256 = ""
```

If a required executable is absent, ROM Unifier either uses its configured URL/checksum recipe or stops with the precise setting that must be supplied. It never silently installs Node/npm/npx.

## Simple workflow

### 1. Inventory (optional)

```bash
rom-unifier inventory
```

This saves a reusable inventory to the processing directory. Detection combines normalized folder aliases, supported file/member types, and sampled checksum/title evidence from DATs.

### 2. Plan

```bash
rom-unifier plan
```

The saved JSON plan records:

- every detected source folder and why it maps to a platform;
- every source filename, size, and modification-time fingerprint;
- the destination and its existing contents;
- each candidate file, whether its name is new or potentially duplicated, and why DAT validation will decide its final disposition;
- unresolved requirements such as a missing core, BIOS audit, media normalizer, or DAT.

Plans are reusable. `run` refuses a modified plan or changed source/destination snapshot and instructs the user to create a new plan. Operations with unresolved media/core requirements are left untouched while independent ready platforms continue.

### 3. Run

```bash
rom-unifier run
```

If no plan exists, `run` creates and saves one automatically. It then performs the complete supported workflow:

1. Locate or provision configured tools and DATs.
2. Create canonical parent/clone DATs where needed.
3. Copy/select into isolated run staging.
4. Deduplicate and canonicalize names/formats using DAT identity.
5. Independently verify staged output.
6. Build and verify relative M3U playlists for multi-disc systems.
7. Back up the previous destination and processed source folders.
8. Promote verified output to `destination/{platform}`.
9. Save complete reports, logs, completion metadata, and a restore manifest.

Long server runs should be launched in a named tmux session. Logs remain under the derived processing directory.

Run a specific saved plan with:

```bash
rom-unifier run --plan /path/to/plan.json
```

## Backups and restoration

Backups are timestamped and contain previous final folders, original source folders (including artwork/support files), and `restore.json`. They can be inspected or deleted as ordinary directories after the user is satisfied.

Restore a run with:

```bash
rom-unifier restore /path/to/backups/rom-unifier/RUN_ID/restore.json
```

Restoration moves the new final collection aside, restores the previous destination, and returns source folders to their original locations. It refuses to overwrite paths that have since reappeared.

## Automatic platform detection

Detection uses escalating evidence:

1. Folder aliases such as `ps`, `ps1`, `psx`, `playstation`, or `sony playstation`.
2. Direct file types and member types sampled inside ZIPs.
3. Platform-unique extensions.
4. SHA-1 or normalized known-game-title matches sampled against available DATs.

Low-confidence and conflicting results remain unresolved rather than being guessed. Aliases, formats, output names, media types, and safety gates are configured in `platforms.toml`.

Supported types can be listed with:

```bash
rom-unifier rom-types
```

## Multi-disc layout

Single-disc games remain directly beneath the platform directory:

```text
destination/psx/Game Name (USA).chd
```

Multi-disc games use a per-title folder:

```text
destination/psx/Game Name (USA)/
  Game Name (USA).m3u
  Game Name (USA) (Disc 1).chd
  Game Name (USA) (Disc 2).chd
```

The M3U contains only relative filenames. This makes each title portable and prevents disc-name collisions. The frontend should index the M3U rather than its individual CHDs.

## Safety boundaries

- Cartridge sources become one-ROM TorrentZip archives.
- Disc formats are never ZIP-wrapped.
- CHD verification uses complete content; quick archive checksums are not used for Redump matching.
- Existing finals and sources move only after every operation in the run has staged and verified successfully.
- Any logged error, malformed archive, missing playlist reference, changed plan, changed source snapshot, or unresolved platform gate stops the run before promotion.
- Nothing is permanently deleted automatically.
- Arcade processing remains blocked until an exact core and matching ROM-set DAT are configured.

## Current extension points

The registry already marks workflows requiring dedicated handlers. The next useful additions are:

1. N64 byte-order normalization as an automatic media handler.
2. ISO/CUE/GDI/CDI-to-CHD handlers with full round-trip verification.
3. 7z/RAR member sampling through configured standalone readers.
4. PICO-8 cartridge-PNG validation and Game & Watch core validation.
5. Arcade handlers bound to exact core/DAT versions.
6. SQLite indexing for faster incremental plans and content-addressed caching.
7. A `doctor` section within `plan` covering disk space, permissions, BIOS, tool versions, and temporary-directory conflicts.

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
