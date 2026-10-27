"""Register FEMIC hydrology response bundles in a FHOPS scenario.

Registration validates the bundle and readiness evidence, records a stable pin
with artifact checksums, and writes the pin to the scenario only after the
loader accepts the result. The bundle is referenced, never copied.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError

from fhops.scenario.contract.hydrology import (
    HydrologyArtifactPin,
    HydrologyBundleRef,
    HydrologyReadinessStatus,
)
from fhops.scenario.hydrology import (
    FemicHydrologyBundle,
    FemicHydrologyError,
    assess_femic_hydrology_readiness,
    load_femic_hydrology_bundle,
)
from fhops.scenario.io import load_scenario

__all__ = [
    "FemicHydrologyRegistrationError",
    "RegistrationResult",
    "register_femic_hydrology_bundle",
]


class FemicHydrologyRegistrationError(RuntimeError):
    """A hydrology bundle cannot be bound to a scenario or written safely."""


@dataclass(frozen=True)
class RegistrationResult:
    """Outcome of a hydrology bundle registration.

    Attributes
    ----------
    scenario_path : Path
        Scenario YAML that owns the pin.
    bundle_id : str
        Registered FEMIC bundle identifier.
    bundle_version : str
        Registered FEMIC bundle version.
    manifest_sha256 : str
        Manifest digest recorded in the pin.
    manifest_path : str
        Manifest path recorded in the pin, relative when possible.
    readiness_status : str
        Producer readiness state at registration time.
    warnings : tuple[str, ...]
        Registration and readiness warnings.
    written : bool
        False for a dry run.
    pin : HydrologyBundleRef
        Pin that was written or would be written.
    """

    scenario_path: Path
    bundle_id: str
    bundle_version: str
    manifest_sha256: str
    manifest_path: str
    readiness_status: str
    warnings: tuple[str, ...]
    written: bool
    pin: HydrologyBundleRef

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready registration summary.

        Returns
        -------
        dict[str, object]
            Scenario, bundle, readiness, warnings, and pin fields.
        """
        return {
            "scenario_path": str(self.scenario_path),
            "bundle_id": self.bundle_id,
            "bundle_version": self.bundle_version,
            "manifest_sha256": self.manifest_sha256,
            "manifest_path": self.manifest_path,
            "readiness_status": self.readiness_status,
            "warnings": list(self.warnings),
            "written": self.written,
            "pin": self.pin.model_dump(mode="json", exclude_none=True),
        }


def register_femic_hydrology_bundle(
    scenario_path: str | Path,
    bundle_dir: str | Path,
    *,
    expected_bundle_id: str | None = None,
    expected_bundle_version: str | None = None,
    verify_checksums: bool = True,
    dry_run: bool = False,
) -> RegistrationResult:
    """Validate a hydrology bundle and pin it in a scenario.

    Parameters
    ----------
    scenario_path : str | Path
        Scenario YAML to update.
    bundle_dir : str | Path
        FEMIC hydrology bundle directory or manifest path.
    expected_bundle_id : str | None, optional
        Require this bundle identifier.
    expected_bundle_version : str | None, optional
        Require this bundle version.
    verify_checksums : bool, optional
        Verify artifact sizes and SHA-256 digests. Defaults to True.
    dry_run : bool, optional
        Validate and return the pin without writing the scenario.

    Returns
    -------
    RegistrationResult
        Stable pin, readiness state, warnings, and whether the scenario changed.

    Raises
    ------
    FemicHydrologyRegistrationError
        If the bundle or scenario cannot be loaded, the existing pin conflicts,
        or the updated scenario does not reload.
    """
    scenario = Path(scenario_path).expanduser().resolve()
    bundle_path = Path(bundle_dir).expanduser().resolve()
    try:
        loaded = load_scenario(scenario)
        bundle = load_femic_hydrology_bundle(
            bundle_path,
            expected_bundle_id=expected_bundle_id,
            expected_bundle_version=expected_bundle_version,
            verify_checksums=verify_checksums,
        )
        readiness = assess_femic_hydrology_readiness(bundle)
    except (FemicHydrologyError, ValueError, FileNotFoundError) as exc:
        raise FemicHydrologyRegistrationError(_format_error(exc)) from exc
    manifest_path = _relative_manifest_path(scenario, bundle.manifest_path)
    evidence_digest = hashlib.sha256(
        json.dumps(readiness.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    pin = HydrologyBundleRef(
        bundle_id=bundle.bundle_id,
        bundle_version=bundle.bundle_version,
        manifest_sha256=bundle.manifest_sha256,
        domain_id=bundle.domain_id,
        ledger_id=bundle.ledger_id,
        response_surface_id=bundle.response_surface_id,
        manifest_path=manifest_path,
        readiness_status=cast(HydrologyReadinessStatus, readiness.status),
        readiness_evidence_sha256=evidence_digest,
        artifacts=_artifact_pins(bundle),
        caveats=list(bundle.caveats),
        consumer_contract=bundle.consumer_contract,
    )
    existing = list(loaded.hydrology_products or [])
    for current in existing:
        if (current.bundle_id, current.bundle_version) == (pin.bundle_id, pin.bundle_version):
            if current.manifest_sha256 != pin.manifest_sha256:
                raise FemicHydrologyRegistrationError(
                    f"Bundle {pin.bundle_id}@{pin.bundle_version} is already pinned with a "
                    "different manifest checksum."
                )
            existing.remove(current)
            break
    pins = [*existing, pin]
    text = _replace_top_level_section(
        scenario.read_text(encoding="utf-8"),
        "hydrology_products",
        [item.model_dump(mode="json", exclude_none=True) for item in pins],
    )
    if not dry_run:
        _validate_and_replace(scenario, text)
    return RegistrationResult(
        scenario_path=scenario,
        bundle_id=bundle.bundle_id,
        bundle_version=bundle.bundle_version,
        manifest_sha256=bundle.manifest_sha256,
        manifest_path=manifest_path,
        readiness_status=readiness.status,
        warnings=readiness.warnings,
        written=not dry_run,
        pin=pin,
    )


def _artifact_pins(bundle: FemicHydrologyBundle) -> list[HydrologyArtifactPin]:
    return [
        HydrologyArtifactPin(
            role=role,
            relative_path=artifact.relative_path,
            schema_version=artifact.schema_version,
            media_type=artifact.media_type,
            size_bytes=artifact.size_bytes,
            sha256=artifact.sha256,
        )
        for role, artifact in sorted(bundle.artifacts.items())
    ]


def _relative_manifest_path(scenario: Path, manifest: Path) -> str:
    try:
        return str(manifest.relative_to(scenario.parent))
    except ValueError:
        return str(manifest)


def _replace_top_level_section(text: str, key: str, value: Any) -> str:
    lines = text.splitlines()
    pattern = re.compile(rf"^{re.escape(key)}\s*:")
    start = next((index for index, line in enumerate(lines) if pattern.match(line)), None)
    rendered = (
        yaml.safe_dump({key: value}, sort_keys=False, allow_unicode=True, default_flow_style=False)
        .rstrip("\n")
        .splitlines()
    )
    if start is None:
        prefix = text.rstrip("\n")
        return (prefix + "\n\n" if prefix else "") + "\n".join(rendered) + "\n"
    end = start + 1
    while end < len(lines):
        line = lines[end]
        stripped = line.strip()
        if not stripped:
            end += 1
            continue
        if line[0] in " \t" or stripped.startswith("-"):
            end += 1
            continue
        break
    return "\n".join(lines[:start] + rendered + [""] + lines[end:]).rstrip("\n") + "\n"


def _validate_and_replace(path: Path, text: str) -> None:
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=".fhops-hydrology-",
        suffix=path.suffix,
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(text)
        load_scenario(temp_path)
        os.chmod(temp_path, path.stat().st_mode)
        os.replace(temp_path, path)
    except Exception as exc:  # noqa: BLE001 - the loader message is the user-facing result
        temp_path.unlink(missing_ok=True)
        raise FemicHydrologyRegistrationError(_format_error(exc)) from exc


def _format_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts = []
        for error in exc.errors():
            location = ".".join(str(item) for item in error.get("loc", ()))
            parts.append(f"{location}: {error.get('msg', 'invalid value')}")
        return "; ".join(parts) or str(exc)
    return f"{type(exc).__name__}: {exc}"
