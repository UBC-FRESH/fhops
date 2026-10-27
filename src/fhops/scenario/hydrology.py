"""Read and validate FEMIC hydrology response bundles.

FHOPS is a consumer of the FEMIC producer contract. This module pins a hydrology
response bundle, verifies manifest and artifact checksums, checks the bundle's
internal identities, and reports optional validation/model-card readiness. It
does not run FEMIC, fit distributions, or call WS4 at runtime.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

FEMIC_HYDROLOGY_MANIFEST_SCHEMA = "femic.hydrology.response.v1"
FEMIC_HYDROLOGY_MANIFEST_NAME = "manifest.json"
FEMIC_HYDROLOGY_REQUIRED_ROLES: tuple[str, ...] = (
    "response_surface",
    "flood_risk",
    "domain",
    "disturbance_ledger",
)
FEMIC_HYDROLOGY_OPTIONAL_ROLES: tuple[str, ...] = (
    "surrogate_model",
    "surrogate_validation",
    "frequency_fit",
    "frequency_pairing",
    "tier0_screening",
    "benchmark_check",
    "validation_report",
    "model_card",
    "pilot_run",
)
FEMIC_HYDROLOGY_ROLE_SCHEMAS: dict[str, str] = {
    "response_surface": "femic.hydrology.flood_response.v1",
    "flood_risk": "femic.hydrology.flood_risk.v1",
    "domain": "femic.hydrology.domain.v1",
    "disturbance_ledger": "femic.hydrology.disturbance.v1",
    "validation_report": "femic.hydrology.validation.v1",
    "model_card": "femic.hydrology.model_card.v1",
}
FEMIC_HYDROLOGY_REVIEW_STATUSES: tuple[str, ...] = (
    "not_reviewed",
    "review_pending",
    "reviewed",
    "reviewed_with_conditions",
)
FEMIC_HYDROLOGY_READINESS_STATUSES: tuple[str, ...] = (
    "not_available",
    "provisional",
    "conditionally_ready",
    "ready",
    "blocked",
)
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


class FemicHydrologyError(RuntimeError):
    """Raised when a FEMIC hydrology bundle cannot be consumed."""


@dataclass(frozen=True)
class FemicHydrologyArtifact:
    """One pinned artifact from a FEMIC hydrology manifest.

    Attributes
    ----------
    role : str
        Producer artifact role.
    relative_path : str
        Path relative to the bundle root.
    schema_version : str
        Artifact schema recorded by the producer.
    media_type : str
        Artifact media type.
    size_bytes : int
        Declared artifact size.
    sha256 : str
        Declared artifact SHA-256 digest.
    description : str
        Producer description.
    """

    role: str
    relative_path: str
    schema_version: str
    media_type: str
    size_bytes: int
    sha256: str
    description: str


@dataclass(frozen=True)
class FemicHydrologyBundle:
    """Validated and pinned FEMIC hydrology bundle metadata.

    Attributes
    ----------
    bundle_dir : Path
        Resolved bundle root.
    manifest_path : Path
        Resolved manifest path.
    bundle_id : str
        Producer bundle identifier.
    bundle_version : str
        Producer bundle version.
    generated_utc : str
        Producer generation timestamp.
    domain_id : str
        FEMIC domain identifier.
    ledger_id : str
        FEMIC disturbance-ledger identifier.
    response_surface_id : str
        FEMIC response-surface identifier.
    manifest_sha256 : str
        SHA-256 digest of the manifest bytes.
    artifacts : dict[str, FemicHydrologyArtifact]
        Artifacts keyed by role.
    response_surface : dict[str, object]
        Producer response-surface summary.
    flood_risk : dict[str, object]
        Producer flood-risk summary.
    applicability_domain : dict[str, object]
        Producer applicability domain.
    consumer_contract : dict[str, object]
        Producer consumer-contract metadata.
    caveats : tuple[str, ...]
        Producer caveats.
    total_bytes : int
        Sum of declared artifact sizes.
    """

    bundle_dir: Path
    manifest_path: Path
    bundle_id: str
    bundle_version: str
    generated_utc: str
    domain_id: str
    ledger_id: str
    response_surface_id: str
    manifest_sha256: str
    artifacts: dict[str, FemicHydrologyArtifact]
    response_surface: dict[str, object]
    flood_risk: dict[str, object]
    applicability_domain: dict[str, object]
    consumer_contract: dict[str, object]
    caveats: tuple[str, ...]
    total_bytes: int


@dataclass(frozen=True)
class FemicHydrologyValidation:
    """Validation report for a FEMIC hydrology bundle.

    Attributes
    ----------
    bundle_dir : Path
        Resolved bundle root.
    is_valid : bool
        Whether every required check passed.
    checked_utc : str
        Report timestamp.
    errors : tuple[str, ...]
        Blocking findings.
    warnings : tuple[str, ...]
        Non-blocking findings.
    artifact_count : int
        Number of artifacts inspected.
    total_bytes : int
        Sum of declared artifact sizes.
    """

    bundle_dir: Path
    is_valid: bool
    checked_utc: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    artifact_count: int
    total_bytes: int

    def to_dict(self) -> dict[str, object]:
        """Return the validation report as a JSON-serializable mapping.

        Returns
        -------
        dict[str, object]
            Bundle path, validity, findings, counts, and size.
        """
        return {
            "bundle_dir": str(self.bundle_dir),
            "is_valid": self.is_valid,
            "checked_utc": self.checked_utc,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "artifact_count": self.artifact_count,
            "total_bytes": self.total_bytes,
        }


@dataclass(frozen=True)
class FemicHydrologyReadiness:
    """Validation/model-card evidence for a pinned hydrology bundle.

    Attributes
    ----------
    status : str
        ``not_available``, ``provisional``, ``conditionally_ready``, ``ready``,
        or ``blocked``.
    validation_report_id : str | None
        Validation-report identifier, when packaged.
    model_card_id : str | None
        Model-card identifier, when packaged.
    review_status : str | None
        Producer model-card review status.
    full_process_pilot_ready : bool | None
        Producer full-pilot readiness flag.
    hydrologist_review_recorded : bool | None
        Producer review-record flag.
    tail_check_failures : dict[str, list[str]]
        Tail-check failures keyed by gauge/station.
    usable_fits : dict[str, list[str]]
        Usable fit methods keyed by gauge/station.
    benchmark_cases : int
        Published benchmark count.
    benchmark_passed : int
        Passed benchmark count.
    benchmark_failed : int
        Failed benchmark count.
    benchmark_not_evaluated : int
        Not-evaluated benchmark count.
    warnings : tuple[str, ...]
        Non-fatal evidence warnings.
    caveats : tuple[str, ...]
        Evidence caveats.
    evidence_sha256 : str
        Deterministic digest of the evidence record.
    """

    status: str
    validation_report_id: str | None
    model_card_id: str | None
    review_status: str | None
    full_process_pilot_ready: bool | None
    hydrologist_review_recorded: bool | None
    tail_check_failures: dict[str, list[str]]
    usable_fits: dict[str, list[str]]
    benchmark_cases: int
    benchmark_passed: int
    benchmark_failed: int
    benchmark_not_evaluated: int
    warnings: tuple[str, ...]
    caveats: tuple[str, ...]
    evidence_sha256: str

    def to_dict(self) -> dict[str, object]:
        """Return the readiness report as a JSON-serializable mapping.

        Returns
        -------
        dict[str, object]
            Status, evidence identifiers, failures, fits, benchmarks, and
            caveats.
        """
        return {
            "status": self.status,
            "validation_report_id": self.validation_report_id,
            "model_card_id": self.model_card_id,
            "review_status": self.review_status,
            "full_process_pilot_ready": self.full_process_pilot_ready,
            "hydrologist_review_recorded": self.hydrologist_review_recorded,
            "tail_check_failures": self.tail_check_failures,
            "usable_fits": self.usable_fits,
            "benchmark_cases": self.benchmark_cases,
            "benchmark_passed": self.benchmark_passed,
            "benchmark_failed": self.benchmark_failed,
            "benchmark_not_evaluated": self.benchmark_not_evaluated,
            "warnings": list(self.warnings),
            "caveats": list(self.caveats),
            "evidence_sha256": self.evidence_sha256,
        }


def validate_femic_hydrology_bundle(
    bundle_dir: Path,
    *,
    expected_bundle_id: str | None = None,
    expected_bundle_version: str | None = None,
    verify_checksums: bool = True,
) -> FemicHydrologyValidation:
    """Validate a FEMIC hydrology response bundle without raising.

    Parameters
    ----------
    bundle_dir : Path
        Bundle directory or manifest path.
    expected_bundle_id : str | None, optional
        Require this bundle identifier.
    expected_bundle_version : str | None, optional
        Require this bundle version.
    verify_checksums : bool, optional
        Verify every declared size and SHA-256. Defaults to True.

    Returns
    -------
    FemicHydrologyValidation
        Validation report with specific errors and warnings.
    """
    report, _bundle = _validate(
        bundle_dir,
        expected_bundle_id=expected_bundle_id,
        expected_bundle_version=expected_bundle_version,
        verify_checksums=verify_checksums,
    )
    return report


def load_femic_hydrology_bundle(
    bundle_dir: Path,
    *,
    expected_bundle_id: str | None = None,
    expected_bundle_version: str | None = None,
    verify_checksums: bool = True,
) -> FemicHydrologyBundle:
    """Load and validate a FEMIC hydrology bundle.

    Parameters
    ----------
    bundle_dir : Path
        Bundle directory or manifest path.
    expected_bundle_id : str | None, optional
        Require this bundle identifier.
    expected_bundle_version : str | None, optional
        Require this bundle version.
    verify_checksums : bool, optional
        Verify every declared size and SHA-256. Defaults to True.

    Returns
    -------
    FemicHydrologyBundle
        Validated bundle with artifact pins and summaries.

    Raises
    ------
    FemicHydrologyError
        If the bundle is invalid.
    """
    report, bundle = _validate(
        bundle_dir,
        expected_bundle_id=expected_bundle_id,
        expected_bundle_version=expected_bundle_version,
        verify_checksums=verify_checksums,
    )
    if not report.is_valid or bundle is None:
        raise FemicHydrologyError("; ".join(report.errors) or "Invalid hydrology bundle.")
    return bundle


def bundle_pin(bundle: FemicHydrologyBundle) -> dict[str, object]:
    """Return a stable downstream pin for a validated bundle.

    Parameters
    ----------
    bundle : FemicHydrologyBundle
        Validated bundle.

    Returns
    -------
    dict[str, object]
        Bundle identity, manifest digest, IDs, artifact pins, caveats, and the
        producer consumer contract.
    """
    return {
        "bundle_id": bundle.bundle_id,
        "bundle_version": bundle.bundle_version,
        "manifest_sha256": bundle.manifest_sha256,
        "domain_id": bundle.domain_id,
        "ledger_id": bundle.ledger_id,
        "response_surface_id": bundle.response_surface_id,
        "artifacts": {
            role: {
                "relative_path": artifact.relative_path,
                "schema_version": artifact.schema_version,
                "media_type": artifact.media_type,
                "size_bytes": artifact.size_bytes,
                "sha256": artifact.sha256,
            }
            for role, artifact in sorted(bundle.artifacts.items())
        },
        "caveats": list(bundle.caveats),
        "consumer_contract": bundle.consumer_contract,
    }


def read_femic_hydrology_domain(bundle: FemicHydrologyBundle) -> dict[str, object]:
    """Return the pinned FEMIC domain artifact.

    Parameters
    ----------
    bundle : FemicHydrologyBundle
        Validated bundle.

    Returns
    -------
    dict[str, object]
        Domain payload with watersheds and receptors.

    Raises
    ------
    FemicHydrologyError
        If the domain artifact is missing or malformed.
    """
    payload = _optional_payload(bundle, "domain")
    if payload is None:
        raise FemicHydrologyError("Hydrology bundle has no domain artifact.")
    return payload


def read_femic_hydrology_ledger(bundle: FemicHydrologyBundle) -> dict[str, object]:
    """Return the pinned FEMIC disturbance-ledger artifact.

    Parameters
    ----------
    bundle : FemicHydrologyBundle
        Validated bundle.

    Returns
    -------
    dict[str, object]
        Ledger payload with units and watershed assignments.

    Raises
    ------
    FemicHydrologyError
        If the ledger artifact is missing or malformed.
    """
    payload = _optional_payload(bundle, "disturbance_ledger")
    if payload is None:
        raise FemicHydrologyError("Hydrology bundle has no disturbance-ledger artifact.")
    return payload


def assess_femic_hydrology_readiness(
    bundle: FemicHydrologyBundle,
) -> FemicHydrologyReadiness:
    """Read optional validation-report and model-card evidence.

    Parameters
    ----------
    bundle : FemicHydrologyBundle
        Validated bundle.

    Returns
    -------
    FemicHydrologyReadiness
        Review, tail-check, fit, and benchmark evidence. Missing evidence is
        reported explicitly and never treated as approval.

    Raises
    ------
    FemicHydrologyError
        If a packaged evidence artifact is malformed.
    """
    validation = _optional_payload(bundle, "validation_report")
    card = _optional_payload(bundle, "model_card")
    warnings: list[str] = []
    validation_id: str | None = None
    card_id: str | None = None
    review_status: str | None = None
    full_process_ready: bool | None = None
    review_recorded: bool | None = None
    tail_failures: dict[str, list[str]] = {}
    usable_fits: dict[str, list[str]] = {}
    benchmark_cases = 0
    benchmark_passed = 0
    benchmark_failed = 0
    benchmark_not_evaluated = 0
    if validation is None:
        warnings.append("No validation_report artifact is packaged.")
    else:
        if validation.get("schema_version") != "femic.hydrology.validation.v1":
            raise FemicHydrologyError("Unsupported validation_report schema.")
        validation_id = _text(validation.get("validation_id"), "validation_id")
        summary = _mapping(validation.get("summary"), "validation summary")
        tail_failures = _failure_map(summary.get("tail_check_failures"), "tail_check_failures")
        usable_fits = _fit_map(summary.get("usable_fits"), "usable_fits")
        full_process_ready = _optional_bool(
            summary.get("full_process_pilot_ready"), "full_process_pilot_ready"
        )
        review_recorded = _optional_bool(
            summary.get("hydrologist_review_recorded"),
            "hydrologist_review_recorded",
        )
        benchmark_cases = _optional_int(summary.get("benchmark_cases"), 0) or 0
        benchmark_passed = _optional_int(summary.get("benchmark_passed"), 0) or 0
        benchmark_failed = _optional_int(summary.get("benchmark_failed"), 0) or 0
        benchmark_not_evaluated = _optional_int(summary.get("benchmark_not_evaluated"), 0) or 0
        if benchmark_not_evaluated:
            warnings.append(
                f"{benchmark_not_evaluated} published benchmark case(s) are not evaluated."
            )
    if card is None:
        warnings.append("No model_card artifact is packaged.")
    else:
        if card.get("schema_version") != "femic.hydrology.model_card.v1":
            raise FemicHydrologyError("Unsupported model_card schema.")
        card_id = _text(card.get("model_card_id"), "model_card_id")
        review_status = _text(card.get("review_status"), "review_status")
        if review_status not in FEMIC_HYDROLOGY_REVIEW_STATUSES:
            raise FemicHydrologyError(f"Unsupported model-card review status {review_status!r}.")
        summary = _mapping(card.get("validation_summary"), "model_card summary")
        card_failures = _failure_map(
            summary.get("tail_check_failures"), "model_card tail_check_failures"
        )
        if card_failures:
            tail_failures = card_failures
        card_fits = _fit_map(summary.get("usable_fits"), "model_card usable_fits")
        if card_fits:
            usable_fits = card_fits
        card_full = _optional_bool(
            summary.get("full_process_pilot_ready"), "model_card full_process_pilot_ready"
        )
        if card_full is not None:
            full_process_ready = card_full
        card_review = _optional_bool(
            summary.get("hydrologist_review_recorded"),
            "model_card hydrologist_review_recorded",
        )
        if card_review is not None:
            review_recorded = card_review
        linked = _optional_text(card.get("validation_report_id"))
        if linked is not None and validation_id is not None and linked != validation_id:
            raise FemicHydrologyError(
                "Model card validation_report_id does not match the validation report."
            )
    if tail_failures:
        warnings.append("Tail-check failures are recorded and must not be used silently.")
    if review_status is not None and review_status != "reviewed":
        warnings.append(f"Model card review status is {review_status!r}.")
    if validation is None and card is None:
        status = "not_available"
    elif tail_failures:
        status = "blocked"
    elif review_status == "reviewed" and review_recorded:
        status = "ready"
    elif review_status == "reviewed_with_conditions":
        status = "conditionally_ready"
    else:
        status = "provisional"
    evidence = {
        "validation_report_id": validation_id,
        "model_card_id": card_id,
        "review_status": review_status,
        "full_process_pilot_ready": full_process_ready,
        "hydrologist_review_recorded": review_recorded,
        "tail_check_failures": tail_failures,
        "usable_fits": usable_fits,
        "benchmark_cases": benchmark_cases,
        "benchmark_passed": benchmark_passed,
        "benchmark_failed": benchmark_failed,
        "benchmark_not_evaluated": benchmark_not_evaluated,
        "status": status,
    }
    digest = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return FemicHydrologyReadiness(
        status=status,
        validation_report_id=validation_id,
        model_card_id=card_id,
        review_status=review_status,
        full_process_pilot_ready=full_process_ready,
        hydrologist_review_recorded=review_recorded,
        tail_check_failures=tail_failures,
        usable_fits=usable_fits,
        benchmark_cases=benchmark_cases,
        benchmark_passed=benchmark_passed,
        benchmark_failed=benchmark_failed,
        benchmark_not_evaluated=benchmark_not_evaluated,
        warnings=tuple(warnings),
        caveats=(
            "Readiness reports producer evidence; it does not create a review.",
            "A structural checksum pass is not hydrologic validation.",
        ),
        evidence_sha256=f"hydro-evidence-{digest[:16]}",
    )


def _validate(
    bundle_dir: Path,
    *,
    expected_bundle_id: str | None,
    expected_bundle_version: str | None,
    verify_checksums: bool,
) -> tuple[FemicHydrologyValidation, FemicHydrologyBundle | None]:
    root = bundle_dir.expanduser().resolve()
    manifest_path = root if root.is_file() else root / FEMIC_HYDROLOGY_MANIFEST_NAME
    if manifest_path.is_file():
        root = manifest_path.parent
    checked = datetime.now(UTC).isoformat()
    errors: list[str] = []
    warnings: list[str] = []
    artifacts: dict[str, FemicHydrologyArtifact] = {}
    payloads: dict[str, dict[str, object]] = {}
    total_bytes = 0
    if not manifest_path.is_file():
        return (
            FemicHydrologyValidation(
                bundle_dir=root,
                is_valid=False,
                checked_utc=checked,
                errors=(f"Manifest is missing: {manifest_path}",),
                warnings=(),
                artifact_count=0,
                total_bytes=0,
            ),
            None,
        )
    try:
        raw = manifest_path.read_bytes()
    except OSError as exc:
        return (
            FemicHydrologyValidation(
                bundle_dir=root,
                is_valid=False,
                checked_utc=checked,
                errors=(f"Unable to read manifest: {exc}",),
                warnings=(),
                artifact_count=0,
                total_bytes=0,
            ),
            None,
        )
    manifest_sha = hashlib.sha256(raw).hexdigest()
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        errors.append(f"Manifest is not UTF-8: {exc}")
        manifest = None
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid manifest JSON: {exc}")
        manifest = None
    if not isinstance(manifest, Mapping):
        if not errors:
            errors.append("Manifest must be a JSON object.")
        return _report(root, checked, errors, warnings, 0, 0), None
    if manifest.get("schema_version") != FEMIC_HYDROLOGY_MANIFEST_SCHEMA:
        errors.append(f"Unsupported manifest schema {manifest.get('schema_version')!r}.")
    bundle_id = _required_text(manifest.get("bundle_id"), "bundle_id", errors)
    bundle_version = _required_text(manifest.get("bundle_version"), "bundle_version", errors)
    generated_utc = _required_text(manifest.get("generated_utc"), "generated_utc", errors)
    domain_id = _required_text(manifest.get("domain_id"), "domain_id", errors)
    ledger_id = _required_text(manifest.get("ledger_id"), "ledger_id", errors)
    surface_id = _required_text(manifest.get("response_surface_id"), "response_surface_id", errors)
    if expected_bundle_id is not None and bundle_id != expected_bundle_id:
        errors.append(f"Bundle id {bundle_id!r} does not match expected {expected_bundle_id!r}.")
    if expected_bundle_version is not None and bundle_version != expected_bundle_version:
        errors.append(
            f"Bundle version {bundle_version!r} does not match expected "
            f"{expected_bundle_version!r}."
        )
    surface_summary = _required_mapping(
        manifest.get("response_surface"), "response_surface", errors
    )
    risk_summary = _required_mapping(manifest.get("flood_risk"), "flood_risk", errors)
    applicability = _optional_mapping(
        manifest.get("applicability_domain"), "applicability_domain", errors
    )
    consumer_contract = _optional_mapping(
        manifest.get("consumer_contract"), "consumer_contract", errors
    )
    caveats = _string_list(manifest.get("caveats", []), "caveats", errors)
    artifacts_payload = manifest.get("artifacts")
    if not isinstance(artifacts_payload, list) or not artifacts_payload:
        errors.append("Manifest artifacts must be a non-empty list.")
        artifacts_payload = []
    for index, item in enumerate(artifacts_payload, start=1):
        artifact, payload = _artifact(
            root,
            item,
            index=index,
            verify_checksums=verify_checksums,
            errors=errors,
            warnings=warnings,
        )
        if artifact is None:
            continue
        if artifact.role in artifacts:
            errors.append(f"Duplicate artifact role {artifact.role!r}.")
            continue
        artifacts[artifact.role] = artifact
        total_bytes += artifact.size_bytes
        if payload is not None:
            payloads[artifact.role] = payload
    missing = [role for role in FEMIC_HYDROLOGY_REQUIRED_ROLES if role not in artifacts]
    if missing:
        errors.append("Missing required artifact roles: " + ", ".join(missing) + ".")
    if errors:
        return _report(root, checked, errors, warnings, len(artifacts), total_bytes), None
    assert isinstance(surface_summary, dict)
    assert isinstance(risk_summary, dict)
    assert isinstance(applicability, dict)
    assert isinstance(consumer_contract, dict)
    _validate_response_surface(
        payloads.get("response_surface"),
        surface_id=surface_id,
        summary=surface_summary,
        errors=errors,
    )
    _validate_flood_risk(
        payloads.get("flood_risk"),
        surface_id=surface_id,
        summary=risk_summary,
        return_periods=_return_periods(surface_summary),
        errors=errors,
    )
    _validate_domain(payloads.get("domain"), domain_id=domain_id, errors=errors)
    _validate_ledger(
        payloads.get("disturbance_ledger"),
        ledger_id=ledger_id,
        domain_id=domain_id,
        errors=errors,
    )
    if errors:
        return _report(root, checked, errors, warnings, len(artifacts), total_bytes), None
    bundle = FemicHydrologyBundle(
        bundle_dir=root,
        manifest_path=manifest_path,
        bundle_id=bundle_id,
        bundle_version=bundle_version,
        generated_utc=generated_utc,
        domain_id=domain_id,
        ledger_id=ledger_id,
        response_surface_id=surface_id,
        manifest_sha256=manifest_sha,
        artifacts=artifacts,
        response_surface=surface_summary,
        flood_risk=risk_summary,
        applicability_domain=applicability,
        consumer_contract=consumer_contract,
        caveats=caveats,
        total_bytes=total_bytes,
    )
    return _report(root, checked, errors, warnings, len(artifacts), total_bytes, valid=True), bundle


def _report(
    root: Path,
    checked: str,
    errors: list[str],
    warnings: list[str],
    artifact_count: int,
    total_bytes: int,
    *,
    valid: bool | None = None,
) -> FemicHydrologyValidation:
    return FemicHydrologyValidation(
        bundle_dir=root,
        is_valid=(not errors if valid is None else valid),
        checked_utc=checked,
        errors=tuple(errors),
        warnings=tuple(warnings),
        artifact_count=artifact_count,
        total_bytes=total_bytes,
    )


def _artifact(
    root: Path,
    item: object,
    *,
    index: int,
    verify_checksums: bool,
    errors: list[str],
    warnings: list[str],
) -> tuple[FemicHydrologyArtifact | None, dict[str, object] | None]:
    if not isinstance(item, Mapping):
        errors.append(f"Artifact {index} must be an object.")
        return None, None
    role = _required_text(item.get("role"), f"artifact {index} role", errors)
    relative_path = _required_text(
        item.get("relative_path"), f"artifact {index} relative_path", errors
    )
    schema_version = _required_text(
        item.get("schema_version"), f"artifact {index} schema_version", errors
    )
    media_type = _required_text(
        item.get("media_type", "application/json"), f"artifact {index} media_type", errors
    )
    size_bytes = _required_int(item.get("size_bytes"), f"artifact {index} size_bytes", errors)
    sha256 = _required_text(item.get("sha256"), f"artifact {index} sha256", errors).lower()
    if SHA256_PATTERN.fullmatch(sha256) is None:
        errors.append(f"Artifact {index} sha256 must be a 64-character hex digest.")
    description = str(item.get("description", ""))
    if not role:
        return None, None
    expected_schema = FEMIC_HYDROLOGY_ROLE_SCHEMAS.get(role)
    if expected_schema is None:
        warnings.append(f"Unknown optional artifact role {role!r}.")
    elif schema_version != expected_schema:
        errors.append(
            f"Artifact {role!r} schema {schema_version!r} does not match {expected_schema!r}."
        )
    path = Path(relative_path)
    if path.is_absolute():
        errors.append(f"Artifact {role!r} path must be relative: {relative_path!r}.")
        return None, None
    if ".." in path.parts:
        errors.append(f"Artifact {role!r} path must not traverse: {relative_path!r}.")
        return None, None
    member = (root / path).resolve()
    try:
        member.relative_to(root)
    except ValueError:
        errors.append(f"Artifact {role!r} path escapes the bundle: {relative_path!r}.")
        return None, None
    if not member.is_file():
        errors.append(f"Artifact {role!r} is missing: {relative_path!r}.")
        return None, None
    if verify_checksums:
        actual_size = member.stat().st_size
        if actual_size != size_bytes:
            errors.append(
                f"Artifact {role!r} size mismatch: declared {size_bytes}, actual {actual_size}."
            )
        actual_sha = hashlib.sha256(member.read_bytes()).hexdigest()
        if actual_sha != sha256:
            errors.append(f"Artifact {role!r} checksum mismatch.")
    try:
        payload = json.loads(member.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"Artifact {role!r} is not valid JSON: {exc}.")
        return None, None
    if not isinstance(payload, Mapping):
        errors.append(f"Artifact {role!r} must be a JSON object.")
        return None, None
    payload_dict = {str(key): value for key, value in payload.items()}
    payload_schema = payload_dict.get("schema_version")
    if isinstance(payload_schema, str) and payload_schema != schema_version:
        errors.append(
            f"Artifact {role!r} payload schema {payload_schema!r} does not match the manifest."
        )
    return (
        FemicHydrologyArtifact(
            role=role,
            relative_path=relative_path,
            schema_version=schema_version,
            media_type=media_type,
            size_bytes=size_bytes,
            sha256=sha256,
            description=description,
        ),
        payload_dict,
    )


def _validate_response_surface(
    payload: dict[str, object] | None,
    *,
    surface_id: str,
    summary: dict[str, object],
    errors: list[str],
) -> None:
    if payload is None:
        errors.append("Response-surface artifact is missing.")
        return
    if payload.get("surface_id") != surface_id:
        errors.append("Response-surface artifact ID does not match the manifest.")
    if payload.get("baseline_name") != summary.get("baseline_name"):
        errors.append("Response-surface baseline does not match the manifest.")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        errors.append("Response-surface rows must be a list.")
        return
    row_count = summary.get("row_count")
    if isinstance(row_count, int) and row_count != len(rows):
        errors.append("Response-surface row count does not match the manifest.")
    periods = _return_periods(payload)
    if periods != _return_periods(summary):
        errors.append("Response-surface return periods do not match the manifest.")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            errors.append(f"Response row {index} must be an object.")
            continue
        ratio = _finite_number(row.get("ratio"), f"response row {index} ratio", errors)
        baseline = _finite_number(
            row.get("baseline_quantile"), f"response row {index} baseline_quantile", errors
        )
        quantile = _finite_number(row.get("quantile"), f"response row {index} quantile", errors)
        difference = _finite_number(
            row.get("difference"), f"response row {index} difference", errors
        )
        if (
            ratio is not None
            and baseline is not None
            and quantile is not None
            and difference is not None
        ):
            if not math.isclose(quantile, baseline * ratio, rel_tol=1e-6, abs_tol=1e-6):
                errors.append(f"Response row {index} quantile does not match ratio.")
            if not math.isclose(difference, quantile - baseline, rel_tol=1e-6, abs_tol=1e-6):
                errors.append(f"Response row {index} difference does not match quantiles.")


def _validate_flood_risk(
    payload: dict[str, object] | None,
    *,
    surface_id: str,
    summary: dict[str, object],
    return_periods: tuple[float, ...],
    errors: list[str],
) -> None:
    if payload is None:
        errors.append("Flood-risk artifact is missing.")
        return
    if payload.get("source_surface_id") != surface_id:
        errors.append("Flood-risk source surface does not match the response surface.")
    if payload.get("table_id") != summary.get("table_id"):
        errors.append("Flood-risk table ID does not match the manifest.")
    if payload.get("baseline_name") != summary.get("baseline_name"):
        errors.append("Flood-risk baseline does not match the manifest.")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        errors.append("Flood-risk rows must be a list.")
        return
    row_count = summary.get("row_count")
    if isinstance(row_count, int) and row_count != len(rows):
        errors.append("Flood-risk row count does not match the manifest.")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            errors.append(f"Flood-risk row {index} must be an object.")
            continue
        for field in ("receptor_id", "watershed_id"):
            if not _required_text(row.get(field), f"flood-risk row {index} {field}", errors):
                continue
        period = _finite_number(
            row.get("return_period"), f"flood-risk row {index} return_period", errors
        )
        if period is not None and period not in return_periods:
            errors.append(f"Flood-risk row {index} return period is not in the surface.")
        baseline = _finite_number(
            row.get("baseline_peak_flow_m3s"),
            f"flood-risk row {index} baseline_peak_flow_m3s",
            errors,
        )
        scenario = _finite_number(
            row.get("scenario_peak_flow_m3s"),
            f"flood-risk row {index} scenario_peak_flow_m3s",
            errors,
        )
        ratio = _finite_number(row.get("ratio"), f"flood-risk row {index} ratio", errors)
        if baseline is not None and scenario is not None and ratio is not None and baseline > 0:
            if not math.isclose(ratio, scenario / baseline, rel_tol=1e-6, abs_tol=1e-6):
                errors.append(f"Flood-risk row {index} ratio does not match the flows.")


def _validate_domain(
    payload: dict[str, object] | None,
    *,
    domain_id: str,
    errors: list[str],
) -> None:
    if payload is None:
        errors.append("Domain artifact is missing.")
        return
    if payload.get("domain_id") != domain_id:
        errors.append("Domain artifact ID does not match the manifest.")
    watersheds = payload.get("watersheds")
    if not isinstance(watersheds, list) or not watersheds:
        errors.append("Domain artifact must declare at least one watershed.")
        return
    seen: set[str] = set()
    for index, item in enumerate(watersheds, start=1):
        if not isinstance(item, Mapping):
            errors.append(f"Domain watershed {index} must be an object.")
            continue
        watershed_id = _required_text(
            item.get("watershed_id"), f"domain watershed {index} watershed_id", errors
        )
        if watershed_id in seen:
            errors.append(f"Duplicate domain watershed {watershed_id!r}.")
        seen.add(watershed_id)
        area = item.get("area_km2")
        if area is not None:
            value = _finite_number(area, f"domain watershed {index} area_km2", errors)
            if value is not None and value <= 0:
                errors.append(f"Domain watershed {watershed_id!r} area must be positive.")


def _validate_ledger(
    payload: dict[str, object] | None,
    *,
    ledger_id: str,
    domain_id: str,
    errors: list[str],
) -> None:
    if payload is None:
        errors.append("Disturbance-ledger artifact is missing.")
        return
    if payload.get("ledger_id") != ledger_id:
        errors.append("Disturbance-ledger ID does not match the manifest.")
    if payload.get("domain_id") != domain_id:
        errors.append("Disturbance-ledger domain ID does not match the manifest.")
    units = payload.get("units")
    if not isinstance(units, list) or not units:
        errors.append("Disturbance ledger must declare at least one unit.")
        return
    for index, item in enumerate(units, start=1):
        if not isinstance(item, Mapping):
            errors.append(f"Disturbance unit {index} must be an object.")
            continue
        _required_text(item.get("unit_id"), f"disturbance unit {index} unit_id", errors)
        _required_text(item.get("watershed_id"), f"disturbance unit {index} watershed_id", errors)


def _optional_payload(bundle: FemicHydrologyBundle, role: str) -> dict[str, object] | None:
    artifact = bundle.artifacts.get(role)
    if artifact is None:
        return None
    path = (bundle.bundle_dir / artifact.relative_path).resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FemicHydrologyError(f"Unable to read {role} artifact: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise FemicHydrologyError(f"{role} artifact must be a JSON object.")
    return {str(key): value for key, value in payload.items()}


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FemicHydrologyError(f"{field} must be a non-empty string.")
    return value.strip()


def _required_text(value: object, field: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a non-empty string.")
        return ""
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _required_int(value: object, field: str, errors: list[str]) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors.append(f"{field} must be a non-negative integer.")
        return 0
    return value


def _optional_int(value: object, default: int) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


def _finite_number(value: object, field: str, errors: list[str]) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{field} must be a finite number.")
        return None
    number = float(value)
    if not math.isfinite(number):
        errors.append(f"{field} must be a finite number.")
        return None
    return number


def _required_mapping(value: object, field: str, errors: list[str]) -> dict[str, object]:
    if not isinstance(value, Mapping):
        errors.append(f"{field} must be an object.")
        return {}
    return {str(key): item for key, item in value.items()}


def _optional_mapping(value: object, field: str, errors: list[str]) -> dict[str, object]:
    if value is None:
        return {}
    return _required_mapping(value, field, errors)


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise FemicHydrologyError(f"{field} must be an object.")
    return {str(key): item for key, item in value.items()}


def _string_list(value: object, field: str, errors: list[str]) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{field} must be a list of strings.")
        return ()
    return tuple(item.strip() for item in value if item.strip())


def _optional_bool(value: object, field: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise FemicHydrologyError(f"{field} must be boolean.")
    return value


def _return_periods(payload: dict[str, object]) -> tuple[float, ...]:
    periods = payload.get("return_periods")
    if not isinstance(periods, list):
        return ()
    values: list[float] = []
    for item in periods:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            continue
        number = float(item)
        if math.isfinite(number):
            values.append(number)
    return tuple(sorted(values))


def _failure_map(value: object, field: str) -> dict[str, list[str]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise FemicHydrologyError(f"{field} must be an object.")
    result: dict[str, list[str]] = {}
    for key, item in value.items():
        if not isinstance(item, list) or not all(isinstance(entry, str) for entry in item):
            raise FemicHydrologyError(f"{field}.{key} must be a list of strings.")
        result[str(key)] = [entry for entry in item if entry]
    return result


def _fit_map(value: object, field: str) -> dict[str, list[str]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise FemicHydrologyError(f"{field} must be an object.")
    result: dict[str, list[str]] = {}
    for key, item in value.items():
        if not isinstance(item, list) or not all(isinstance(entry, str) for entry in item):
            raise FemicHydrologyError(f"{field}.{key} must be a list of strings.")
        result[str(key)] = [entry for entry in item if entry]
    return result
