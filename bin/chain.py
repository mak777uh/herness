"""chain - проверка K9: композиция шагов и цепочка мостов.

Модель декларативная: checker читает объявленные замыкания шагов и разрешённые
адреса мостов, а не код downstream. Это policy-only проверка; она не доказывает
безопасность и не выдаёт `K9_proven`.

    python bin/chain.py check <chain.json>

Коды отказа (K5, явные):
  K9_ADJACENT_REQUIRED          — в цепочке нет adjacent-моста
  K9_CHAIN_UNPROVEN             — downstream-мост без доказательства композиции
  K9_PROVEN_BAD_FORMAT          — proof object не того типа/формы или путь небезопасен
  K9_PROVEN_MISSING_ARTIFACT    — объявленный proof artifact отсутствует
  K9_PROVEN_HASH_MISMATCH       — sha256 не совпадает с точными байтами artifact
  K9_PROVEN_SUBJECT_MISMATCH    — subject_sha256 не совпадает с канонической цепочкой
  K9_DOWNSTREAM_MISSING_DEST    — adjacent форвардит адрес, downstream его не пропускает
  K9_DOWNSTREAM_MISSING_METHOD  — adjacent разрешает метод, downstream его не покрывает
                                  (coverage: [] = deny-all на своей стороне,
                                   отсутствие поля — K9_SCHEMA)
  K9_TAINT_ESCAPE               — в композиции есть и секрет, и сеть
  K9_SCHEMA                     — декларация не того типа

Выход: 0 — цепочка допустима, 3 — отказ, 2 — ошибка чтения/разбора JSON.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAVEAT = "policy-only proof-binding check; it does not verify proof truth or downstream code"
SECRET_PREFIX = "secret:"
DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
PROOF_KINDS = frozenset({"lean-instance"})
PROOF_FIELDS = frozenset({"kind", "artifact", "sha256", "subject_sha256"})
MAX_SAFE_INTEGER = 2**53 - 1


class StrictJSONError(ValueError):
    """JSON не входит в строгий JCS-subset репозитория."""


def _destinations(bridge: dict) -> list[str]:
    return [str(item) for item in (bridge or {}).get("allowed_destinations", [])]


def _methods(bridge: dict) -> list[str]:
    return [str(item) for item in (bridge or {}).get("allowed_methods", [])]


def _problem(code: str, message: str, **extra: object) -> dict:
    return {"code": code, "message": message, **extra}


def _canonical_value(value: object) -> object:
    """JCS-subset из admission.py: без float, duplicate и unsafe integer.

    Локальная реализация намеренно не импортирует admission.py: тот требует
    cryptography уже при импорте, а K9-checker должен оставаться stdlib-only.
    """
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise StrictJSONError("integer outside ±(2^53−1)")
        return value
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.isascii():
                raise StrictJSONError("object keys must be ASCII strings")
            result[key] = _canonical_value(item)
        return result
    raise StrictJSONError(f"unsupported JSON value: {type(value).__name__}")


def canonical_json(value: object) -> str:
    """Канонические UTF-8 байты декларации в строгом JCS-subset."""
    return json.dumps(_canonical_value(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def proof_subject(decl: dict) -> dict:
    """Предмет привязки: вся цепочка, но без bridge-level `proven`.

    Удаляются только поля proven у adjacent и элементов downstream. Остальные
    одноимённые поля внутри steps/Policy остаются частью subject.
    """
    subject = copy.deepcopy(decl)
    adjacent = subject.get("adjacent")
    if isinstance(adjacent, dict):
        adjacent.pop("proven", None)
    downstream = subject.get("downstream")
    if isinstance(downstream, list):
        for bridge in downstream:
            if isinstance(bridge, dict):
                bridge.pop("proven", None)
    return subject


def subject_sha256(decl: dict) -> str:
    return digest_bytes(canonical_json(proof_subject(decl)).encode("utf-8"))


def proof_object(subject: str, artifact: str = "proofs/Proofs/ChainInstances.lean",
                 root: Path = ROOT) -> dict:
    """Собрать proof-binding для тестов/фикстур из реальных байтов artifact."""
    path = Path(root) / Path(*artifact.split("/"))
    return {
        "kind": "lean-instance",
        "artifact": artifact,
        "sha256": digest_file(path),
        "subject_sha256": subject,
    }


def _safe_artifact_path(value: object, root: Path) -> tuple[Path | None, str | None]:
    """Repo-relative POSIX path; traversal/absolute/backslash отвергаются до чтения."""
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return None, "artifact must be a non-empty repo-relative POSIX path"
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        return None, "artifact must be repo-relative"
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None, "artifact path must not contain empty, dot or parent segments"
    try:
        root_resolved = Path(root).resolve()
        target = (root_resolved / Path(*parts)).resolve()
        target.relative_to(root_resolved)
    except ValueError:
        return None, "artifact resolves outside repository root"
    except (OSError, RuntimeError) as exc:
        return None, f"artifact path cannot be resolved: {exc}"
    return target, None


def _verify_proof(proof: object, expected_subject: str, bridge_id: object,
                  root: Path) -> list[dict]:
    """Проверить форму, subject и exact-byte artifact; истинность не проверяется."""
    umbrella = _problem(
        "K9_CHAIN_UNPROVEN",
        f"bridge {bridge_id!r} has no valid composition proof binding",
        bridge=bridge_id,
    )
    if not isinstance(proof, dict):
        return [umbrella, _problem("K9_PROVEN_BAD_FORMAT", "proven must be an object",
                                   bridge=bridge_id)]
    if set(proof) != PROOF_FIELDS:
        return [umbrella, _problem(
            "K9_PROVEN_BAD_FORMAT",
            "proven must contain exactly kind, artifact, sha256, subject_sha256",
            bridge=bridge_id,
        )]
    kind = proof.get("kind")
    if not isinstance(kind, str) or kind not in PROOF_KINDS:
        return [umbrella, _problem("K9_PROVEN_BAD_FORMAT", "unsupported proof kind",
                                   bridge=bridge_id, kind=kind)]
    if not isinstance(proof.get("sha256"), str) or not DIGEST_RE.fullmatch(proof["sha256"]):
        return [umbrella, _problem("K9_PROVEN_BAD_FORMAT", "sha256 must be 64 lowercase hex",
                                   bridge=bridge_id)]
    if (not isinstance(proof.get("subject_sha256"), str)
            or not DIGEST_RE.fullmatch(proof["subject_sha256"])):
        return [umbrella, _problem("K9_PROVEN_BAD_FORMAT",
                                   "subject_sha256 must be 64 lowercase hex", bridge=bridge_id)]

    path, path_error = _safe_artifact_path(proof.get("artifact"), root)
    if path_error or path is None:
        return [umbrella, _problem("K9_PROVEN_BAD_FORMAT", path_error or "invalid artifact path",
                                   bridge=bridge_id, artifact=proof.get("artifact"))]

    problems: list[dict] = []
    if proof["subject_sha256"] != expected_subject:
        problems.append(_problem(
            "K9_PROVEN_SUBJECT_MISMATCH",
            "proof subject_sha256 does not match the canonical chain subject",
            bridge=bridge_id,
            expected=expected_subject,
            actual=proof["subject_sha256"],
        ))
    if not path.is_file():
        problems.append(_problem("K9_PROVEN_MISSING_ARTIFACT", "proof artifact is missing",
                                 bridge=bridge_id, artifact=proof["artifact"]))
        return [umbrella, *problems]
    try:
        actual_digest = digest_file(path)
    except OSError as exc:
        problems.append(_problem("K9_PROVEN_MISSING_ARTIFACT", "proof artifact is unreadable",
                                 bridge=bridge_id, artifact=proof["artifact"], error=str(exc)))
        return [umbrella, *problems]
    if actual_digest != proof["sha256"]:
        problems.append(_problem(
            "K9_PROVEN_HASH_MISMATCH",
            "proof sha256 does not match the exact artifact bytes",
            bridge=bridge_id,
            artifact=proof["artifact"],
            expected=proof["sha256"],
            actual=actual_digest,
        ))
    return [umbrella, *problems] if problems else []


def _object_pairs(pairs: list[tuple[str, object]]) -> dict:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJSONError(f"duplicate object key: {key!r}")
        if not key.isascii():
            raise StrictJSONError("object keys must be ASCII strings")
        result[key] = value
    return result


def _parse_integer(text: str) -> int:
    value = int(text)
    if abs(value) > MAX_SAFE_INTEGER:
        raise StrictJSONError("integer outside ±(2^53−1)")
    return value


def _reject_number(text: str) -> object:
    raise StrictJSONError(f"non-integer JSON number is not allowed: {text}")


def load_json(path: Path) -> object:
    """Строгий JSON: duplicate key, float/NaN и unsafe integer отвергаются."""
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_object_pairs,
                      parse_int=_parse_integer, parse_float=_reject_number,
                      parse_constant=_reject_number)


def reads_secret(step: dict) -> bool:
    """Шаг читает секрет: источник начинается с `secret:`."""
    return any(str(source).startswith(SECRET_PREFIX) for source in step.get("reads", []))


def sends_external(step: dict) -> bool:
    """Шаг отправляет наружу: у него есть хотя бы один адрес в `sends`."""
    return bool(step.get("sends", []))


def step_leaks(step: dict) -> bool:
    """Утечка одного шага: он и читает секрет, и отправляет наружу."""
    return reads_secret(step) and sends_external(step)


def check_chain(decl: dict, root: Path = ROOT) -> dict:
    """Проверить одну декларацию цепочки. Возвращает отчёт, не бросает."""
    if not isinstance(decl, dict):
        return {"law": "K9", "ok": False, "caveat": CAVEAT,
                "problems": [_problem("K9_SCHEMA", "declaration must be an object")]}

    problems: list[dict] = []
    try:
        expected_subject = subject_sha256(decl)
    except (StrictJSONError, ValueError, UnicodeError) as exc:
        expected_subject = None
        problems.append(_problem("K9_SCHEMA", f"declaration is not canonical JSON: {exc}"))

    adjacent = decl.get("adjacent")
    downstream = decl.get("downstream", [])
    steps = decl.get("steps", [])

    if not isinstance(adjacent, dict) or not adjacent:
        problems.append(_problem("K9_ADJACENT_REQUIRED", "chain has no adjacent bridge"))
        adjacent = None
    if not isinstance(downstream, list):
        problems.append(_problem("K9_SCHEMA", "downstream must be a list"))
        downstream = []
    if not isinstance(steps, list):
        problems.append(_problem("K9_SCHEMA", "steps must be a list"))
        steps = []

    # Adjacent proof не обязателен, но если поле есть — boolean legacy не принимается.
    if adjacent is not None and "proven" in adjacent:
        proof = adjacent["proven"]
        if isinstance(proof, bool):
            problems.append(_problem("K9_SCHEMA", "boolean proven is not accepted",
                                     bridge=adjacent.get("id", "?")))
        elif expected_subject is not None:
            problems.extend(_verify_proof(proof, expected_subject, adjacent.get("id", "?"), root))

    for index, bridge in enumerate(downstream):
        if not isinstance(bridge, dict):
            problems.append(_problem("K9_SCHEMA", "downstream entry must be an object", index=index))
            continue
        if "proven" not in bridge:
            problems.append(_problem(
                "K9_CHAIN_UNPROVEN",
                f"downstream bridge {bridge.get('id', index)!r} has no composition proof",
                bridge=bridge.get("id", index),
            ))
            continue
        proof = bridge["proven"]
        if isinstance(proof, bool):
            problems.append(_problem(
                "K9_CHAIN_UNPROVEN",
                f"downstream bridge {bridge.get('id', index)!r} has only a boolean proof claim",
                bridge=bridge.get("id", index),
            ))
            problems.append(_problem("K9_SCHEMA", "boolean proven is not accepted",
                                     bridge=bridge.get("id", index)))
        elif expected_subject is not None:
            problems.extend(_verify_proof(proof, expected_subject, bridge.get("id", index), root))

    adjacent_destinations = _destinations(adjacent) if adjacent else []
    adjacent_methods = _methods(adjacent) if adjacent else []
    if adjacent and "allowed_methods" not in adjacent:
        problems.append(_problem(
            "K9_SCHEMA",
            f"adjacent bridge {adjacent.get('id', '?')!r} has no allowed_methods",
            bridge=adjacent.get("id", "?"),
        ))
    for bridge in downstream:
        if not isinstance(bridge, dict):
            continue
        destinations = _destinations(bridge)
        for destination in adjacent_destinations:
            if destination not in destinations:
                problems.append(_problem(
                    "K9_DOWNSTREAM_MISSING_DEST",
                    f"adjacent forwards {destination!r} but downstream "
                    f"{bridge.get('id', '?')!r} does not",
                    dest=destination,
                    bridge=bridge.get("id", "?"),
                ))
        methods = _methods(bridge)
        if "allowed_methods" not in bridge:
            problems.append(_problem(
                "K9_SCHEMA",
                f"downstream bridge {bridge.get('id', '?')!r} has no allowed_methods",
                bridge=bridge.get("id", "?"),
            ))
            continue
        if adjacent_methods:
            for method in adjacent_methods:
                if method not in methods:
                    problems.append(_problem(
                        "K9_DOWNSTREAM_MISSING_METHOD",
                        f"adjacent allows {method!r} but downstream "
                        f"{bridge.get('id', '?')!r} does not",
                        method=method,
                        bridge=bridge.get("id", "?"),
                    ))

    readers = [str(step.get("id", index)) for index, step in enumerate(steps)
               if isinstance(step, dict) and reads_secret(step)]
    senders = [str(step.get("id", index)) for index, step in enumerate(steps)
               if isinstance(step, dict) and sends_external(step)]
    if readers and senders:
        problems.append(_problem(
            "K9_TAINT_ESCAPE",
            "composition reads a secret and sends external; refused",
            readers=readers,
            senders=senders,
        ))

    if not adjacent:
        reachable: list[str] = []
    elif not downstream:
        reachable = sorted(set(adjacent_destinations))
    else:
        common = set(adjacent_destinations)
        for bridge in downstream:
            if isinstance(bridge, dict):
                common &= set(_destinations(bridge))
        reachable = sorted(common)

    broader = sorted({dest for bridge in downstream if isinstance(bridge, dict)
                      for dest in _destinations(bridge)} - set(adjacent_destinations))

    return {
        "law": "K9",
        "ok": not problems,
        "problems": problems,
        "caveat": CAVEAT,
        "subject_sha256": expected_subject,
        "reachable_through_chain": reachable,
        "downstream_broader_unreachable": broader,
        "reads_secret": readers,
        "sends_external": senders,
        "steps": len(steps),
        "per_step_leaks": [str(step.get("id", index)) for index, step in enumerate(steps)
                           if isinstance(step, dict) and step_leaks(step)],
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] != "check":
        print("usage: python bin/chain.py check <chain.json>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    try:
        decl = load_json(path)
    except StrictJSONError as exc:
        result = {"law": "K9", "ok": False, "caveat": CAVEAT,
                  "problems": [_problem("K9_SCHEMA", f"strict JSON refused: {exc}")]}
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 3
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"chain: {exc}", file=sys.stderr)
        return 2
    if not isinstance(decl, dict):
        result = {"law": "K9", "ok": False, "caveat": CAVEAT,
                  "problems": [_problem("K9_SCHEMA", "declaration must be a JSON object")]}
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 3
    result = check_chain(decl)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0 if result["ok"] else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
