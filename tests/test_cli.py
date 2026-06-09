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

    def test_fetch_command_parses_city_collection_options(self):
        args = build_parser().parse_args(
            [
                "fetch",
                "--city-codes",
                "seoul,busan",
                "--property-types",
                "apartment",
                "--output",
                "data/seoul_busan_apartment_trades.csv",
            ]
        )

        self.assertEqual(args.city_codes, "seoul,busan")
        self.assertEqual(args.property_types, "apartment")
        self.assertEqual(args.output, "data/seoul_busan_apartment_trades.csv")

    def test_fetch_command_uses_selected_city_districts(self):
        stdout = io.StringIO()
        with (
            patch("hedonic_house_price.cli.get_service_key", return_value="service-key"),
            patch("hedonic_house_price.cli.recent_months", return_value=["202505"]),
            patch("hedonic_house_price.cli.fetch_transactions", return_value=sample_transactions()) as fetch_mock,
            redirect_stdout(stdout),
        ):
            exit_code = main(
                [
                    "fetch",
                    "--city-codes",
                    "seoul,busan",
                    "--property-types",
                    "apartment",
                    "--output",
                    "/tmp/seoul_busan_apartment.csv",
                ]
            )

        self.assertEqual(exit_code, 0)
        call_kwargs = fetch_mock.call_args.kwargs
        self.assertEqual(call_kwargs["property_types"], ["apartment"])
        self.assertEqual(len(call_kwargs["district_codes"]), 41)
        self.assertEqual(call_kwargs["district_codes"]["서울특별시 강남구"], "11680")
        self.assertEqual(call_kwargs["district_codes"]["부산광역시 해운대구"], "26350")
        self.assertIn('"city_codes"', stdout.getvalue())

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

    def test_db_init_command_parses_schema_and_seed_options(self):
        args = build_parser().parse_args(
            [
                "db-init",
                "--schema",
                "sql/mysql_schema.sql",
                "--seed",
                "sql/mysql_seed_regions.sql",
                "--skip-seed",
            ]
        )

        self.assertEqual(args.command, "db-init")
        self.assertEqual(args.schema, "sql/mysql_schema.sql")
        self.assertEqual(args.seed, "sql/mysql_seed_regions.sql")
        self.assertTrue(args.skip_seed)

    def test_db_import_csv_command_parses_city_and_input(self):
        args = build_parser().parse_args(
            [
                "db-import-csv",
                "--input",
                "data/seoul_apartment_trades.csv",
                "--city-code",
                "seoul",
            ]
        )

        self.assertEqual(args.command, "db-import-csv")
        self.assertEqual(args.input, "data/seoul_apartment_trades.csv")
        self.assertEqual(args.city_code, "seoul")

    def test_db_import_complex_info_command_parses_input(self):
        args = build_parser().parse_args(
            [
                "db-import-complex-info",
                "--input",
                "data/complex_basic_info.csv",
                "--reset-addresses",
                "--accept-remaining-matches",
            ]
        )

        self.assertEqual(args.command, "db-import-complex-info")
        self.assertEqual(args.input, "data/complex_basic_info.csv")
        self.assertTrue(args.reset_addresses)
        self.assertTrue(args.accept_remaining_matches)

    def test_db_import_complex_conditions_command_parses_input(self):
        args = build_parser().parse_args(
            [
                "db-import-complex-conditions",
                "--input",
                "data/complex_basic_info.csv",
                "--accept-remaining-matches",
            ]
        )

        self.assertEqual(args.command, "db-import-complex-conditions")
        self.assertEqual(args.input, "data/complex_basic_info.csv")
        self.assertTrue(args.accept_remaining_matches)

    def test_db_geocode_complexes_command_parses_options(self):
        args = build_parser().parse_args(
            [
                "db-geocode-complexes",
                "--provider",
                "kakao",
                "--city-code",
                "seoul",
                "--limit",
                "100",
                "--sleep-seconds",
                "0.05",
                "--overwrite",
            ]
        )

        self.assertEqual(args.command, "db-geocode-complexes")
        self.assertEqual(args.provider, "kakao")
        self.assertEqual(args.city_code, "seoul")
        self.assertEqual(args.limit, 100)
        self.assertEqual(args.sleep_seconds, 0.05)
        self.assertTrue(args.overwrite)

    def test_db_clear_data_command_parses(self):
        args = build_parser().parse_args(["db-clear-data"])

        self.assertEqual(args.command, "db-clear-data")

    def test_db_refresh_derived_snapshots_command_parses(self):
        args = build_parser().parse_args(["db-refresh-derived-snapshots"])

        self.assertEqual(args.command, "db-refresh-derived-snapshots")

    def test_train_command_parses_db_training_options(self):
        args = build_parser().parse_args(
            [
                "train",
                "--from-db",
                "--city-code",
                "busan",
                "--property-types",
                "apartment,rowhouse",
            ]
        )

        self.assertTrue(args.from_db)
        self.assertEqual(args.city_code, "busan")
        self.assertEqual(args.property_types, "apartment,rowhouse")

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

    def test_train_from_db_uses_training_view_reader(self):
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as model_file:
            model_path = model_file.name

        stderr = io.StringIO()
        stdout = io.StringIO()
        try:
            with (
                patch("hedonic_house_price.cli.get_mysql_connection", return_value=object()),
                patch("hedonic_house_price.cli.read_transactions_from_training_view", return_value=sample_transactions()),
                redirect_stderr(stderr),
                redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "train",
                        "--from-db",
                        "--city-code",
                        "seoul",
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
            self.assertIn("[train] DB 로드 시작", stderr.getvalue())
            self.assertIn("[train] DB 로드 완료", stderr.getvalue())
            self.assertIn('"model_output"', stdout.getvalue())
        finally:
            os.unlink(model_path)

    def test_db_clear_data_uses_maintenance_helper(self):
        stdout = io.StringIO()
        with (
            patch("hedonic_house_price.cli.get_mysql_connection", return_value=object()),
            patch("hedonic_house_price.cli.clear_transaction_data", return_value={"cleared_tables": 6}),
            redirect_stdout(stdout),
        ):
            exit_code = main(["db-clear-data"])

        self.assertEqual(exit_code, 0)
        self.assertIn('"cleared_tables": 6', stdout.getvalue())

    def test_db_refresh_derived_snapshots_uses_maintenance_helper(self):
        stdout = io.StringIO()
        with (
            patch("hedonic_house_price.cli.get_mysql_connection", return_value=object()),
            patch(
                "hedonic_house_price.cli.refresh_transaction_derived_snapshots",
                return_value={"property_condition_rows": 10, "urban_competitiveness_rows": 2},
            ),
            redirect_stdout(stdout),
        ):
            exit_code = main(["db-refresh-derived-snapshots"])

        self.assertEqual(exit_code, 0)
        self.assertIn('"property_condition_rows": 10', stdout.getvalue())

    def test_db_import_complex_info_uses_import_helper(self):
        stdout = io.StringIO()
        with (
            patch("hedonic_house_price.cli.get_mysql_connection", return_value=object()),
            patch(
                "hedonic_house_price.cli.import_complex_basic_info_csv",
                return_value={"matched_complexes": 3, "updated_complexes": 2},
            ) as import_mock,
            redirect_stdout(stdout),
        ):
            exit_code = main(
                [
                    "db-import-complex-info",
                    "--input",
                    "data/complex_basic_info.csv",
                    "--reset-addresses",
                    "--accept-remaining-matches",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertTrue(import_mock.call_args.kwargs["reset_addresses"])
        self.assertTrue(import_mock.call_args.kwargs["accept_remaining_matches"])
        self.assertIn('"matched_complexes": 3', stdout.getvalue())

    def test_db_import_complex_conditions_uses_import_helper(self):
        stdout = io.StringIO()
        with (
            patch("hedonic_house_price.cli.get_mysql_connection", return_value=object()),
            patch(
                "hedonic_house_price.cli.import_complex_property_conditions_csv",
                return_value={"matched_complexes": 3, "snapshot_rows": 20},
            ) as import_mock,
            redirect_stdout(stdout),
        ):
            exit_code = main(
                [
                    "db-import-complex-conditions",
                    "--input",
                    "data/complex_basic_info.csv",
                    "--accept-remaining-matches",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertTrue(import_mock.call_args.kwargs["accept_remaining_matches"])
        self.assertIn('"snapshot_rows": 20', stdout.getvalue())

    def test_db_geocode_complexes_uses_kakao_geocoder(self):
        stdout = io.StringIO()
        with (
            patch("hedonic_house_price.cli.get_mysql_connection", return_value=object()),
            patch("hedonic_house_price.cli.KakaoGeocoder") as geocoder_cls,
            patch("hedonic_house_price.cli.get_kakao_rest_api_key", return_value="kakao-key"),
            patch(
                "hedonic_house_price.cli.geocode_missing_complex_coordinates",
                return_value={"updated_complexes": 7},
            ) as geocode_mock,
            redirect_stdout(stdout),
        ):
            exit_code = main(
                [
                    "db-geocode-complexes",
                    "--city-code",
                    "busan",
                    "--limit",
                    "10",
                    "--sleep-seconds",
                    "0",
                ]
            )

        self.assertEqual(exit_code, 0)
        geocoder_cls.assert_called_once_with("kakao-key")
        self.assertEqual(geocode_mock.call_args.kwargs["city_code"], "busan")
        self.assertEqual(geocode_mock.call_args.kwargs["limit"], 10)
        self.assertIn('"updated_complexes": 7', stdout.getvalue())

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
