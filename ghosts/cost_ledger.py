import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

USD_QUANTUM = Decimal("0.00000001")
GENESIS_HASH = "GENESIS"


class CostCapAbort(RuntimeError):
    def __init__(self, label: str, cumulative_usd: Decimal, projected_usd: Decimal, hard_cap_usd: Decimal):
        self.label = label
        self.cumulative_usd = cumulative_usd
        self.projected_usd = projected_usd
        self.hard_cap_usd = hard_cap_usd
        super().__init__(
            f"cost cap abort before {label}: cumulative={usd_string(cumulative_usd)} "
            f"projected={usd_string(projected_usd)} hard_cap={usd_string(hard_cap_usd)}"
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def canonical_json_bytes(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def decimal_value(value: str | int | float | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def usd_string(value: Decimal) -> str:
    return format(value.quantize(USD_QUANTUM), "f")


def cost_for_tokens(input_tokens: int, output_tokens: int, input_price: Decimal, output_price: Decimal) -> Decimal:
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token counts must be non-negative")
    return (Decimal(input_tokens) * input_price + Decimal(output_tokens) * output_price) / Decimal(1_000_000)


class CostLedger:
    def __init__(
        self,
        path: Path,
        hard_cap_usd: str | float | Decimal,
        input_price_per_million_usd: str | float | Decimal = Decimal("0.50"),
        output_price_per_million_usd: str | float | Decimal = Decimal("1.50"),
    ):
        self.path = path
        self.hard_cap_usd = decimal_value(hard_cap_usd)
        self.input_price = decimal_value(input_price_per_million_usd)
        self.output_price = decimal_value(output_price_per_million_usd)

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        for line_number, line in enumerate(self.path.read_text().splitlines(), start=1):
            if not line.strip():
                raise ValueError(f"blank line in append-only ledger at line {line_number}")
            rows.append(json.loads(line))
        return rows

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        return cost_for_tokens(input_tokens, output_tokens, self.input_price, self.output_price)

    def cumulative_cost(self) -> Decimal:
        total = Decimal(0)
        for entry in self.entries():
            total += Decimal(entry["cost_usd"])
        return total

    def conservative_input_tokens(self, request_body: bytes) -> int:
        return (len(request_body) + 3) // 4 + 8

    def projected_cost(self, request_body: bytes, max_output_tokens: int) -> Decimal:
        return self.cost(self.conservative_input_tokens(request_body), max_output_tokens)

    def check_cap(self, projected_cost_usd: Decimal, label: str) -> None:
        cumulative = self.cumulative_cost()
        if cumulative + projected_cost_usd > self.hard_cap_usd:
            raise CostCapAbort(label, cumulative, projected_cost_usd, self.hard_cap_usd)

    def append_call(
        self,
        *,
        call_id: str,
        phase: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        usage_source: str,
        request_sha256: str,
        response_sha256: str,
        http_status: int | None = None,
    ) -> dict:
        errors = self.verify()
        if errors:
            raise ValueError("refusing to append to invalid ledger: " + "; ".join(errors))
        if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
            raise TypeError("ledger token counts must be integers")
        cost = self.cost(input_tokens, output_tokens)
        rows = self.entries()
        cumulative = self.cumulative_cost() + cost
        previous = rows[-1]["entry_sha256"] if rows else GENESIS_HASH
        entry = {
            "schema": "container-ghosts.cost-ledger-entry.v1",
            "sequence": len(rows) + 1,
            "utc": utc_now(),
            "call_id": call_id,
            "phase": phase,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "input_price_per_million_usd": str(self.input_price),
            "output_price_per_million_usd": str(self.output_price),
            "cost_usd": usd_string(cost),
            "cumulative_cost_usd": usd_string(cumulative),
            "hard_cap_usd": usd_string(self.hard_cap_usd),
            "usage_source": usage_source,
            "http_status": http_status,
            "request_sha256": request_sha256,
            "response_sha256": response_sha256,
            "previous_entry_sha256": previous,
        }
        entry["entry_sha256"] = sha256_bytes(canonical_json_bytes(entry))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return entry

    def verify(self) -> list[str]:
        errors = []
        try:
            rows = self.entries()
        except (ValueError, json.JSONDecodeError) as exc:
            return [f"ledger is not readable as append-only JSON lines: {exc}"]
        expected_sequence = 1
        expected_previous = GENESIS_HASH
        expected_cumulative = Decimal(0)
        for row in rows:
            if row.get("sequence") != expected_sequence:
                errors.append(f"ledger sequence gap at entry {expected_sequence}")
            if row.get("previous_entry_sha256") != expected_previous:
                errors.append(f"ledger hash-chain break at sequence {expected_sequence}")
            try:
                input_tokens = int(row["input_tokens"])
                output_tokens = int(row["output_tokens"])
                cost = Decimal(row["cost_usd"])
                cumulative = Decimal(row["cumulative_cost_usd"])
            except (KeyError, TypeError, ValueError) as exc:
                errors.append(f"ledger numeric fields invalid at sequence {expected_sequence}: {exc}")
                break
            want_cost = self.cost(input_tokens, output_tokens)
            if cost != want_cost:
                errors.append(f"ledger cost mismatch at sequence {expected_sequence}")
            expected_cumulative += cost
            if cumulative != expected_cumulative:
                errors.append(f"ledger cumulative mismatch at sequence {expected_sequence}")
            if cumulative > self.hard_cap_usd:
                errors.append(f"ledger cumulative cost exceeds hard cap at sequence {expected_sequence}")
            stored_hash = row.get("entry_sha256")
            unsigned = dict(row)
            unsigned.pop("entry_sha256", None)
            want_hash = sha256_bytes(canonical_json_bytes(unsigned))
            if stored_hash != want_hash:
                errors.append(f"ledger entry hash mismatch at sequence {expected_sequence}")
            expected_previous = str(stored_hash)
            expected_sequence += 1
        return errors
