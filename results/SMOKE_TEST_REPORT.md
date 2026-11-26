# Vyce Relay Smoke Test Report

**INSTRUMENT VALIDATION ONLY ON A NON-PAPER-GRADE RELAY ENDPOINT. This is not a scientific result, not evidence about any production frontier pipeline, and not evidence about NVIDIA's real serving stack. The relayed open-model endpoint was used only to test adapter plumbing before first-party execution.**

## 1. Executive outcome

Status: **BLOCKED BEFORE VISION VALIDATION**.

One live inline-image chat-completions call was attempted against `https://vyceai.com/v1/chat/completions` with requested model `nemotron-3.5-super-vl`. The relay returned HTTP 402 with this exact error payload:

```json
{"error":{"message":"Insufficient balance. Please top up your account.","type":"insufficient_quota","param":null,"code":"insufficient_balance"},"request_id":"n/a"}
```

The remaining 15 planned calls were not attempted. This outcome does **not** establish that the model cannot process images. It also does not establish that it can. Vision capability remains unresolved because the request was rejected for account balance before any model generation was observed.

What was validated live:

- the adapter constructed an OpenAI-compatible chat-completions request containing inline base64 image bytes;
- the request reached the relay and received a structured JSON error response;
- raw request and response bytes were archived before analysis;
- transport/error capture, latency capture, hash pinning, and ledger append all executed.

What was **not** validated live:

- successful image acceptance by the model;
- response-text generation or exact-grammar parsing from a real generation;
- semantic correctness, exact-repeat agreement, cross-container behavior, canary behavior, or refusal behavior;
- the served model snapshot/version string, because the error response contained no `model` field.

## 2. Cost accounting

**Exact observed successful-generation spend: $0.00000000.** There were zero successful generations, zero API-reported input tokens, and zero API-reported output tokens. The sole request was rejected with `insufficient_balance`.

The append-only cap ledger intentionally uses conservative fallback accounting when usage is absent. Under that cap-accounting rule it recorded a worst-case debit of **$0.00801000** for the failed request. This is not evidence of an actual relay charge; it is a conservative cap-control artifact.

| Cost measurement | Value |
|---|---:|
| Hard cap | $4.00000000 |
| Exact observed successful-generation spend | $0.00000000 |
| Conservative cap-ledger debit for the failed call | $0.00801000 |
| Conservative precomputed cap projection for all 16 planned calls | $0.32594200 |
| API usage returned by relay | none |
| Assumed cap prices | $0.50 input / $1.50 output per 1M tokens |

Ledger validation after the live failure: no hash-chain, arithmetic, sequence, or cap errors.

## 3. Empirical meaning of `requires_verification`

A non-generation `GET /v1/models` preflight succeeded with HTTP 200 when using a browser-like user agent. The catalog response is preserved as `results/vyce-smoke/preflight_models_response.json`.

Relevant facts from that response:

- `nemotron-3.5-super-vl` is present, `owned_by` is `nvidia`, and `context_window` is `1000000`.
- `requires_verification: true` appears on **all six** catalog entries, not only on vision-capable entries.
- The completion attempt then failed with `insufficient_balance`, not with a vision-specific or verification-specific error code.

Empirical interpretation, limited to these observations: the catalog flag is not a vision-capability flag. It is consistent with an account-level verification or entitlement gate, but this test did not isolate that mechanism because balance failure occurred first.

## 4. Planned smoke protocol

The planned protocol was deliberately small and separate from the scientific battery:

- development image: `object_arrangement`;
- 12 core calls in the existing palindromic order: `J0, PT, P0, P1, JC, JA, JA, JC, P1, P0, PT, J0`;
- two additional exact-repeat control pairs: `J0,J0` and `P0,P0`;
- total planned live generation calls: 16;
- temperature: 0;
- maximum output tokens: 16;
- transport: inline base64 raw bytes in OpenAI-compatible `image_url` chat-completions format;
- first/manual gate call: `core-000`, variant `J0`.

Only `core-000` was attempted. The exact transmitted image was `artifacts/variants/object_arrangement__J0.jpg`:

| Measurement | Value |
|---|---|
| Image SHA-256 | `eb9bf1d202eee3e8438d79d5a1e25417a4936e5fd89692c2cdb6c3965f7ac244` |
| Image byte length | 47,381 |
| Base64 SHA-256 | `e12438082b1ddf6a762f32d6dcd40804fb25fa4a92c2036cee49ac6d65a81b12` |
| Nonce | `GHOSTNONCE_9D8B5AB2DD19912A` |

## 5. Live transport and relay artifacts

| Field | Observed value |
|---|---|
| HTTP status | 402 |
| Latency | 5496.412 ms |
| Request ID header | `req_mwx6r04xe48ec7ad7d7f` |
| Served model field | absent |
| System fingerprint | absent |
| Finish reason | absent |
| Refusal field | absent |
| Response text | empty |
| Usage object | absent |
| Rate-limit headers | none observed |
| Extra top-level response fields | `error`, `request_id` |

The raw request artifact contains no API key. Request headers are represented in records only with `Bearer <redacted>`. `smoke_summary.json` intentionally reports structural validation errors for the incomplete 1/16-call run (missing planned calls and incomplete ABBA positions); those errors are the fail-closed evidence of the stop, not a claim that completed data are scientifically usable.

## 6. Offline verification evidence

These checks validate instrument plumbing, not model behavior:

| Gate | Result |
|---|---|
| Full `./run.sh` | PASS |
| Unit tests | 27 passed |
| Deterministic regeneration | PASS |
| One-pixel verifier mutation control | PASS under Pillow and OpenCV |
| Existing mock probe dry run | PASS, 48 mock calls, 0 live calls |
| Adapter payload mutation test | PASS: corrupted inline base64 raises `PayloadIntegrityError` before network use; captured network calls remain 0 |
| Cost-ledger tiny-cap unit test | PASS: artificially tiny cap raises `CostCapAbort` |
| Runner batch-cap integration test | PASS: tiny cap aborts before any transport call or record append |
| Fake-transport end-to-end runner test | PASS: 16/16 planned calls complete, validation errors 0, ledger entries 16 |
| Live ledger hash-chain validation | PASS, no errors |

The fake-transport end-to-end test uses a deterministic local fake response. It proves scheduling, raw archiving, parsing, repeat-pair bookkeeping, artifact hashing, and ledger integration. It says nothing about Vyce or nemotron behavior.

## 7. Hash-pinned artifacts

| Artifact | SHA-256 |
|---|---|
| `configs/vyce_smoke.json` | `729f65d72be7073d77795cd594dac84482adb9581e043d3cfc0dd9ff1cc2a19a` |
| `ghosts/openai_compatible.py` | `1de34deac82df90e692f5db86c826e2cdee147719fb1dc84aa42081aa119fd44` |
| `ghosts/cost_ledger.py` | `c2b8c73101613d93d4fb375c969ae60c5381806f77f59aacafdbd4be934b82cf` |
| `ghosts/vyce_smoke.py` | `e41077015e94a40edb4f8d09689314c2e9afb3da6712584c82a03851512905a1` |
| `tests/test_live_smoke.py` | `522c9423f05269acfd48db0dbbe523b3b136dc46e598807aa46bab00633bb423` |
| `results/vyce-smoke/smoke_plan.json` | `2be829d1611fe7072c4511dea6c3adaa571ab03db7bd04fd28d32606c5454454` |
| `results/vyce-smoke/raw/0000_core-000_request.json` | `6346b574aa47dc25fe70aaa5b9869ffa481d2a8909205517ea5eb1ea3ee41e5e` |
| `results/vyce-smoke/raw/0000_core-000_response.json` | `ad38e908150c482cb9d2121c4d6573dcf7ed153fdb980dcdd45bf351b83e5523` |
| `results/vyce-smoke/records.jsonl` | `f729e384cb428ca48b11f38b35c38a28e31ddc527addb0af95f5006344c8e763` |
| `results/vyce-smoke/cost_ledger.jsonl` | `0fdffe77d84d22e2e39cc237dcfd3a22ef417796667bebf20387ed2b1b06fbb6` |
| `results/vyce-smoke/preflight_models_response.json` | `49fec52bcfd39b1c8857d0b0b036116f074c97886682742329c36e864daff66d` |
| `results/vyce-smoke/preflight_models_meta.json` | `2162e456f2f8aba4deea0e951960ca9b78da5d101efcf0349eca41317d6de809` |
| `results/vyce-smoke/preflight_models_python_ua_response.json` | `621a2450709334bc4c65216b69954c61c3916f6df29f58d2380dc9e9333f41e1` |
| `results/vyce-smoke/preflight_models_python_ua_meta.json` | `034f019c78c3df10e1b2e7fc07f59f08cced86acbaae21d1eb4b6883362eb575` |
| `results/vyce-smoke/capability_gate.json` | `e0c393cfd893bb5513a4ca5d7d5d75b0ab0d03d7ff359ff40d662c31144e0967` |
| `results/vyce-smoke/relay_artifacts.json` | `7ddf4c2e275a18a59ae81a82c37556f48daa789e3b29fe0f95616fe6eb396097` |
| `results/vyce-smoke/smoke_summary.json` | `4d85e4c5ccffa98b362de45037d4b83e1fd61214518608256493820e560d6765` |
| `results/vyce-smoke/run_state.json` | `0be40f3d8cbc376c20447aee70df2ba5f71d7b7545d2eb89ee81eaa62cbca409` |

`results/vyce-smoke/artifact_hashes.json` additionally pins the artifact set. Its own SHA-256 at report writing was `ea08466fb37ec8ae04bce26f9cf6784930b83185f5b3a0805426e2ba35551e4b`.

## 8. Behavioral observations

No nemotron behavior was observed. The model produced no text because no generation occurred. Therefore there are no semantic correctness results, no exact-repeat agreement results, no cross-container observations, no canary or provenance-marker emissions, and no refusal/quirk behaviors beyond the relay-level HTTP 402 insufficient-balance error. The zero count of canary text in an empty non-response is meaningless and is not evidence about metadata ingestion.

## 9. Adapter gaps and operational lessons

1. **Funding/entitlement gate:** the immediate blocker is account balance. A successful rerun requires a funded or otherwise entitled Vyce account. If verification is separately required, that remains untested.
2. **Fail-closed resume semantics:** the runner preserves failed attempts and stops on non-200 responses. A future funded rerun should use a fresh output directory, or the runner should be extended with attempt-aware resume semantics. Silent retry over a failed immutable transcript would be wrong.
3. **Cost semantics on errors:** conservative byte-based fallback accounting is appropriate for hard-cap protection but can overstate spend for pre-generation errors. A production runner should distinguish `cap_accounting_cost` from provider-confirmed billable cost where the provider exposes billing data.
4. **No retry/policy layer yet:** the smoke runner deliberately fails fast. Rate-limit backoff, bounded retries, sentinel batches, and provider-specific operability logic remain first-party execution work.
5. **Catalog access quirk:** the catalog required a browser-like user agent in preflight; the chat-completions endpoint itself was reachable with the adapter's explicit non-browser user agent. This is a relay operational artifact, not a model result.
6. **Served snapshot unavailable:** because no generation occurred, no served `model` or system fingerprint was returned. Only the requested model string `nemotron-3.5-super-vl` is pinned here.

## 10. Remaining prerequisites before first-party execution

The smoke branch does not remove any pre-execution gate from the main artifact:

- funded first-party API access for OpenAI, Anthropic, and Google;
- frozen dated model snapshots and exact API parameters;
- final licensed corpus, label audit, privacy/face review, and redistribution decisions;
- final numeric equivalence bound and timestamped preregistration lock;
- positive-control implementation and pass thresholds;
- production retry/rate-limit/sentinel batch logic;
- provider-confirmed price/billing reconciliation rather than conservative assumptions;
- separate Files API versus inline-ingestion contrast if still in scope.

VERIFY_REAL: local instrument gates passed (`./run.sh`, 27 tests, mutation-tested verifier, 48-call mock dry run). Live transport reached Vyce and archived hash-pinned raw bytes, but live end-to-end generation did not occur because HTTP 402 `insufficient_balance` blocked the first image call. Exact observed successful-generation spend: $0.00000000.
