import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from hedonic_house_price.cli import build_parser, main
from hedonic_house_price.transactions import Transaction, write_transactions_csv


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
                building_name="반복단지",
                exclusive_area_m2=84.9,
                floor=[2, 6, 10, 15][idx % 4],
                build_year=2008,
                price_manwon=90_000 + idx * 1_000,
            )
        )
    return rows


class CliTests(unittest.TestCase):
    def test_fetch_command_parses_default_seoul_collection_options(self):
        args = build_parser().parse_args(["fetch", "--months", "24", "--reference-month", "202606"])

        self.assertEqual(args.command, "fetch")
        self.assertEqual(args.months, 24)
        self.assertEqual(args.reference_month, "202606")
        self.assertEqual(args.output, "data/seoul_apartment_trades.csv")
        self.assertEqual(args.property_types, "apartment")

    def test_fetch_command_parses_non_apartment_collection_options(self):
        args = build_parser().parse_args(
            [
                "fetch",
                "--months",
                "24",
                "--property-types",
                "apartment,officetel,rowhouse",
                "--output",
                "data/seoul_housing_trades.csv",
            ]
        )

        self.assertEqual(args.property_types, "apartment,officetel,rowhouse")
        self.assertEqual(args.output, "data/seoul_housing_trades.csv")

    def test_train_command_parses_model_options(self):
        args = build_parser().parse_args(
            [
                "train",
                "--input",
                "data/input.csv",
                "--model-output",
                "artifacts/model.json",
                "--alpha",
                "0.25",
            ]
        )

        self.assertEqual(args.command, "train")
        self.assertEqual(args.input, "data/input.csv")
        self.assertEqual(args.model_output, "artifacts/model.json")
        self.assertEqual(args.alpha, 0.25)

    def test_train_command_defaults_to_pickle_model_artifact(self):
        args = build_parser().parse_args(["train"])

        self.assertEqual(args.model_output, "artifacts/hedonic_model.pkl")

    def test_gui_command_parses_local_server_options(self):
        args = build_parser().parse_args(["gui", "--model", "artifacts/model.pkl", "--port", "8123"])

        self.assertEqual(args.command, "gui")
        self.assertEqual(args.model, "artifacts/model.pkl")
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 8123)

    def test_train_command_prints_realtime_progress_to_stderr(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as csv_file:
            input_path = csv_file.name
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as model_file:
            model_path = model_file.name

        stderr = io.StringIO()
        stdout = io.StringIO()
        try:
            write_transactions_csv(sample_transactions(), input_path)
            with redirect_stderr(stderr), redirect_stdout(stdout):
                exit_code = main(
                    [
                        "train",
                        "--input",
                        input_path,
                        "--model-output",
                        model_path,
                        "--alpha",
                        "0.1",
                        "--min-apartment-count",
                        "2",
                        "--validation-months",
                        "2",
                    ]
                )

            self.assertEqual(exit_code, 0)
            progress_text = stderr.getvalue()
            self.assertIn("[train] CSV 로드 시작", progress_text)
            self.assertIn("[train] 특성 생성", progress_text)
            self.assertIn("[train] sklearn Ridge 학습", progress_text)
            self.assertIn("[train] 모델 저장 완료", progress_text)
            self.assertIn('"model_output"', stdout.getvalue())
        finally:
            os.unlink(input_path)
            os.unlink(model_path)

    def test_fetch_command_writes_skipped_trade_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "seoul_officetel_trades.csv"
            expected_log_path = Path(tmpdir) / "seoul_officetel_trades.skipped.jsonl"

            def fake_fetch_transactions(**kwargs):
                skip_logger = kwargs["skip_logger"]
                skip_logger(
                    {
                        "reason": "missing_build_year",
                        "property_type": "officetel",
                        "district": "송파구",
                        "lawd_cd": "11710",
                        "deal_ymd": "202505",
                        "legal_dong": "문정동",
                        "building_name": "건축년도없는오피스텔",
                        "exclusive_area_m2": "42.4",
                        "floor": "12",
                        "price_manwon": "55,000",
                    }
                )
                return sample_transactions()[:1]

            stderr = io.StringIO()
            stdout = io.StringIO()
            with (
                patch("hedonic_house_price.cli.get_service_key", return_value="service-key"),
                patch("hedonic_house_price.cli.recent_months", return_value=["202505"]),
                patch("hedonic_house_price.cli.fetch_transactions", side_effect=fake_fetch_transactions),
                redirect_stderr(stderr),
                redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "fetch",
                        "--property-types",
                        "officetel",
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(expected_log_path.exists())
            record = json.loads(expected_log_path.read_text(encoding="utf-8").strip())
            self.assertEqual(record["reason"], "missing_build_year")
            self.assertEqual(record["building_name"], "건축년도없는오피스텔")
            self.assertIn("skipped_rows", stdout.getvalue())
            self.assertIn("[fetch] 제외 거래 기록", stderr.getvalue())

    def test_predict_command_parses_required_property_fields(self):
        args = build_parser().parse_args(
            [
                "predict",
                "--model",
                "artifacts/model.json",
                "--district",
                "강남구",
                "--lawd-cd",
                "11680",
                "--deal-year",
                "2026",
                "--deal-month",
                "6",
                "--legal-dong",
                "역삼동",
                "--area",
                "84.95",
                "--floor",
                "15",
                "--build-year",
                "2005",
            ]
        )

        self.assertEqual(args.command, "predict")
        self.assertEqual(args.district, "강남구")
        self.assertEqual(args.area, 84.95)
        self.assertEqual(args.floor, 15)
        self.assertEqual(args.deal_day, 15)
        self.assertEqual(args.property_type, "apartment")
        self.assertEqual(args.apartment_name, "")


if __name__ == "__main__":
    unittest.main()
