# Operational lessons encoded by the project

## Identification and 1G1R

- Filename similarity is insufficient for cartridge duplicates. Select using DAT identity/checksums.
- Libretro multi-format DATs can contain the same release in several formats. Filter to the platform's canonical extension before Retool, or one checksum/title can produce duplicate output.
- Retool supplies parent/clone selection. English is a preference rather than a hard exclusion, preserving games with no English release.
- Validate each prepared DAT with known regional clones before bulk processing.
- If IGIR writes more games than it scanned files, stop and inspect DAT duplication.

## Media formats

- Cartridge output is one ROM per TorrentZip-compatible ZIP.
- N64 sources may use `.n64`, `.v64`, or `.z64` byte order; normalize to `.z64` before checksumming.
- Atari 7800 `.a78` and Lynx `.lnx` can contain removable headers; match against canonical headerless records when the DAT requires it.
- PS1, Sega CD, PC Engine CD, Dreamcast, and PSP archival output prefers CHD. Never ZIP CHD/CSO/RVZ.
- Regenerate and validate M3U playlists after canonical multi-disc renaming.
- Store multi-disc CHDs with their relative M3U in a per-title folder; keep single-disc CHDs directly under the platform folder. Frontends should index the M3U rather than each constituent disc.
- PSP CHD conversion is accepted only after CHD-to-ISO SHA-256 round-trip verification.
- PBP/EBOOT is retained only when no verified CHD for the game exists.

## Reliability

- SMB can produce `EBADF` during large writes. Run large batches against server-local storage.
- Use the configured absolute standalone IGIR path in tmux; do not assume an interactive shell's `PATH` is available.
- Do not place an executable at `/tmp/igir`: IGIR may use that path as a temporary directory. Configure `TMPDIR` beneath the processing root.
- Do not use server `/tmp` for long work; it may be cleared automatically.
- A valid 7z can still fail in IGIR's bundled reader. Verify with native 7-Zip, extract into processing, exclude the problematic archive, and match the extracted ROM.
- IGIR can leave `.zip.<random>` partials after failed writes. Quarantine them and require exact staged file counts.
- A report showing `FOUND` does not prove the output was written. Run `igir test` independently and inspect logs for errors.
- Continue unrelated platforms after an isolated failure, but never promote the failed platform.

## Destructive boundaries

- Staging never moves sources.
- Existing final content must be enumerated before replacement, with saves/support files called out explicitly.
- Batch similar replacements into one manifest and one approval.
- Move replaced finals and processed sources into dated quarantine; permanent deletion is a separate retention decision.
- Promotion must fail when staging counts, verification results, or the approved manifest change.

## Disc and arcade constraints

- Redump CHD identification requires full internal track scanning. Never use IGIR quick archive checksums for CD CHDs.
- CDI and other non-Redump formats remain unmatched until converted and independently verified.
- Arcade processing requires the exact DAT matching the chosen RetroArch core and ROM-set version; never mix sets by filename.
- BIOS files are audited by checksum and required filename, not ordinary 1G1R selection.
