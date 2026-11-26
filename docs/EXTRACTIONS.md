# Container Ghosts — Deep Research Extractions (2026-11-25)

## Novelty verdict: PROCEED. No prior powered raster-hash-verified audit of production VLMs exists. Confidence MEDIUM-HIGH.
Flip condition: published production-endpoint results from vision-input-check or vendor system card.

## Claim-by-claim novelty
- (i) exact-repeat invariance metric: MODERATE (vision-input-check + Uncontrolled Variable adjacent)
- (ii) camera-vs-AI provenance polarity in container bytes: STRONG — nothing exists
- (iii) canary leakage: MODERATE (GSL-T073 heuristic unexecuted; MMPIBench adversarial 0.0%)
- (iv) PNG representation-only contrast: MODERATE
- (v) combined late-2026 production audit: STRONG

## Mandatory design changes from deep research
1. BEFORE finalizing protocol: `pip download vision-input-check==0.1.0 --no-deps`, inspect 32KB wheel, cite exactly in related work.
2. Preregister EQUIVALENCE BOUNDS, not just flip detection. Null is the prior-likely outcome on OpenAI/Anthropic (explicit docs deny metadata processing; MMPIBench EXIF 0.0%; ChatGPT web strips to IHDR/IDAT/IEND). Publishable null = tight upper bounds + strong positive controls.
3. Add signed-C2PA arm (valid vs stripped manifest). Google consumer app parses C2PA since May 2026; developer API undocumented — this is the highest-positive-probability arm.
4. Add ingestion-path contrast: inline base64 vs Files API upload.
5. NEW EXPERIMENT (bonus, strong): P0-2 prompt-cache key granularity side channel. Warm cache with image A, then submit image B with identical pixels but 1 altered non-rendering byte. Cache miss = pre-decode raw-byte hashing; cache hit = post-decode pixel hashing. Uses provider cache telemetry (cached_tokens etc). Clean binary measurement, no statistics needed beyond repetition.
6. Pixel dimensions: square multiples of lcm(28,32)=224. Use 448x448 primary (224 also OK, 896 if excluding legacy gpt-4o). Anthropic: transformations.oversized_image=error. OpenAI: detail=original/high.
7. RAW BYTES ONLY: never pass PIL.Image through google-genai SDK — client-side image.save() re-encodes and strips metadata. Send raw encoded bytes. Log SHA-256 of every transmitted file.
8. Per-call prefix nonce in primary trials to defeat implicit cache reuse; dedicated cache trials separate.
9. Temporal drift real: OpenAI silently patched image encoder Mar 13 + Sep 25 2026 without model ID change. Pin dated snapshots where possible, log UTC timestamps, daily baseline sentinels.

## Key vendor facts (Tier 1 verified)
- Anthropic INTERNAL CONTRADICTION: FAQ says "no metadata parsed" but vision-coordinates doc says "format conversion, and orientation correction proceed as usual" — server-side preprocessing provably touches files. Files API stores uploads as-is including C2PA.
- OpenAI: "model doesn't process original file names or metadata"; web UI strips EXIF/ICC, converts P3->sRGB, recompresses (Mochify Tier 3).
- Google: ZERO metadata documentation on any vision API surface, while adjacent products parse C2PA. Widest fragmentation. ICC_PROFILE chunk-0 bug proves header parsing at ingress.

## Closest methodological neighbor to cite
arXiv 2609.26174 "The Uncontrolled Variable" — paired exact McNemar on hosted APIs with hash-verified inputs, but manipulates RENDERED pixels/presence, never non-rendering container bytes. Our design inherits their statistics, differs in the manipulation layer.
- Text Over Image (MICCAI 2026, arXiv 2606.25375): 61.1% accuracy drop from provenance as PROMPT TEXT — that is our positive control arm, not prior art.

## Licensing architecture (from licensing dossier)
- Redistribute bytes ONLY for ~20 cleared images: verified Wikimedia Commons CC0 + 5 self-captured + 5 local FLUX.1[schnell] (Apache-2.0) generations with seeds.
- COCO/OpenImages: pointer+SHA-256 manifest only, no bytes. Screen out NC/ND licenses (use IDs 4/7/8 for COCO).
- NEVER use Pexels/Unsplash (AI/ML prohibitions). Never Midjourney (automation ban).
- PAID no-training API tiers only. Google: paid tier or Cloud Agent Platform (free tier trains on inputs outside EEA/UK/CH).
- Zenodo DOI deposit for cleared bytes + scripts + raw API logs.

## Remaining open (2 pending Gemini reports)
- Container-vs-pixel forensics details (prompt 3)
- Anything else in flight

## Codec guardrails (forensics report, NOW MANDATORY in artifact)
1. BYTE-LENGTH MATCHING across paired variants is essential: lossless PNG re-encode swings file size 129x (477B -> 61KB same pixels); stripping 1.7KB EXIF shrinks JPEG 13%. Control total byte length via neutral padding (JPEG COM or PNG tEXt pad chunk) or size-dependent pipeline behavior becomes an uncontrolled confound.
2. PNG = cross-decoder bit-identity guaranteed (exact integer bijection). JPEG = invariance only for FIXED decoder (IDCT/upsampling not mandated bit-exact; tf/Pillow/OpenCV diverge). Prefer PNG for primary arms.
3. EXCLUSION CHECKLIST (hold constant or omit in every variant): EXIF Orientation (0x0112), ICC/APP2/iCCP/Adobe APP14, embedded thumbnails, progressive vs baseline mixing (MozJPEG trellis rewrites coefficients), restart markers, DQT/DHT (DQT alters decoded pixels directly).
4. JPEG splicing must be byte-level segment insertion after SOI; NEVER high-level Image.save()/cv2.imwrite (re-quantizes).
5. PNG text chunks: valid CRC-32, never interrupt IDAT sequence, never before IHDR/after IEND. XMP-in-PNG = iTXt keyed XML:com.adobe.xmp.
6. PNG eXIf chunk is NOT ancillary-safe for our purposes (orientation honored inconsistently across browsers/libs) — exclude from clean arms.
7. Forensics literature explicitly says NOTHING about VLM ingestion — confirms the empirical gap is real.

## Provenance content for arms (from forensics lit)
- Camera-realistic EXIF: Make/Model/ExposureTime/ISO/Lens/GPS + MakerNotes structure matters (Kee et al. 576-value header signatures are camera-unique). Fake-camera arm should use real camera header structure copied from actual camera files, not invented fields.
- AI-realistic metadata: ComfyUI prompt/workflow chunks, A1111 parameters chunk, IPTC 2025.1 XMP AI fields (AISystemUsed), C2PA trainedAlgorithmicMedia assertion.
