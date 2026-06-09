from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .access_times import import_average_access_time_snapshots_xlsx
from .client import fetch_transactions
from .complex_info import import_complex_basic_info_csv, import_complex_property_conditions_csv
from .config import get_service_key
from .db import bootstrap_database, get_mysql_connection
from .db_import import import_transactions_csv
from .db_maintenance import clear_transaction_data, refresh_transaction_derived_snapshots
from .db_training import read_transactions_from_training_view
from .dates import recent_months
from .geocoding import KakaoGeocoder, geocode_missing_complex_coordinates, get_kakao_rest_api_key
from .gui import run_gui_server
from .law_codes import CITY_DISTRICT_CODES, SEOUL_DISTRICT_CODES, city_name_for_city_code, district_codes_for_city
from .modeling import PredictionInput, load_model, predict_price, save_model, train_hedonic_model
from .school_distances import import_school_distance_snapshots_csv
from .subway_distances import import_subway_distance_snapshots_csvs
from .transactions import normalize_property_type, read_transactions_csv, write_transactions_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hedonic-house-price",
        description="Fetch Seoul apartment trades and train a hedonic price regression model.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch Seoul apartment sale transactions.")
    fetch_parser.add_argument("--output", default="data/seoul_apartment_trades.csv")
    fetch_parser.add_argument("--months", type=int, default=24)
    fetch_parser.add_argument("--reference-month", default=None, help="YYYYMM. Defaults to current month.")
    fetch_parser.add_argument("--num-rows", type=int, default=1000)
    fetch_parser.add_argument(
        "--city-codes",
        default="seoul",
        help="Comma-separated: seoul,busan. Defaults to seoul.",
    )
    fetch_parser.add_argument(
        "--property-types",
        default="apartment",
        help="Comma-separated: apartment,officetel,rowhouse. Defaults to apartment.",
    )
    fetch_parser.add_argument(
        "--skip-log-output",
        default=None,
        help="JSONL path for trades excluded during fetch. Defaults to <output stem>.skipped.jsonl.",
    )

    train_parser = subparsers.add_parser("train", help="Train the hedonic regression model.")
    train_parser.add_argument("--input", default="data/seoul_apartment_trades.csv")
    train_parser.add_argument("--model-output", default="artifacts/hedonic_model.pkl")
    train_parser.add_argument("--alpha", type=float, default=1.0)
    train_parser.add_argument("--min-apartment-count", type=int, default=5, help=argparse.SUPPRESS)
    train_parser.add_argument("--validation-months", type=int, default=6)
    train_parser.add_argument("--from-db", action="store_true", help="Train from MySQL model_training_features instead of CSV.")
    train_parser.add_argument("--city-code", choices=["seoul", "busan"], default=None, help="Filter DB training rows by city.")
    train_parser.add_argument(
        "--property-types",
        default=None,
        help="Comma-separated DB training property types. Defaults to all property types.",
    )

    predict_parser = subparsers.add_parser("predict", help="Predict apartment sale price.")
    predict_parser.add_argument("--model", default="artifacts/hedonic_model.pkl")
    predict_parser.add_argument("--district", required=True)
    predict_parser.add_argument("--lawd-cd", required=True)
    predict_parser.add_argument("--deal-year", type=int, required=True)
    predict_parser.add_argument("--deal-month", type=int, required=True)
    predict_parser.add_argument("--deal-day", type=int, default=15)
    predict_parser.add_argument("--legal-dong", required=True)
    predict_parser.add_argument("--apartment-name", default="")
    predict_parser.add_argument("--property-type", default="apartment", choices=["apartment", "officetel", "rowhouse"])
    predict_parser.add_argument("--house-type", default="")
    predict_parser.add_argument("--land-area", type=float, default=None)
    predict_parser.add_argument("--area", type=float, required=True)
    predict_parser.add_argument("--floor", type=int, required=True)
    predict_parser.add_argument("--build-year", type=int, required=True)

    gui_parser = subparsers.add_parser("gui", help="Run the local browser GUI.")
    gui_parser.add_argument("--model", default="artifacts/hedonic_model.pkl")
    gui_parser.add_argument("--host", default="127.0.0.1")
    gui_parser.add_argument("--port", type=int, default=8000)

    db_init_parser = subparsers.add_parser("db-init", help="Create MySQL schema and seed administrative regions.")
    db_init_parser.add_argument("--schema", default="sql/mysql_schema.sql")
    db_init_parser.add_argument("--seed", default="sql/mysql_seed_regions.sql")
    db_init_parser.add_argument("--skip-seed", action="store_true")

    db_import_parser = subparsers.add_parser("db-import-csv", help="Import a transaction CSV into MySQL.")
    db_import_parser.add_argument("--input", required=True)
    db_import_parser.add_argument("--city-code", required=True, choices=["seoul", "busan"])

    db_complex_info_parser = subparsers.add_parser(
        "db-import-complex-info",
        help="Enrich MySQL apartment complexes from a K-apt complex basic info CSV.",
    )
    db_complex_info_parser.add_argument("--input", required=True)
    db_complex_info_parser.add_argument(
        "--reset-addresses",
        action="store_true",
        help="Clear Seoul/Busan apartment complex addresses before applying K-apt enrichment.",
    )
    db_complex_info_parser.add_argument(
        "--accept-remaining-matches",
        action="store_true",
        help="Also accept ambiguous and low-confidence same-dong candidate matches.",
    )

    db_complex_conditions_parser = subparsers.add_parser(
        "db-import-complex-conditions",
        help="Enrich MySQL property condition snapshots from a K-apt complex basic info CSV.",
    )
    db_complex_conditions_parser.add_argument("--input", required=True)
    db_complex_conditions_parser.add_argument(
        "--accept-remaining-matches",
        action="store_true",
        help="Also accept ambiguous and low-confidence same-dong candidate matches.",
    )

    db_geocode_parser = subparsers.add_parser(
        "db-geocode-complexes",
        help="Fill missing apartment complex coordinates by geocoding enriched addresses.",
    )
    db_geocode_parser.add_argument("--provider", choices=["kakao"], default="kakao")
    db_geocode_parser.add_argument("--api-key", default=None, help="Provider API key. Defaults to KAKAO_REST_API_KEY.")
    db_geocode_parser.add_argument("--city-code", choices=["seoul", "busan"], default=None)
    db_geocode_parser.add_argument("--limit", type=int, default=None)
    db_geocode_parser.add_argument("--sleep-seconds", type=float, default=0.1)
    db_geocode_parser.add_argument("--overwrite", action="store_true")

    db_school_parser = subparsers.add_parser(
        "db-import-school-distances",
        help="Fill elementary/middle school distance and school radius-count fields from a school location CSV.",
    )
    db_school_parser.add_argument("--input", required=True)
    db_school_parser.add_argument("--source-name", default="school_location")
    db_school_parser.add_argument("--radius-m", type=int, default=1000)

    db_subway_parser = subparsers.add_parser(
        "db-import-subway-distances",
        help="Fill subway distance and radius-count fields from subway station CSVs.",
    )
    db_subway_parser.add_argument(
        "--input",
        required=True,
        action="append",
        help="Subway station CSV path. Repeat for multiple files.",
    )
    db_subway_parser.add_argument("--source-name", default="transport_access")
    db_subway_parser.add_argument("--radius-m", type=int, default=1000)
    db_subway_parser.add_argument("--provider", choices=["kakao"], default="kakao")
    db_subway_parser.add_argument("--api-key", default=None, help="Provider API key. Defaults to KAKAO_REST_API_KEY.")
    db_subway_parser.add_argument("--sleep-seconds", type=float, default=0.1)

    db_access_time_parser = subparsers.add_parser(
        "db-import-access-times",
        help="Fill average car/transit access time fields from the 2023 access time workbook.",
    )
    db_access_time_parser.add_argument("--input", required=True)
    db_access_time_parser.add_argument("--source-name", default="transport_access")

    subparsers.add_parser("db-clear-data", help="Delete loaded transaction, complex, and factor snapshot data.")
    subparsers.add_parser("db-refresh-derived-snapshots", help="Rebuild transaction-derived factor snapshots.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "fetch":
        return _handle_fetch(args)
    if args.command == "train":
        return _handle_train(args)
    if args.command == "predict":
        return _handle_predict(args)
    if args.command == "gui":
        return _handle_gui(args)
    if args.command == "db-init":
        return _handle_db_init(args)
    if args.command == "db-import-csv":
        return _handle_db_import_csv(args)
    if args.command == "db-import-complex-info":
        return _handle_db_import_complex_info(args)
    if args.command == "db-import-complex-conditions":
        return _handle_db_import_complex_conditions(args)
    if args.command == "db-geocode-complexes":
        return _handle_db_geocode_complexes(args)
    if args.command == "db-import-school-distances":
        return _handle_db_import_school_distances(args)
    if args.command == "db-import-subway-distances":
        return _handle_db_import_subway_distances(args)
    if args.command == "db-import-access-times":
        return _handle_db_import_access_times(args)
    if args.command == "db-clear-data":
        return _handle_db_clear_data(args)
    if args.command == "db-refresh-derived-snapshots":
        return _handle_db_refresh_derived_snapshots(args)
    parser.error(f"unknown command: {args.command}")
    return 2


def _handle_fetch(args: argparse.Namespace) -> int:
    service_key = get_service_key()
    months = recent_months(count=args.months, reference_yyyymm=args.reference_month)
    city_codes = _parse_city_codes(args.city_codes)
    district_codes = _district_codes_for_city_codes(city_codes)
    property_types = _parse_property_types(args.property_types)
    skip_log_path = _resolve_skip_log_path(output_path=args.output, skip_log_output=args.skip_log_output)
    skipped_rows = 0
    skip_log_handle = None

    def skip_logger(record: dict[str, object]) -> None:
        nonlocal skipped_rows, skip_log_handle
        if skip_log_handle is None:
            skip_log_path.parent.mkdir(parents=True, exist_ok=True)
            skip_log_handle = skip_log_path.open("w", encoding="utf-8")
        skipped_rows += 1
        skip_log_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        skip_log_handle.flush()

    try:
        transactions = fetch_transactions(
            service_key=service_key,
            district_codes=district_codes,
            deal_months=months,
            num_rows=args.num_rows,
            property_types=property_types,
            skip_logger=skip_logger,
        )
    finally:
        if skip_log_handle is not None:
            skip_log_handle.close()

    if skipped_rows:
        _print_fetch_progress("제외 거래 기록", rows=skipped_rows, output=skip_log_path)

    if not transactions:
        raise RuntimeError("no transactions were returned for the requested Seoul/month scope")

    write_transactions_csv(transactions, args.output)
    print(
        json.dumps(
            {
                "output": args.output,
                "rows": len(transactions),
                "months": months,
                "city_codes": city_codes,
                "districts": len(district_codes),
                "property_types": property_types,
                "skipped_rows": skipped_rows,
                "skip_log_output": str(skip_log_path) if skipped_rows else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _handle_train(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    if args.from_db:
        _print_train_progress("DB 로드 시작", city_code=args.city_code or "all")
        connection = get_mysql_connection()
        property_types = _parse_property_types(args.property_types) if args.property_types else None
        transactions = read_transactions_from_training_view(
            connection,
            city_code=args.city_code,
            property_types=property_types,
        )
        _print_train_progress("DB 로드 완료", rows=len(transactions), elapsed_s=_elapsed(started))
    else:
        _print_train_progress("CSV 로드 시작", input=args.input)
        transactions = read_transactions_csv(args.input)
        _print_train_progress("CSV 로드 완료", rows=len(transactions), elapsed_s=_elapsed(started))

    model = train_hedonic_model(
        transactions,
        alpha=args.alpha,
        min_apartment_count=args.min_apartment_count,
        validation_months=args.validation_months,
        progress=lambda event: _print_model_progress(event, started),
    )
    _print_train_progress("모델 저장 시작", output=args.model_output, elapsed_s=_elapsed(started))
    save_model(model, args.model_output)
    _print_train_progress("모델 저장 완료", output=args.model_output, elapsed_s=_elapsed(started))

    print(
        json.dumps(
            {
                "model_output": args.model_output,
                "training_rows": model.training_rows,
                "validation_rows": model.validation_rows,
                "metrics": model.metrics,
                "residuals_by_floor_band": model.residuals_by_floor_band,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _print_model_progress(event: dict[str, object], started: float) -> None:
    stage = event["stage"]
    if stage == "sort":
        _print_train_progress("거래 정렬 완료", rows=event["rows"], elapsed_s=_elapsed(started))
    elif stage == "split":
        _print_train_progress(
            "학습/검증 분할 완료",
            training_rows=event["training_rows"],
            validation_rows=event["validation_rows"],
            first_month=event["first_month"],
            elapsed_s=_elapsed(started),
        )
    elif stage == "exclude_apartment_name":
        _print_train_progress("건물명 특성 제외", elapsed_s=_elapsed(started))
    elif stage == "features_train":
        _print_train_progress("특성 생성", dataset="train", rows=event["rows"], elapsed_s=_elapsed(started))
    elif stage == "features_validation":
        _print_train_progress("특성 생성", dataset="validation", rows=event["rows"], elapsed_s=_elapsed(started))
    elif stage == "fit":
        _print_train_progress("sklearn Ridge 학습", training_rows=event["training_rows"], alpha=event["alpha"], elapsed_s=_elapsed(started))
    elif stage == "evaluate":
        _print_train_progress("평가 완료", rows=event["rows"], mape=f"{float(event['mape']):.4f}", r2_log=f"{float(event['r2_log']):.4f}", elapsed_s=_elapsed(started))
    elif stage == "residuals":
        _print_train_progress("층 구간 잔차 계산 완료", rows=event["rows"], floor_bands=event["floor_bands"], elapsed_s=_elapsed(started))
    elif stage == "complete":
        _print_train_progress("학습 완료", training_rows=event["training_rows"], validation_rows=event["validation_rows"], elapsed_s=_elapsed(started))


def _print_train_progress(message: str, **fields: object) -> None:
    suffix = ""
    if fields:
        suffix = " " + " ".join(f"{key}={value}" for key, value in fields.items())
    print(f"[train] {message}{suffix}", file=sys.stderr, flush=True)


def _print_fetch_progress(message: str, **fields: object) -> None:
    suffix = ""
    if fields:
        suffix = " " + " ".join(f"{key}={value}" for key, value in fields.items())
    print(f"[fetch] {message}{suffix}", file=sys.stderr, flush=True)


def _elapsed(started: float) -> str:
    return f"{time.perf_counter() - started:.1f}"


def _handle_predict(args: argparse.Namespace) -> int:
    model = load_model(args.model)
    prediction = predict_price(
        model,
        PredictionInput(
            district=args.district,
            lawd_cd=args.lawd_cd,
            deal_year=args.deal_year,
            deal_month=args.deal_month,
            deal_day=args.deal_day,
            legal_dong=args.legal_dong,
            apartment_name=args.apartment_name,
            property_type=args.property_type,
            house_type=args.house_type,
            land_area_m2=args.land_area,
            exclusive_area_m2=args.area,
            floor=args.floor,
            build_year=args.build_year,
        ),
    )
    print(json.dumps(prediction, ensure_ascii=False, indent=2))
    return 0


def _handle_gui(args: argparse.Namespace) -> int:
    run_gui_server(model_path=args.model, host=args.host, port=args.port)
    return 0


def _handle_db_init(args: argparse.Namespace) -> int:
    connection = get_mysql_connection()
    result = bootstrap_database(
        connection,
        schema_path=args.schema,
        seed_path=args.seed,
        include_seed=not args.skip_seed,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _handle_db_import_csv(args: argparse.Namespace) -> int:
    connection = get_mysql_connection()
    result = import_transactions_csv(
        connection,
        args.input,
        city_code=args.city_code,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _handle_db_import_complex_info(args: argparse.Namespace) -> int:
    connection = get_mysql_connection()
    result = import_complex_basic_info_csv(
        connection,
        args.input,
        reset_addresses=args.reset_addresses,
        accept_remaining_matches=args.accept_remaining_matches,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _handle_db_import_complex_conditions(args: argparse.Namespace) -> int:
    connection = get_mysql_connection()
    result = import_complex_property_conditions_csv(
        connection,
        args.input,
        accept_remaining_matches=args.accept_remaining_matches,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _handle_db_geocode_complexes(args: argparse.Namespace) -> int:
    if args.provider != "kakao":
        raise ValueError(f"unsupported geocoding provider: {args.provider}")
    api_key = args.api_key or get_kakao_rest_api_key()
    geocoder = KakaoGeocoder(api_key)
    connection = get_mysql_connection()
    result = geocode_missing_complex_coordinates(
        connection,
        geocoder,
        city_code=args.city_code,
        limit=args.limit,
        overwrite=args.overwrite,
        sleep_seconds=args.sleep_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _handle_db_import_school_distances(args: argparse.Namespace) -> int:
    connection = get_mysql_connection()
    result = import_school_distance_snapshots_csv(
        connection,
        args.input,
        source_name=args.source_name,
        radius_m=args.radius_m,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _handle_db_import_subway_distances(args: argparse.Namespace) -> int:
    if args.provider != "kakao":
        raise ValueError(f"unsupported geocoding provider: {args.provider}")
    api_key = args.api_key or get_kakao_rest_api_key()
    geocoder = KakaoGeocoder(api_key)
    connection = get_mysql_connection()
    result = import_subway_distance_snapshots_csvs(
        connection,
        args.input,
        geocoder,
        source_name=args.source_name,
        radius_m=args.radius_m,
        sleep_seconds=args.sleep_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _handle_db_import_access_times(args: argparse.Namespace) -> int:
    connection = get_mysql_connection()
    result = import_average_access_time_snapshots_xlsx(
        connection,
        args.input,
        source_name=args.source_name,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _handle_db_clear_data(args: argparse.Namespace) -> int:
    connection = get_mysql_connection()
    result = clear_transaction_data(connection)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _handle_db_refresh_derived_snapshots(args: argparse.Namespace) -> int:
    connection = get_mysql_connection()
    result = refresh_transaction_derived_snapshots(connection)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _parse_city_codes(raw: str) -> list[str]:
    values = [value.strip().lower() for value in raw.split(",") if value.strip()]
    if not values:
        raise ValueError("city-codes must include at least one city code")
    normalized: list[str] = []
    for value in values:
        if value not in CITY_DISTRICT_CODES:
            raise ValueError(f"unsupported city_code: {value}")
        if value not in normalized:
            normalized.append(value)
    return normalized


def _district_codes_for_city_codes(city_codes: list[str]) -> dict[str, str]:
    if len(city_codes) == 1:
        return dict(district_codes_for_city(city_codes[0]))

    combined: dict[str, str] = {}
    for city_code in city_codes:
        city_name = city_name_for_city_code(city_code)
        for district, lawd_cd in district_codes_for_city(city_code).items():
            combined[f"{city_name} {district}"] = lawd_cd
    return combined


def _parse_property_types(raw: str) -> list[str]:
    values = [value.strip() for value in raw.split(",") if value.strip()]
    if not values:
        raise ValueError("property-types must include at least one property type")
    normalized: list[str] = []
    for value in values:
        property_type = normalize_property_type(value)
        if property_type not in normalized:
            normalized.append(property_type)
    return normalized


def _resolve_skip_log_path(output_path: str, skip_log_output: str | None) -> Path:
    if skip_log_output:
        return Path(skip_log_output)
    return Path(output_path).with_suffix(".skipped.jsonl")


if __name__ == "__main__":
    raise SystemExit(main())
