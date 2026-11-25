# Container Ghosts artifact

Local, no-API implementation of the container-variant generator, pixel-hash verifier, probe-harness skeleton, and statistics scaffolding for the Container Ghosts research project.

## Reproduce

```sh
./run.sh
```

The command creates the venv if needed, installs pinned dependencies, regenerates all development stimuli and variants, writes `environment.json`, verifies deterministic regeneration, verifies invariance, runs the verifier mutation self-test, exercises the probe harness against a mock endpoint, and runs unit tests. It makes no hosted model API calls. The endpoint config also carries a structured inline-vs-Files-API ingestion-contrast stub for later live experiments; only inline exact-byte payloads are exercised in the dry run.

Generated files are under `artifacts/` and are intentionally gitignored. The important outputs are:

- `artifacts/build_manifest.json` — source/variant hashes, byte lengths, generation parameters, padding policy, canaries, probe labels.
- `artifacts/verification_manifest.json` — file/raster hashes, decoder-path results, chunk/segment inventory diffs, critical JPEG byte-identity checks, pairwise comparison counts, failures.
- `artifacts/dryrun/probe_dryrun.jsonl` — mock probe-call log with UTC timestamps, nonces, model snapshot placeholders, transmitted-byte hashes, option mappings, and response hashes.

## Stimuli and corpus drop-in

Default inputs are six deterministic procedural 448x448 RGB development stimuli: controlled text, color fields, a geometric scene, a document-like image, a face-free object arrangement, and a woven texture. They are not the final licensed corpus.

A later corpus directory can be supplied:

```sh
.venv/bin/python -m ghosts.build_variants --out artifacts --corpus /path/to/licensed-images
```

PNG/JPEG inputs are orientation-resolved once, converted to RGB, center-cropped square, resized to 448x448 with pinned LANCZOS resampling, and stripped by construction. This drop-in path is a development interface, not a substitute for the licensing/label audit required by the research specification.

## Variant arms

PNG, cross-decoder lossless:

- `P0`: baseline deflate-6, filter None, single IDAT.
- `P1`: combined representation contrast: deflate-9, Paeth filter, 4096-byte IDAT splits.
- `PC0`/`PC9`: deflate-level exploration; `P0` is the deflate-6 arm.
- `PF1`-`PF4`: Sub, Up, Average, Paeth filter strategies.
- `PS2K`: IDAT chunk splitting at 2048 bytes.
- `PT`: neutral `tEXt`, `zTXt`, and XMP `iTXt` ancillary metadata plus canary.
- `PTC`/`PTA`: camera-style versus AI-generator-style PNG ancillary provenance, including A1111/ComfyUI-style chunks for AI and IPTC 2025.1 XMP AI fields.

JPEG, fixed-decoder invariance only, all by byte-level segment splicing:

- `J0`: canonical stripped baseline JPEG, quality 95, 4:4:4, non-progressive, optimize off.
- `JC`/`JA`: camera-provenance versus AI-provenance APP1 EXIF + APP1 XMP polarity pair. EXIF UserComment carries the same per-image canary.
- `JXMP`: neutral XMP APP1 splice.
- `JCOM`: neutral COM splice.

The camera EXIF uses a real EXIF IFD hierarchy and plausible Make/Model/ExposureTime/ISO/FNumber/FocalLength/Lens fields. It does not copy proprietary MakerNotes; that realism limitation is explicit. Orientation is never written.

## Byte-length policy

Automated exact padding is implemented with a neutral PNG `tEXt` chunk keyed `Pad` and a JPEG COM filler segment.

- `P0/P1/PT/PTC/PTA` are length-controlled as one exact PNG group.
- `JC/JA` are length-controlled as the exact primary JPEG provenance pair.
- Verification requires zero byte-length delta in both groups.
- Unpadded `J0` and `P0` reference bytes are retained under `artifacts/reference/`.

Contrasts of stripped `J0` against metadata-bearing JPEGs retain insertion size as an explicit experimental factor, matching the specification. The `PC/PF/PS` representation exploration arms are also marked `byte_length_factor=true` rather than silently pretending that compression representation and length are separable.

## Verification semantics

The verifier decodes every variant with both Pillow and OpenCV. Pillow is the pinned canonical decoder. PNG must be bit-identical across decoders. JPEG metadata variants must be bit-identical within each fixed decoder and, more importantly, must preserve entropy-coded scan bytes, DQT, DHT, SOF, non-progressive structure, and restart parameters byte-for-byte. Cross-decoder JPEG equality is recorded but not assumed because IDCT/upsampling is implementation-dependent.

Programmatic exclusions include EXIF Orientation, embedded thumbnails, ICC/APP2/iCCP, Adobe APP14, progressive JPEG, restart markers, PNG rendering/color/animation chunks, and PNG `eXIf`. Any raster mismatch exits nonzero and writes a failing manifest.

`--mutation-test` changes one pixel in a regenerated PNG and requires both decoder comparisons to reject it. This is the negative control against a verifier that cannot fail.

## Probe harness

`ghosts.probe_harness` is structure only. It defines OpenAI/Anthropic/Google payload shapes in `configs/endpoints.json`, constructs inline-base64 payloads directly from raw file bytes, never PIL objects, schedules the six core variants in a seeded palindromic sequence with adjacent `JC/JA`, injects unique per-call nonces, supports exact-repeat mode, and validates the dry-run log. Live adapters are intentionally absent; no credentials are sufficient to run the artifact.

## Statistics

`ghosts.score` implements strict exact-response parsing, semantic remapping, flip helpers, and canary substring scan. `ghosts.stats` implements exact McNemar tests, discordance tables, exact-repeat noise comparison, Clopper-Pearson intervals, Newcombe/Wilson score intervals, paired bootstrap percentile intervals, and Holm adjustment. Unit tests include worked examples with known numeric answers.

## C2PA arm

Stubbed by default, with a functional narrow interface in `ghosts.c2pa_arm.py` and optional pins in `requirements-c2pa.txt`. Investigation result: `c2pa-python 0.39.0` / c2pa-rs SDK 0.92.0 can sign JPEG locally using a test Ed25519 certificate chain; a probe preserved scan/DQT/DHT/SOF bytes, but repeated signing is not byte-deterministic because the SDK generates a fresh manifest UUID. Activation requires controlling manifest UUIDs and all nondeterministic claim bytes, vendoring/generating a clearly labeled test certificate chain, and then proving scan/DQT/DHT/SOF identity after APP11 insertion. Signature trust validation remains out of scope.
