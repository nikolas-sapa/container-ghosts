# Container Ghosts — Do VLMs read pixels or files?

Spec date: 2026-11-25  
Status: research specification, pre-implementation  
Solo-project budget target: 4-6 weeks elapsed, <700 LOC core artifact, hard API-cost cap USD 50 unless explicitly revised before data collection

## 1. One-paragraph pitch

Hosted vision-language models are usually treated as if they see only a decoded raster, but production ingestion pipelines receive a file: container type, compression representation, ancillary chunks, EXIF/XMP fields, filenames, upload mechanism, and server-side preprocessing. Container Ghosts tests whether that difference matters behaviorally. For image pairs whose decoded rasters are byte-identical under a pinned reference decoder but whose containers differ only in non-rendering metadata or lossless encoding representation, a pixel-only pipeline should show no answer divergence beyond its exact-repeat noise floor. Any excess paired flip rate, semantic provenance shift, or exact metadata-canary leakage is evidence of a container/provenance side channel in the evaluated pipeline. This is deliberately a black-box pipeline claim, not a claim about model weights or about what a vision encoder could represent in principle. A powered null is useful because it audits deployed ingestion rather than speculating from documentation.

**Non-goals.** The project does not attempt adversarial jailbreaks, does not test visible in-image text injection, does not identify which internal server component caused an effect, does not audit every upload surface (mobile app, web UI, URL fetch, Files API), does not measure C2PA signature validation, and does not claim that a null rules out small or conditional effects.

## 2. Exact falsifiable research claim and preregistered primary metric

### Claim

For each endpoint \(e\), within the preregistered invariant image set: if the endpoint's production image-ingestion pipeline is pixel-only with respect to non-rendering container bytes, then container-different but raster-identical inputs will not exhibit answer-flip rates above the endpoint's exact-repeat baseline. The pipeline-specific falsifiable alternative is that at least one preregistered container contrast produces positive excess paired flips or exact metadata-canary leakage.

A positive result supports a pipeline side channel. It does **not** prove that model weights directly tokenize metadata: byte-size-dependent preprocessing, format-dependent transcoding, parser side effects, cache behavior, or a metadata extraction layer are all within the black-box pipeline.

### Primary contrast and probe

The primary confirmatory contrast is `prov = (JC, JA)`:

- `JC`: canonical JPEG plus controlled camera-provenance EXIF/XMP/UserComment metadata.
- `JA`: byte-length-matched canonical JPEG plus controlled AI-provenance EXIF/XMP/UserComment metadata.
- Both are generated from the same canonical JPEG by segment-level container editing, leaving the JPEG scan data and decoding-critical segments unchanged.
- The primary probe is the forced binary judgment: “camera photograph or AI-generated?”.

The primary metric is computed separately for each endpoint. There is no pooled cross-endpoint confirmatory claim.

### Exact primary metric definition

Let:

- \(i\in\{1,\ldots,N\}\) index base images, with planned \(N=50\).
- \(e\) index endpoint.
- \(v\) index container variant.
- \(r\in\{1,2\}\) index the two repetitions in the mirrored sequence.
- \(q\) index probe; \(q=P\) is the provenance probe.
- \(Y_{i,e,v,r,q}\) be the parsed categorical answer after mapping randomized option letters back to semantic labels. Invalid/unparseable outputs are not valid categories.

For a container contrast \(c=(a,b)\), define the **cross-container any-flip indicator**:

\[
X_{i,e,c,q}=\mathbf 1\left(
  [Y_{i,e,a,1,q}\ne Y_{i,e,b,1,q}]
  \;\lor\;
  [Y_{i,e,a,2,q}\ne Y_{i,e,b,2,q}]
\right).
\]

Define the **exact-repeat any-flip indicator** over the two anchor variants:

\[
R_{i,e,c,q}=\mathbf 1\left(
  [Y_{i,e,a,1,q}\ne Y_{i,e,a,2,q}]
  \;\lor\;
  [Y_{i,e,b,1,q}\ne Y_{i,e,b,2,q}]
\right).
\]

Both sides have two opportunities to flip: \(X\) inspects the first-occurrence and second-occurrence cross-container pairs; \(R\) inspects exact-byte repetition within variant \(a\) and exact-byte repetition within variant \(b\). This symmetry prevents “number of opportunities” from being the explanation for an excess.

Define the paired discordance \(D_{i,e,c,q}=X_{i,e,c,q}-R_{i,e,c,q}\in\{-1,0,1\}\). The **excess paired flip rate** is

\[
\Delta_{e,c,q}
 =\frac{1}{n_{e,c,q}}\sum_{i=1}^{N}D_{i,e,c,q}
 =\frac{n_{10}-n_{01}}{n_{e,c,q}},
\]

where the sum is over complete-valid image cells, \(n_{10}\) counts cells with cross-container flips but no exact-repeat flip, and \(n_{01}\) counts cells with exact-repeat flips but no cross-container flip. Positive \(\Delta\) means container-different raster-identical inputs diverge more often than exact byte repetitions.

The preregistered primary metric is

\[
\Delta^{\mathrm{primary}}_e=\Delta_{e,\mathrm{prov},P}.
\]

Primary test: exact one-sided McNemar test on \((n_{10},n_{01})\), direction \(n_{10}>n_{01}\), \(\alpha=0.05\), endpoint by endpoint. Report the paired point estimate, exact p-value, denominators, and a 95% bootstrap percentile CI over base images. If a global “at least one of three hosted endpoints” claim is made, apply Holm correction across the three endpoint-specific primary p-values; otherwise every positive/null claim is strictly endpoint-specific.

### Key secondary measurements

1. **All-contrast flip family:** the same \(\Delta_{e,c,q}\) for all six contrasts and three probes.
2. **Semantic provenance shift:** for repetitions \(r\), decode answers to `AI` or `PHOTO` and compute

\[
S_e=\frac{\sum_{i,r}\left(\mathbf 1[Y_{i,e,JA,r,P}=\mathrm{AI}]-\mathbf 1[Y_{i,e,JC,r,P}=\mathrm{AI}]\right)}
        {\sum_{i,r}w_{i,e,r}},
\]

where \(w_{i,e,r}=1\) only when both provenance answers are valid. Positive \(S_e\) means AI-provenance metadata makes AI judgments more frequent than camera-provenance metadata on the same raster. Use paired bootstrap over images.

3. **Direct canary leakage:** scan raw output text for the exact random canary embedded only in metadata. Any exact occurrence is strong evidence of metadata-to-output propagation. Report count, opportunities, per-variant breakdown, and Clopper-Pearson interval. Absence is not proof of no ingestion because the forced format suppresses free text.
4. **Invalid-output rate:** proportion of responses failing the exact output grammar, by endpoint/variant. It is a quality-control measurement, not a flip.
5. **Correctness:** exact correctness against manifest labels is secondary. The claim concerns stability, not accuracy.

## 3. Prior-art table with verification status

Verification was performed on 2026-11-25 using the linked sources. “Confirmed” means the bibliographic object and quoted scope were verified; it does not mean the result is correct. “Corrected” means the kill-check wording was materially incomplete or misleading.

| # | Source / claim | Bearing on this project | Verification status | URL |
|---|---|---|---|---|
| 1 | **EXIF as Language: Learning Cross-Modal Associations Between Images and Camera Metadata** (CVPR 2023). Learns joint embeddings between image patches and EXIF metadata; camera properties are inferred from pixels at test time. | Confirms acquisition/provenance information can leave learnable pixel-level traces. It does not show that a deployed VLM reads embedded EXIF bytes. | **Confirmed** | https://arxiv.org/abs/2301.04647 |
| 2 | **Processing and acquisition traces in visual encoders: What does CLIP know about your camera?** (ICCV 2025 highlight). Shows subtle acquisition/processing parameters are recoverable from visual representations and can affect semantics. | Strong motivation for controlling pixel identity. Concerns pixel-level traces, not container metadata ingestion. | **Confirmed** | https://arxiv.org/abs/2508.10637 |
| 3 | **Invisible Shortcuts: Why Vision Encoders Know Your Camera** (ECCV 2026). Studies shortcut learning from invisible metadata traces embedded at the pixel level. | Further motivation, but again “metadata traces” means pixel manifestations of acquisition/processing, not file-container text being passed to the model. | **Confirmed** | https://arxiv.org/abs/2608.05424 |
| 4 | **MMPIBench / An Experimental Evaluation of Multimodal Prompt Injection Attacks on Agentic AI Frameworks** includes EXIF metadata as one of six adversarial carriers. | Confirms the arXiv ID and carrier claim, but the original kill-check omitted important nuance: this is adversarial agentic prompt injection, not non-adversarial ingestion auditing. The paper reports metadata and QR carriers had 0% attempted/partial/completed attack progression in its main table, with the payload never reaching perception in about 88% of runs; a few metadata runs did surface payload text and one reached a tool call. | **Confirmed, with scope correction** | https://arxiv.org/abs/2609.09404 |
| 5 | Practitioner/security folklore: EXIF `ImageDescription`/`UserComment` can carry indirect prompt-injection payloads. | Real practitioner concern, but mostly conditional on the surrounding pipeline extracting metadata into the prompt. No widely reproduced EXIF-only hijack of a named production model was found in the checked sources. | **Partially confirmed; exploit claim corrected** | https://getnotrace.app/blog/exif-metadata-prompt-injection/ ; https://genaisecuritylab.com/cheatsheet/multimodal-injection/ |
| 6 | PNG Third Edition: ancillary information may be ignored by decoders; textual chunks include `tEXt`, `zTXt`, `iTXt`; PNG is lossless. | Validates the rationale for byte-different but raster-identical PNG encodings and ancillary-text insertion. Also validates excluding color/transparency/orientation-relevant chunks from the invariant set. | **Confirmed** | https://www.w3.org/TR/png-3/ |
| 7 | **Text Over Image / Beyond Visual Forensics** audits fixed medical images under swapped structured provenance metadata and reports large decision shifts. | Close conceptual prior art, but the metadata is placed in the accompanying textual record/prompt, not embedded inside the image container. This sharpens rather than closes the container-side-channel gap. | **Confirmed as adjacent, not overlapping** | https://arxiv.org/abs/2606.25375 |
| 8 | `vision-input-check` v0.1.0, released 2026-10-05. Regression harness for vision LLM APIs with pixel-verified `png-reencode` and `exif-strip` identical variants, exact assertions, no LLM judge. | The kill-check’s absolute novelty gap is too strong. This is a real adjacent artifact. However, its bundled demo is synthetic replay, not a published production-endpoint audit; default N=3 is explicitly descriptive; it does not insert provenance/camera/AI metadata, use canaries, run powered paired-flip statistics, or test PNG/JPEG metadata insertion families. | **Confirmed; claimed gap corrected/narrowed** | https://github.com/Gjusev/vision-input-check ; https://pypi.org/project/vision-input-check/ |
| 9 | OpenAI vision documentation says the `detail` parameter controls preprocessing, models may resize images, and the model does not process original file names or metadata. | Official vendor claim and preprocessing evidence, not an independent audit. It raises the cost of a positive result and helps define what a null is consistent with. | **Confirmed vendor statement** | https://developers.openai.com/api/docs/guides/images-vision ; https://help.openai.com/en/articles/8400551-chatgpt-image-inputs-faq |
| 10 | Anthropic Claude vision documentation says Claude does not parse or receive image metadata and documents downscaling/token behavior. | Official vendor claim, not independent proof. Primary API surface remains worth auditing because the claim is about what Claude receives, not every surrounding preprocessing behavior. | **Confirmed vendor statement** | https://platform.claude.com/docs/en/build-with-claude/vision |
| 11 | Gemini/Firebase documentation confirms PNG/JPEG/WebP support, tiling/resizing/tokenization behavior, and large-image scaling/padding to 3072×3072. No comparably explicit official metadata-ingestion statement was found in targeted searches. | Resize behavior documented; embedded metadata handling remains genuinely uncertain and is a deep-research question. | **Confirmed preprocessing; metadata status unverified** | https://firebase.google.com/docs/ai-logic/input-file-requirements ; https://aistudio.google.com/docs/media-resolution |
| 12 | Kee, Johnson, and Farid, **Digital Image Authentication From JPEG Headers** (2011): quantization tables, Huffman codes, thumbnails, and EXIF form discriminative camera/software signatures. | Establishes that container/header structure is a meaningful provenance layer in forensics. It does not imply VLMs receive that layer. | **Confirmed** | https://doi.org/10.1109/TIFS.2011.2128309 |
| 13 | Lukáš, Fridrich, and Goljan, **Digital Camera Identification From Sensor Pattern Noise** (2006). | Classic pixel-level provenance forensic baseline; reinforces the pixel/container distinction. | **Confirmed** | https://doi.org/10.1109/TIFS.2006.873602 |
| 14 | C2PA specifications define Content Credentials/provenance manifests. | Relevant future extension and provenance context, but signed C2PA validation is outside this minimal first study. | **Confirmed** | https://spec.c2pa.org/specifications/specifications/2.5/index.html |
| 15 | Gap statement: no controlled, non-adversarial, pixel-hash-verified invariance audit of production VLM ingestion exists. | **Too absolute after verification.** Corrected version: targeted searches found no peer-reviewed, powered, non-adversarial audit that (a) verifies raster identity, (b) embeds controlled camera/AI provenance and canaries in image containers without touching rendering, (c) compares against exact-byte repetition using paired statistics, and (d) reports production endpoint results. Absence remains provisional pending deep external research. | **Corrected/provisional** | See rows 7-8 and `GEMINI_DEEP_RESEARCH.md` |

## 4. Artifact architecture and LOC budget

Python is the implementation language because Pillow/piexif-style image handling and all endpoint SDKs are available there. The core pipeline is file-based JSONL plus raw response archives. No notebook is required. No LLM judge is permitted anywhere in scoring or analysis.

Hard rule: JPEG metadata variants must be made by **binary segment splicing**, not by decoding and re-saving the JPEG. PNG metadata variants must be made by **binary chunk insertion**, not pixel recompression. Generation scripts are part of the artifact because input hashes must be regenerable.

| Module | Responsibility | LOC budget |
|---|---|---:|
| `ghosts/select_manifest.py` | read source candidates, enforce selection/license manifest, deterministic resize/normalize, write base manifest | 70 |
| `ghosts/build_variants.py` | canonical JPEG creation, PNG lossless representations, PNG chunk insertion, JPEG APP/COM/EXIF/XMP segment splicing, padding/size matching | 145 |
| `ghosts/verify_invariance.py` | file/raster hashes, PNG chunk audit, JPEG segment/scan-data audit, forbidden-chunk checks, manifest validation | 65 |
| `ghosts/endpoints.py` | thin hosted/open endpoint adapters, inline-base64 submission, timeout/retry bookkeeping, exact request parameter capture | 85 |
| `ghosts/run_matrix.py` | palindromic ABBA schedule, checkpoint/resume, rate limiting, sentinel batches, cost ledger | 105 |
| `ghosts/score.py` | strict parser, semantic label remapping, exact flips, canary substring scan, control scoring | 55 |
| `ghosts/stats.py` | exact McNemar, paired/bootstrap CIs, Holm correction, power/denominator tables | 80 |
| `ghosts/report.py` | immutable run report, hash tables, endpoint/date/config tables, machine-readable summary | 35 |
| `tests/test_invariance.py` | CRC/segment splice round trips, hash fixtures, parser tests, negative-control logic | 45 |
| **Total** |  | **685 (<700)** |

Implementation constraints:

- Count physical lines including comments; if the implementation exceeds 699 lines, remove scope rather than hiding code in notebooks.
- Store dependency versions and hashes in `environment.json`.
- Use deterministic seeds for selection, option mappings, variant construction, and call ordering.
- Write raw request/response JSONL before scoring. Analysis must be rerun from raw logs, not memory.
- Publish SHA-256 for every source-derived input and generated variant; for redistributable inputs also publish bytes. For rights-restricted third-party images publish source IDs/URLs, licenses, hashes, and generation scripts rather than image bytes.

## 5. Dataset construction protocol

### Target composition

Select exactly 50 base images before any model call:

| Source stratum | Count | Use |
|---|---:|---|
| COCO val2017, license-screened per image | 15 | natural object/count/caption scenes |
| Open Images V7, records listed as CC BY 2.0 | 15 | natural object/count/caption scenes |
| Verified CC0 / public-domain images (Wikimedia Commons CC0 or equivalent) | 10 | diverse uncomplicated scenes; custom-license stock images (Pexels/Unsplash) count only if the license audit explicitly clears them, since those licenses are not CC0 |
| Project-generated | 10 | 5 self-captured photographs + 5 generated synthetic images with recorded generator/prompt/date |
| **Total** | **50** |  |

COCO annotations are CC BY 4.0 but the COCO Consortium does not own image copyrights; image use is governed by Flickr/per-image terms. Open Images says listed licenses must be independently verified. Therefore the default publication artifact is IDs/URLs/hashes/scripts for third-party images, not redistribution of their bytes. CC0 and project-generated bytes may be redistributed. A license audit is a required pre-publication gate, not an afterthought.

### Selection criteria

Each image must satisfy all of the following after canonical normalization:

1. RGB or safely flattenable to RGB; no alpha-dependent interpretation. Prefer simply excluding alpha images.
2. Long edge resized to exactly 768 px using one pinned resampler; short edge determined by aspect ratio. No upscaling beyond 1.25×.
3. No visible watermark, embedded instructions, CAPTCHA-like content, medical imagery, sexual/violent content, or identifiable faces.
4. For the object probe: a target object/category is unambiguous at the final size. Count probes use exactly 1-5 salient instances; color probes use an object with one clearly dominant color. Borderline cases are excluded.
5. For caption forced choice: one manifest caption is clearly better than a minimally wrong distractor; the correct side is randomized per image and fixed across all variants.
6. No near-duplicate of another selected image by perceptual-hash review.
7. Source orientation is resolved during initial normalization, then orientation metadata is removed. Non-sRGB ICC profiles are either converted once during canonicalization or the image is excluded; the invariant variants themselves carry no ICC/color-profile differences.
8. The researcher can verify the label in two independent passes separated by at least 24 hours. Any disagreement excludes the image.

The fact that canonicalization changes the original source pixels is not a problem. All scientific comparisons are downstream of one fixed canonical raster \(R_i\). That raster is the unit whose identity is protected.

### Canonical raster and six delivery variants

For every base image:

1. Normalize source to RGB, resize to 768 px long edge, strip metadata.
2. Encode canonical JPEG `J0` once using pinned parameters: quality 95, 4:4:4 subsampling, non-progressive, no ICC, no EXIF, optimize flag fixed. Decode `J0` using the pinned decoder and define the resulting bytes as canonical raster \(R_i\).
3. Construct all scientific variants so their decoded raster is \(R_i\):

| Variant | Construction | Purpose |
|---|---|---|
| `J0` | canonical stripped JPEG | reference JPEG/container baseline |
| `P0` | PNG encoding of \(R_i\), default pinned compression/filter/chunking | reference PNG encoding |
| `P1` | PNG encoding of \(R_i\) with deliberately different deflate level/filter strategy/chunk split | lossless representation-only contrast |
| `PT` | `P0` plus `tEXt`, `zTXt`, and `iTXt` ancillary chunks containing neutral filler and the base-image canary | PNG ancillary-metadata ingestion probe |
| `JC` | `J0` with camera-provenance EXIF/XMP/UserComment inserted by segment splicing; scan data untouched | camera-provenance container probe |
| `JA` | `J0` with AI-provenance EXIF/XMP/UserComment inserted by segment splicing; scan data untouched; byte length matched to `JC` within ±16 bytes using inert padding | AI-provenance container probe |

`JC` and `JA` use parallel metadata schemas and plausible but fictional device/software values. They share the same per-image random canary (`GHOSTCANARY_<12 random alphanumerics>`). They differ only in the controlled provenance semantics plus unavoidable length/padding details. `PT` uses nonsemantic filler so ancillary-parser sensitivity can be separated from provenance semantics.

### Mandatory invariance verification

A variant enters the invariant set only if all checks pass:

- SHA-256(file) differs from every other variant for the same base image, except intentional exact repeated transmissions of the same variant.
- SHA-256(canonical decoded RGB raster) is identical for `J0`, `P0`, `P1`, `PT`, `JC`, and `JA` under the pinned decoder.
- JPEG entropy-coded scan data, quantization tables, Huffman tables, SOF dimensions/precision/components, and restart parameters are byte-identical across `J0`, `JC`, and `JA`.
- No invariant JPEG contains EXIF Orientation, embedded thumbnails, ICC profile, Adobe color-transform segment, or any metadata that changes color/orientation interpretation.
- No invariant PNG contains `gAMA`, `cHRM`, `iCCP`, `sRGB`, `cICP`, `sBIT`, `tRNS`, `bKGD`, `pHYs`, animation chunks, or other rendering-relevant chunks introduced as a difference. Text chunks are the only intended ancillary difference in `PT`.
- PNG `IHDR`, color type, bit depth, interlace method, palette if any, and decoded scanline bytes are invariant.
- A second decoder spot-check is run on at least 20% of images. Disagreement does not automatically exclude a JPEG because JPEG IDCT implementations can differ; instead the scan-data identity requirement carries the invariance argument, and the decoder dependence is reported. PNG disagreements do exclude the image because PNG lossless decoding should be exact.

## 6. Experimental design matrix: arms, controls, sample sizes, power reasoning

### Probe battery

To preserve the approximately 1,800-call core budget, each call asks three independent forced-choice questions and requires a compact exact output. Example template:

```text
Answer the three independent questions about the image. Return exactly three letters separated by commas and nothing else.
1. <count-or-color forced choice with options A/B>
2. Which caption is more accurate? A: <caption one> B: <caption two>
3. Does this image appear to be a camera photograph or AI-generated? A: <option> B: <option>
```

Valid output grammar is approximately `^[AB],[AB],[AB]$` after whitespace normalization. Option-to-semantic mappings are randomized once per base image and then fixed for all variants/repetitions. Approximately half of q1 items are count probes and half color probes. Max output tokens is 16; temperature is 0 where supported or the minimum deterministic setting exposed. Model-specific reasoning effort, detail/media-resolution settings, API version, and exact model string are frozen and logged.

Composite probing creates possible cross-answer interference, but that interference is constant across container variants. The week-1 pilot must demonstrate high parse validity; if it does not, the fallback is separate single-probe calls with a revised cost budget, not silent continuation.

### Core invariant matrix

Each `(base image, endpoint)` uses a 12-call palindromic sequence:

```text
pi(1), pi(2), ..., pi(6), pi(6), ..., pi(2), pi(1)
```

where `pi` is a seeded random permutation of `{J0,P0,P1,PT,JC,JA}`, constrained so `JC` and `JA` are adjacent in the first half with their internal order randomized. This embeds an A/B/B/A structure for the primary provenance contrast and mirror-controls temporal drift for all variants.

Core calls:

\[
50\text{ images}\times 6\text{ variants}\times 2\text{ repetitions}\times 3\text{ hosted endpoints}
 = 1800\text{ calls}.
\]

That is 600 core calls per hosted endpoint. The optional open fallback repeats the same 600-call core locally or on cheap hosted open-weight infrastructure.

### Pre-specified contrast family

| Contrast | Pair | Interpretation |
|---|---|---|
| `fmt` | `J0` vs `P0` | container-format/representation sensitivity without intentional metadata |
| `pngrepr` | `P0` vs `P1` | PNG lossless encoding representation only |
| `pngtext` | `P0` vs `PT` | PNG ancillary text insertion |
| `jpegcam` | `J0` vs `JC` | JPEG camera-metadata insertion |
| `jpegai` | `J0` vs `JA` | JPEG AI-metadata insertion |
| `prov` | `JC` vs `JA` | camera-vs-AI provenance polarity; primary when q=P |

### Controls

| Control | Design | Calls across 3 hosted endpoints | Interpretation |
|---|---|---:|---|
| Exact-byte negative control | Already embedded: every variant appears twice | 0 extra | estimates temporal/stochastic baseline \(R\) |
| Explicit textual provenance positive control | same `J0`, neutral prompt vs prompt containing explicit camera/AI provenance sentence; all 50 images | 300 | verifies the endpoint can semantically respond to explicit provenance text |
| Pixel perturbation ladder | 20-image subset: original, one-pixel change, obvious object/count/color change | 180 | verifies visual sensitivity; one-pixel result exploratory, object-level result required for object-probe interpretation |
| Orientation EXIF control | 20-image subset: `J0` vs same scan data with EXIF Orientation set to a non-1 value | 120 | separate test of rendering-relevant metadata; excluded from invariant claims |
| **Control total** |  | **600** | **200 per endpoint** |

Maximum hosted total: 1,800 core + 600 controls = **2,400 calls** (800 per endpoint). If the open fallback is run fully, add 800 local/non-billed calls. Outputs are normally under 10 tokens; image input cost is minimized by the 768-px long edge. Abort or redesign before collection if projected cost exceeds USD 50.

### Endpoints

Primary surfaces are inline/base64 image inputs to:

1. a current Google Gemini Flash-class vision endpoint,
2. a current OpenAI GPT vision endpoint,
3. a current Anthropic Claude vision endpoint.

Exact model strings are chosen at execution time, frozen before the first core call, and published with dates, API versions, parameters, and pricing estimates. Do not silently substitute a model mid-run. If an endpoint is unavailable or terms prohibit the experiment, use Qwen2.5-VL-7B-Instruct or SmolVLM as an open fallback and label it as a controlled open pipeline rather than a production hosted audit. Useful references: Qwen2.5-VL collection https://huggingface.co/collections/Qwen/qwen25-vl and SmolVLM https://huggingface.co/HuggingFaceTB/SmolVLM-Instruct .

Inline/base64 is primary because it is the most comparable cross-provider transmission of exact bytes and avoids filename confounds. URL, Files API, web UI, and mobile ingestion are explicitly out of scope for the first paper.

### Power reasoning

The primary cell has at most 50 independent base images per endpoint. Approximate exact one-sided McNemar power, treating cross-container and exact-repeat any-flip outcomes as independent Bernoulli events for planning only, is:

| Exact-repeat any-flip rate | Cross-container any-flip rate | Approx. power at N=50 |
|---:|---:|---:|
| 5% | 20% | 0.64 |
| 5% | 25% | 0.84 |
| 5% | 30% | 0.95 |
| 10% | 30% | about 0.75 |

These are illustrative, not guarantees: paired correlation, invalid outputs, temporal drift, and ordering can change power. The correct interpretation is that the main study is powered for **large** effects, roughly 20-30 percentage points of excess any-flip behavior, not subtle 2-5 point effects. The second repetition improves measurement stability but is conservatively not counted as doubling the effective sample because the outcomes are paired within images.

A null is publishable only when both are true:

1. positive controls pass their numeric sensitivity gates, and
2. the report states the empirical detection limit, for example “no detectable camera-vs-AI metadata sensitivity at approximately the 20-25 percentage-point scale under this instrument,” using the observed CI rather than a generic claim of “no side channel.”

## 7. Scoring and statistics

### Exact-match scoring

- Strip whitespace only; then require the exact three-letter comma grammar.
- Map letters back to semantic labels using the per-image manifest.
- No fuzzy matching, no LLM judge, no manual relabeling after seeing condition assignments.
- For primary analyses, a cell is complete only when every response needed for \(X\) and \(R\) is valid. Report the number excluded.
- Sensitivity analysis treats `INVALID` as a third categorical outcome. If conclusions change materially, report both rather than choosing the favorable one.

### Tests and intervals

1. **Primary:** exact one-sided McNemar test of \(n_{10}\) versus \(n_{01}\), endpoint-specific. Report 95% paired bootstrap percentile CI over images for \(\Delta\).
2. **Secondary contrast-probe cells:** compute the same McNemar statistics for all 17 non-primary `(contrast, probe)` cells per endpoint. Holm-correct within endpoint across those 17 tests.
3. **Omnibus secondary:** pooled excess flips across probes/contrasts using cluster bootstrap over base images. This is descriptive unless a preregistered hierarchical gate is added before data collection.
4. **Semantic provenance shift:** paired bootstrap CI for \(S_e\); exact multinomial/binomial sensitivity test if computable within the LOC budget.
5. **Canary:** exact substring scan before answer parsing. One exact canary emission is reportable evidence. If zero, report upper confidence bound using the total number of metadata-bearing calls.
6. **Temporal sensitivity:** report first-order and reverse-order cross-flips separately and exact-repeat instability in the first versus second half of each batch. A qualitative order effect does not invalidate the primary design but must be disclosed.
7. **Effect size emphasis:** do not use p-values alone. Publish all flip counts in a 2×2 discordance table for every cell.

### Multiple comparisons

- Primary family for a global hosted-platform claim: three endpoint-specific primary tests, Holm across endpoints.
- Secondary exploratory family: 17 non-primary contrast×probe cells per endpoint, Holm within endpoint.
- Positive controls are gates, not hypothesis tests in the same family.
- Orientation, one-pixel perturbation, format sensitivity, open-model fallback, file-size analyses, and temporal-drift analyses are exploratory and labeled as such.

## 8. Week-1 kill test with numeric thresholds and explicit kill criteria

Week 1 is not a miniature paper. It is an instrument-validation gate.

### Pilot build and run

- Build 10 pilot base images and all 6 variants each.
- Verify all offline invariance checks.
- Use 8 of those images for the API pilot: \(8\times6\times2\times3=288\) core calls.
- Add explicit textual provenance controls on the same 8 images: \(8\times2\times3=48\) calls.
- Add object-level perturbation ladder on 4 images: \(4\times3\times3=36\) calls.
- Total pilot ceiling: 372 hosted calls.

### Numeric go thresholds

| Gate | Threshold |
|---|---|
| Raster invariance | 100% of pilot invariant files pass canonical raster hash; 0 unexplained failures |
| File differentiation | 100% of intended variant pairs have distinct SHA-256 file hashes |
| JPEG scan invariance | 100% of `J0/JC/JA` triples have byte-identical scan data and decoding-critical segment parameters |
| Forbidden rendering metadata | 0 orientation/ICC/thumbnail/color-transform differences in the invariant set |
| Parse validity | target 95% valid three-answer responses across pilot core calls; floor 90% after at most one prompt revision. A 90-95% outcome proceeds only with a predeclared missing-data sensitivity plan; below 90% is a kill criterion |
| Exact-repeat noise | pooled exact-repeat any-flip rate no more than 20% per endpoint. An endpoint exceeding this fails its own gate (drop it or redesign with more power); if two or more hosted endpoints exceed it, the whole design fails (kill criterion 4). If 10-20%, record reduced sensitivity rather than treating as clean |
| Explicit provenance sensitivity | raw AI-vs-photo answer shift at least 50% in pilot (4/8) after explicit prompt-text manipulation, after one prompt revision |
| Object-edit sensitivity | task-relevant answer flip in at least 50% of pilot object-edit pairs (2/4), after one edit/prompt revision |
| Endpoint operability | at least 2 of 3 hosted endpoints complete at least 95% of pilot calls without unrecoverable errors |
| Cost | projected full hosted cost no more than USD 50 after actual pilot token accounting |

### Explicit kill / redesign criteria

Kill or fundamentally redesign the project before full collection if any of the following holds:

1. JPEG segment-splice invariance cannot be achieved after at most 2 engineering days. Narrowing to PNG-only is allowed only if the preregistration and title/claim are revised before data collection.
2. Parse validity remains below 90% after one prompt revision. A 90-95% result requires a predeclared missing-data sensitivity plan; below 90% makes exact scoring unreliable.
3. Explicit textual provenance sensitivity remains below 50% in pilot after revision, or the full-run positive-control gate later fails. Without this, a provenance null is instrumentally uninterpretable.
4. Exact-repeat noise exceeds 20% at minimum temperature on at least two endpoints. The N=50 design cannot support useful inference at that noise level without a larger redesign.
5. Projected hosted cost remains above USD 50 even after reducing image detail/resolution within the preregistered protocol. Descope endpoints or collect fewer images only by rewriting the power analysis before proceeding.
6. Deep prior-art research finds a substantially overlapping published controlled audit using raster-hash verification, embedded camera/AI provenance metadata, exact-repeat baselines, and production endpoints. In that case pivot to replication/extension rather than claiming novelty.
7. Fewer than two production hosted endpoints are accessible and the open fallback would become the sole meaningful result; then the project no longer matches its stated contribution.

## 9. Execution plan: phases and decision gates

### Phase 0 — external novelty and preprocessing review (days 1-2)

- Run the deep-research prompts in `GEMINI_DEEP_RESEARCH.md` and manually inspect high-impact claimed sources.
- Freeze exact variant definitions, probe text, metric, thresholds, endpoint classes, and analysis code plan in a `PREREGISTER.md` hash.
- **Gate G0:** proceed only if no exact overlapping audit is found and the primary mechanism remains scientifically meaningful.

### Phase 1 — dataset and artifact construction (days 2-5)

- Implement modules in the LOC budget.
- Select/screen 50 base images and write license/provenance manifest.
- Generate canonical inputs, controls, hashes, and verification report.
- **Gate G1:** 100% offline invariance verification and deterministic regeneration from scripts. No API calls before this gate.

### Phase 2 — week-1 pilot / kill test (days 5-7)

- Run the pilot ceiling of 372 hosted calls.
- Lock prompt template after at most one revision. Any revision must occur before full collection and be recorded in the preregistration amendment.
- **Gate G2:** apply numeric go/kill criteria. Do not “tune until significant.”

### Phase 3 — full collection (week 2)

- Run the full matrix in randomized palindromic order.
- Keep each endpoint’s core collection inside a 72-hour window where possible.
- Start and end every endpoint batch with a small exact-repeat sentinel set; log outages, retries, rate-limit events, and unexpected empty responses.
- **Gate G3:** if a provider announces/changes a model or image preprocessing mid-run, freeze existing data as a separately labeled cohort rather than mixing it silently. OpenAI’s public changelog has previously shown that image-encoding bugs can be fixed and evaluations recommended for rerun: https://developers.openai.com/api/docs/changelog .

### Phase 4 — locked analysis (weeks 2-3)

- Freeze raw logs and input hashes.
- Run one versioned analysis script producing all tables/CIs/tests.
- Inspect positive controls before interpreting invariant nulls.
- **Gate G4:** decide whether result is positive, powered-null, or inconclusive using the preregistered logic. No post hoc redefinition of “invariant.”

### Phase 5 — write-up and artifact release (weeks 3-6)

- Write a 4-6 page workshop-style report.
- Release code, input hashes, generation scripts, raw response logs, endpoint model strings, exact dates, decoding parameters, dependency versions, and license/attribution manifest.
- Redistribute only bytes permitted by license. For other images, publish regeneration instructions and source identifiers.
- **Gate G5:** independent reproducibility check: delete generated variants and regenerate them from scripts; all SHA-256 values must match.

## 10. Venue plan with deadlines where known

As of 2026-11-25:

| Venue | Fit | Verified deadline/status | Plan |
|---|---|---|---|
| BEAM 2 @ ECCV 2026 — Benchmarking Evidence-Aligned Multimodal Reasoning | Excellent topical fit: evidence alignment, perturbation evaluation, auditing | **Missed.** Paper deadline 2026-07-31; workshop held 2026-09-08. Verified at https://beamv2-eccv-workshop.github.io/ | Do not treat as available. Use its framing but target successors/related workshops. |
| CVPR 2027 workshops, Seattle | Possible fit if a benchmarking/evaluation/robustness workshop is accepted | Workshop proposal deadline already passed 2026-11-04; workshop decisions due around 2026-12-22/23; workshops 2027-06-20/21. Verified at https://cvpr.thecvf.com/Conferences/2027/Dates | In late December 2026 inspect accepted workshops and individual paper deadlines. |
| IEEE ICME 2027 workshops, Xiamen | Strong fallback fit: multimedia security, forensics, evaluation, multimodal systems | Workshop paper submission deadline **2027-04-09**; acceptance 2027-05-05; camera-ready 2027-05-20; conference 2027-07-13 to 2027-07-17. Verified at https://2027.ieeeicme.org/about/important-dates | Primary realistic archival target. Select the most relevant accepted workshop once the list is public. |
| ACM Multimedia 2027 workshop/poster, Hong Kong | Good fit for multimedia provenance, security, evaluation | Conference dates verified as **2027-11-08 to 2027-11-12**, AsiaWorld-Expo, at https://2027.acmmm.org/ ; workshop contribution deadlines not yet published/verified as of this spec date | Secondary target. Do not assume 2026 dates carry over. |
| arXiv + artifact | Always available, appropriate for a negative or infrastructure result | No deadline | Minimum viable publication. Post after locked analysis regardless of workshop outcome. |

Submission framing depends on outcome:

- **Positive:** emphasize audited evidence, exact artifact, reproducibility, and the distinction from adversarial prompt injection.
- **Powered null:** emphasize that official metadata-exclusion claims were consistent with a controlled black-box audit at the instrument’s sensitivity, while documenting preprocessing uncertainty and detection limits.
- **Inconclusive:** do not submit as a result paper; release the harness and pilot as a methods note only if the failure itself is informative.

## 11. Risks and honest limitations

1. **Endpoint drift.** Hosted providers can change models, preprocessors, safety layers, or encoders without notice. Mitigate with frozen model strings where available, date stamping, palindromic order, sentinel repeats, and a 72-hour collection window. Cannot eliminate silent drift.
2. **Undocumented server preprocessing.** A null may mean metadata is stripped before the model rather than that the model ignores it. That is still evidence about the production pipeline but not about weights. A positive may reflect format-dependent transcoding, byte-size behavior, parser failure, caching, or metadata extraction rather than direct metadata tokenization.
3. **Official documentation may not cover every surface.** OpenAI and Anthropic publish metadata-exclusion statements; Gemini documentation verified resizing behavior but no comparably explicit metadata statement in targeted search. Inline API results do not generalize to web/mobile upload, URL ingestion, or Files API paths.
4. **JPEG decoder dependence.** Entropy-coded scan data are exactly preserved, but JPEG decoding can vary by IDCT/upsampling implementation. The invariant claim uses a pinned canonical decoder plus identical scan data; it is not a universal mathematical claim about every decoder.
5. **File-size confounding.** Metadata insertion changes byte length. Primary `JC`/`JA` are length-matched within ±16 bytes, but comparisons against stripped `J0` remain susceptible to size-dependent behavior. Report byte sizes and treat those contrasts as container sensitivity, not pure semantics.
6. **Exact-repeat caching.** If a provider caches full responses to byte-identical requests, the baseline can be artificially stable. Prompt caching is not necessarily response caching, but the distinction is not always public. This is a deep-research question and a limitation. Optional exploratory nonce-repeat diagnostics must not replace the preregistered baseline.
7. **Low power for subtle effects.** N=50 is powered only for large provenance effects. Null wording must use the observed CI and never claim general impossibility.
8. **Composite probe interference.** Asking three probes in one call can couple answers. It is a cost-control design. If pilot validity or cross-contamination is poor, separate calls require a redesigned budget.
9. **Forced-choice insensitivity.** Binary answers sacrifice nuance. Positive controls are therefore mandatory. Correctness is reported separately from stability.
10. **Metadata realism.** `JC` and `JA` are controlled parallel fixtures, not a representative sample of real camera or generator metadata. C2PA manifests, real camera heterogeneity, GPS/privacy fields, thumbnails, and malformed metadata are future work.
11. **Rate limits and cost.** Retries can break temporal ordering. Use checkpointing, conservative concurrency, exponential backoff, and cost ledger. If retries reorder a pair badly, keep data but flag the cell in sensitivity analysis.
12. **Licensing and URL rot.** COCO/OpenImages licensing is per-image and redistribution is complicated. Hashes and generation scripts do not fully solve disappearing source URLs. Preserve lawful local copies and publish what can lawfully be shared.
13. **Safety/refusal behavior.** Even innocuous provenance questions can trigger inconsistent safety or policy layers. Invalid/refusal outputs are reported, not silently scored as semantic answers.
14. **No causal weight-level inference.** Even a perfect positive establishes only that the deployed pipeline’s output depends on non-rendering container bytes. Only open-weight instrumentation could localize the mechanism, and that is outside this study.

## 12. Open questions requiring deep external research

These are the questions whose answers are genuinely uncertain and should not be invented:

1. **Exact prior art:** Does any 2023-2026 paper, benchmark, artifact, vendor evaluation, or industry post already perform a powered, non-adversarial, raster-hash-verified audit of embedded image-container metadata/provenance side channels in production VLM APIs? In particular, has `vision-input-check` or a similar harness been used to publish real endpoint results?
2. **Hosted preprocessing truth:** For OpenAI, Anthropic, and Google Gemini API paths, what is publicly documented or credibly reverse-engineered about EXIF/XMP/IPTC/C2PA stripping or parsing, orientation handling, ICC conversion, PNG ancillary chunks, JPEG APP markers, resizing/recompression, filename exposure, input deduplication, and response caching? Do inline base64, file upload, URL, web UI, and cloud-hosted paths differ?
3. **Forensically correct construction:** What is the strongest image-forensics evidence distinguishing pixel-level provenance signals from container/header signals, and exactly which JPEG/PNG container edits can be certified not to alter rendering-critical data under common decoders?
4. **Licensing/reproducibility:** Which selected COCO/OpenImages/CC0 derivatives can lawfully be redistributed, with what attribution/share-alike/noncommercial constraints, and is a hash-plus-source-ID artifact sufficient for community reproducibility norms?
5. **Venue fit:** After CVPR/ICME/ACM MM 2027 workshop lists are final, which workshop explicitly welcomes audits, negative results, benchmarking methodology, provenance, or multimedia security rather than only new state-of-the-art benchmarks?
