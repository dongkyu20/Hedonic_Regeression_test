import csv
import json
import tempfile
import unittest
from pathlib import Path

from hedonic_house_price.modeling import load_model, train_hedonic_model
from hedonic_house_price.training_runs import RunMetadata, write_training_run_artifacts
from hedonic_house_price.transactions import Transaction


def sample_transactions():
    rows = []
    for idx in range(8):
        rows.append(
            Transaction(
                district="강남구",
                lawd_cd="11680",
                deal_year=2025,
                deal_month=idx + 1,
                deal_day=10,
                legal_dong="역삼동",
                building_name="테스트단지",
                exclusive_area_m2=59.8 if idx % 2 == 0 else 84.9,
                floor=[2, 6, 10, 15][idx % 4],
                build_year=2000 + idx,
                price_manwon=80_000 + idx * 2_000,
            )
        )
    return rows


class TrainingRunsTests(unittest.TestCase):
    def test_write_training_run_artifacts_records_manifest_model_and_features(self):
        model = train_hedonic_model(
            sample_transactions(),
            n_estimators=10,
            random_state=42,
            n_jobs=1,
            validation_months=2,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            preprocessing_doc = Path(tmpdir) / "preprocessing.md"
            preprocessing_doc.write_text("# 전처리\n", encoding="utf-8")
            result = write_training_run_artifacts(
                model,
                output_dir=Path(tmpdir) / "run",
                metadata=RunMetadata(
                    data_source="mysql.model_training_features",
                    city_code=None,
                    property_types=["apartment"],
                    complete_case_only=True,
                    validation_months=2,
                    model_type="RandomForest",
                    hyperparameters={
                        "n_estimators": 10,
                        "max_depth": 24,
                        "min_samples_leaf": 5,
                        "random_state": 42,
                        "n_jobs": 1,
                    },
                ),
                preprocessing_doc_path=preprocessing_doc,
                git_commit="abc123",
            )

            run_dir = Path(result["run_output_dir"])
            manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
            metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
            dropped = json.loads((run_dir / "dropped_features.json").read_text(encoding="utf-8"))
            with (run_dir / "feature_names.csv").open(encoding="utf-8") as handle:
                feature_rows = list(csv.DictReader(handle))

            self.assertEqual(manifest["run_id"], "run")
            self.assertEqual(manifest["git_commit"], "abc123")
            self.assertEqual(manifest["data_source"], "mysql.model_training_features")
            self.assertEqual(manifest["property_types"], ["apartment"])
            self.assertTrue(manifest["complete_case_only"])
            self.assertEqual(manifest["model_type"], "RandomForest")
            self.assertEqual(manifest["hyperparameters"]["n_estimators"], 10)
            self.assertEqual(manifest["hyperparameters"]["min_samples_leaf"], 5)
            self.assertEqual(manifest["artifact_paths"]["model"], "model.pkl")
            self.assertIn("mape", metrics)
            self.assertIsInstance(dropped["dropped_features"], list)
            self.assertTrue(any(row["feature_name"] == "log_area_m2" for row in feature_rows))
            self.assertEqual((run_dir / "preprocessing.md").read_text(encoding="utf-8"), "# 전처리\n")
            self.assertEqual(load_model(run_dir / "model.pkl").training_rows, model.training_rows)


if __name__ == "__main__":
    unittest.main()
