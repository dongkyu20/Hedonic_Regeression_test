from __future__ import annotations

import csv
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .modeling import TrainedModel, save_model


@dataclass(frozen=True)
class RunMetadata:
    data_source: str
    city_code: str | None
    property_types: list[str] | None
    complete_case_only: bool
    validation_months: int
    model_type: str
    hyperparameters: dict[str, float | int | str]
    preprocessing_version: str = "db_preprocessed_v3"
    target: str = "log(price_krw)"


def write_training_run_artifacts(
    model: TrainedModel,
    *,
    output_dir: str | Path,
    metadata: RunMetadata,
    preprocessing_doc_path: str | Path = "docs/model_feature_preprocessing.md",
    git_commit: str | None = None,
) -> dict[str, str]:
    run_dir = Path(output_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    model_path = run_dir / "model.pkl"
    manifest_path = run_dir / "run_manifest.json"
    preprocessing_path = run_dir / "preprocessing.md"
    feature_names_path = run_dir / "feature_names.csv"
    dropped_features_path = run_dir / "dropped_features.json"
    metrics_path = run_dir / "metrics.json"
    residuals_path = run_dir / "residuals_by_floor_band.json"

    save_model(model, model_path)
    _copy_preprocessing_doc(preprocessing_doc_path, preprocessing_path)
    _write_feature_names(model, feature_names_path)
    _write_json(dropped_features_path, {"dropped_features": sorted(getattr(model, "dropped_features", set()))})
    _write_json(
        metrics_path,
        {
            "training_rows": model.training_rows,
            "validation_rows": model.validation_rows,
            **model.metrics,
        },
    )
    _write_json(residuals_path, model.residuals_by_floor_band)

    manifest = _manifest(
        run_dir=run_dir,
        model=model,
        metadata=metadata,
        git_commit=git_commit if git_commit is not None else current_git_commit(),
    )
    _write_json(manifest_path, manifest)

    return {
        "run_output_dir": str(run_dir),
        "run_manifest": str(manifest_path),
        "run_model": str(model_path),
        "feature_names": str(feature_names_path),
        "metrics": str(metrics_path),
    }


def current_git_commit(cwd: str | Path = ".") -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(cwd),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def _manifest(
    *,
    run_dir: Path,
    model: TrainedModel,
    metadata: RunMetadata,
    git_commit: str | None,
) -> dict[str, Any]:
    return {
        "run_id": run_dir.name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": git_commit,
        "data_source": metadata.data_source,
        "city_code": metadata.city_code,
        "property_types": metadata.property_types,
        "complete_case_only": metadata.complete_case_only,
        "training_rows": model.training_rows,
        "validation_rows": model.validation_rows,
        "validation_months": metadata.validation_months,
        "target": metadata.target,
        "preprocessing_version": metadata.preprocessing_version,
        "model_type": metadata.model_type,
        "hyperparameters": metadata.hyperparameters,
        "metrics": model.metrics,
        "artifact_paths": {
            "model": "model.pkl",
            "preprocessing_doc": "preprocessing.md",
            "feature_names": "feature_names.csv",
            "dropped_features": "dropped_features.json",
            "metrics": "metrics.json",
            "residuals_by_floor_band": "residuals_by_floor_band.json",
        },
    }


def _write_feature_names(model: TrainedModel, path: Path) -> None:
    estimator = model.pipeline.estimator
    if estimator is None:
        feature_names: list[str] = []
    else:
        feature_names = list(estimator.named_steps["vectorizer"].feature_names_)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["feature_name"])
        writer.writeheader()
        for feature_name in feature_names:
            writer.writerow({"feature_name": feature_name})


def _copy_preprocessing_doc(source: str | Path, destination: Path) -> None:
    source_path = Path(source)
    if source_path.exists():
        shutil.copyfile(source_path, destination)
        return
    destination.write_text("# Model Feature Preprocessing\n\nSource preprocessing document was not found.\n", encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
