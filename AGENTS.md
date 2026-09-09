# Repository guidance

- Keep input trees immutable during discovery, selection, and verification.
- Add platforms and formats to `platforms.toml`; avoid embedding bundle-specific paths in code.
- Generic cartridge logic must never process disc or arcade media.
- Require independent verification before promotion.
- Normal usage should expose only `inventory`, `plan`, `run`, and `restore`; selection, staging, verification, playlist generation, and promotion are internal run phases.
- A saved plan must fingerprint inputs, describe concrete actions, and be reusable until its source snapshot changes.
- A run must quarantine replacements and processed sources recoverably and generate a restore manifest.
- Never add Node/npm/npx as a server requirement. Prefer configured standalone executables under `tools/`.
- Long server jobs must have a generated tmux command and persistent log path.
- Treat warnings, partial output files, malformed archives, and output counts exceeding scanned inputs as failures requiring review.
- Preserve saves, BIOS, artwork, metadata, manuals, playlists, and support files until explicitly classified.
- Add unit tests for every new parser, transformation, safety check, and failure recovery.
