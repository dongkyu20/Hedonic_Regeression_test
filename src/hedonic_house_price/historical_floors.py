from __future__ import annotations

import csv
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .client import fetch_transactions_for_month
from .law_codes import district_codes_for_city
from .transactions import Transaction


HistoricalFloorKey = tuple[str, str, str, str]
ProgressCallback = Callable[[dict[str, object]], None]
MonthlyFetcher = Callable[..., list[Transaction]]
FetchTask = tuple[str, str, str, str]

CSV_FIELDS = [
    "city_code",
    "property_type",
    "district",
    "lawd_cd",
    "legal_dong",
    "building_name",
    "observed_max_floor",
    "estimated_max_floor_rounded_4",
    "observation_count",
    "first_observed_yyyymm",
    "last_observed_yyyymm",
    "min_build_year",
    "max_build_year",
    "confidence",
]


@dataclass(frozen=True)
class HistoricalFloorStat:
    city_code: str
    property_type: str
    district: str
    lawd_cd: str
    legal_dong: str
    building_name: str
    observed_max_floor: int
    estimated_max_floor_rounded_4: int
    observation_count: int
    first_observed_yyyymm: str
    last_observed_yyyymm: str
    min_build_year: int
    max_build_year: int
    confidence: str

    @property
    def key(self) -> HistoricalFloorKey:
        return (
            self.property_type,
            self.lawd_cd,
            self.legal_dong,
            self.building_name,
        )

    def to_row(self) -> dict[str, str]:
        return {
            "city_code": self.city_code,
            "property_type": self.property_type,
            "district": self.district,
            "lawd_cd": self.lawd_cd,
            "legal_dong": self.legal_dong,
            "building_name": self.building_name,
            "observed_max_floor": str(self.observed_max_floor),
            "estimated_max_floor_rounded_4": str(self.estimated_max_floor_rounded_4),
            "observation_count": str(self.observation_count),
            "first_observed_yyyymm": self.first_observed_yyyymm,
            "last_observed_yyyymm": self.last_observed_yyyymm,
            "min_build_year": str(self.min_build_year),
            "max_build_year": str(self.max_build_year),
            "confidence": self.confidence,
        }


@dataclass
class _MutableFloorStat:
    city_code: str
    property_type: str
    district: str
    lawd_cd: str
    legal_dong: str
    building_name: str
    observed_max_floor: int
    observation_count: int
    first_observed_yyyymm: str
    last_observed_yyyymm: str
    min_build_year: int
    max_build_year: int

    def update(self, transaction: Transaction) -> None:
        self.observed_max_floor = max(self.observed_max_floor, transaction.floor)
        self.observation_count += 1
        self.first_observed_yyyymm = min(self.first_observed_yyyymm, transaction.deal_yyyymm)
        self.last_observed_yyyymm = max(self.last_observed_yyyymm, transaction.deal_yyyymm)
        self.min_build_year = min(self.min_build_year, transaction.build_year)
        self.max_build_year = max(self.max_build_year, transaction.build_year)

    def freeze(self) -> HistoricalFloorStat:
        return HistoricalFloorStat(
            city_code=self.city_code,
            property_type=self.property_type,
            district=self.district,
            lawd_cd=self.lawd_cd,
            legal_dong=self.legal_dong,
            building_name=self.building_name,
            observed_max_floor=self.observed_max_floor,
            estimated_max_floor_rounded_4=round_up_to_floor_step(self.observed_max_floor),
            observation_count=self.observation_count,
            first_observed_yyyymm=self.first_observed_yyyymm,
            last_observed_yyyymm=self.last_observed_yyyymm,
            min_build_year=self.min_build_year,
            max_build_year=self.max_build_year,
            confidence=floor_confidence(self.observation_count),
        )


def historical_months(start_month: str, end_month: str) -> list[str]:
    start_year, start_month_number = _split_yyyymm(start_month)
    end_year, end_month_number = _split_yyyymm(end_month)
    start_index = start_year * 12 + start_month_number - 1
    end_index = end_year * 12 + end_month_number - 1
    if start_index > end_index:
        raise ValueError("start_month must be earlier than or equal to end_month")

    months: list[str] = []
    for index in range(start_index, end_index + 1):
        year = index // 12
        month = index % 12 + 1
        months.append(f"{year:04d}{month:02d}")
    return months


def build_historical_floor_stats(transactions: list[Transaction]) -> dict[HistoricalFloorKey, HistoricalFloorStat]:
    mutable_stats: dict[HistoricalFloorKey, _MutableFloorStat] = {}
    for transaction in transactions:
        update_historical_floor_stats(mutable_stats, transaction)
    return {
        key: stat.freeze()
        for key, stat in sorted(mutable_stats.items())
    }


def update_historical_floor_stats(
    stats: dict[HistoricalFloorKey, _MutableFloorStat],
    transaction: Transaction,
    *,
    city_code: str | None = None,
) -> None:
    key = _floor_key(transaction)
    existing = stats.get(key)
    if existing is None:
        stats[key] = _MutableFloorStat(
            city_code=_city_code(transaction, city_code),
            property_type=transaction.property_type,
            district=transaction.district,
            lawd_cd=transaction.lawd_cd,
            legal_dong=transaction.legal_dong,
            building_name=transaction.building_name,
            observed_max_floor=transaction.floor,
            observation_count=1,
            first_observed_yyyymm=transaction.deal_yyyymm,
            last_observed_yyyymm=transaction.deal_yyyymm,
            min_build_year=transaction.build_year,
            max_build_year=transaction.build_year,
        )
        return
    existing.update(transaction)


def freeze_historical_floor_stats(stats: dict[HistoricalFloorKey, _MutableFloorStat]) -> list[HistoricalFloorStat]:
    return [
        stat.freeze()
        for _, stat in sorted(stats.items())
    ]


def write_historical_floor_stats_csv(stats: list[HistoricalFloorStat], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for stat in stats:
            writer.writerow(stat.to_row())


def fetch_historical_floor_stats(
    *,
    service_key: str,
    city_codes: list[str],
    start_month: str,
    end_month: str,
    num_rows: int = 1000,
    sleep_seconds: float = 0.0,
    max_retries: int = 2,
    retry_backoff_seconds: float = 30.0,
    workers: int = 1,
    progress: ProgressCallback | None = None,
    fetcher: MonthlyFetcher = fetch_transactions_for_month,
) -> list[HistoricalFloorStat]:
    months = historical_months(start_month, end_month)
    stats: dict[HistoricalFloorKey, _MutableFloorStat] = {}
    request_count = 0
    transaction_count = 0
    tasks = _fetch_tasks(city_codes, months)
    worker_count = max(1, int(workers))

    if worker_count == 1:
        for task in tasks:
            city_code, district, lawd_cd, deal_month = task
            transactions = _fetch_task(
                task,
                fetcher=fetcher,
                service_key=service_key,
                num_rows=num_rows,
                max_retries=max_retries,
                sleep_seconds=sleep_seconds,
                retry_backoff_seconds=retry_backoff_seconds,
            )
            request_count, transaction_count = _record_fetch_result(
                stats,
                transactions,
                city_code=city_code,
                district=district,
                lawd_cd=lawd_cd,
                deal_month=deal_month,
                request_count=request_count,
                transaction_count=transaction_count,
                progress=progress,
            )
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_task = {
                executor.submit(
                    _fetch_task,
                    task,
                    fetcher=fetcher,
                    service_key=service_key,
                    num_rows=num_rows,
                    max_retries=max_retries,
                    sleep_seconds=sleep_seconds,
                    retry_backoff_seconds=retry_backoff_seconds,
                ): task
                for task in tasks
            }
            for future in as_completed(future_to_task):
                city_code, district, lawd_cd, deal_month = future_to_task[future]
                transactions = future.result()
                request_count, transaction_count = _record_fetch_result(
                    stats,
                    transactions,
                    city_code=city_code,
                    district=district,
                    lawd_cd=lawd_cd,
                    deal_month=deal_month,
                    request_count=request_count,
                    transaction_count=transaction_count,
                    progress=progress,
                )

    frozen_stats = freeze_historical_floor_stats(stats)
    if progress is not None:
        progress(
            {
                "stage": "complete",
                "requests": request_count,
                "transactions": transaction_count,
                "complexes": len(frozen_stats),
                "months": len(months),
            }
        )
    return frozen_stats


def _fetch_tasks(city_codes: list[str], months: list[str]) -> list[FetchTask]:
    return [
        (city_code, district, lawd_cd, deal_month)
        for city_code in city_codes
        for district, lawd_cd in district_codes_for_city(city_code).items()
        for deal_month in months
    ]


def _fetch_task(
    task: FetchTask,
    *,
    fetcher: MonthlyFetcher,
    service_key: str,
    num_rows: int,
    max_retries: int,
    sleep_seconds: float,
    retry_backoff_seconds: float,
) -> list[Transaction]:
    _city_code, district, lawd_cd, deal_month = task
    return _fetch_month_with_retries(
        fetcher,
        service_key=service_key,
        district=district,
        lawd_cd=lawd_cd,
        deal_month=deal_month,
        num_rows=num_rows,
        max_retries=max_retries,
        sleep_seconds=sleep_seconds,
        retry_backoff_seconds=retry_backoff_seconds,
    )


def _record_fetch_result(
    stats: dict[HistoricalFloorKey, _MutableFloorStat],
    transactions: list[Transaction],
    *,
    city_code: str,
    district: str,
    lawd_cd: str,
    deal_month: str,
    request_count: int,
    transaction_count: int,
    progress: ProgressCallback | None,
) -> tuple[int, int]:
    next_request_count = request_count + 1
    next_transaction_count = transaction_count + len(transactions)
    for transaction in transactions:
        update_historical_floor_stats(stats, transaction, city_code=city_code)
    if progress is not None:
        progress(
            {
                "stage": "month",
                "city_code": city_code,
                "district": district,
                "lawd_cd": lawd_cd,
                "deal_month": deal_month,
                "rows": len(transactions),
                "requests": next_request_count,
                "transactions": next_transaction_count,
                "complexes": len(stats),
            }
        )
    return next_request_count, next_transaction_count


def floor_confidence(observation_count: int) -> str:
    if observation_count >= 20:
        return "high"
    if observation_count >= 5:
        return "medium"
    return "low"


def round_up_to_floor_step(floor: int, step: int = 4) -> int:
    normalized_floor = max(1, int(floor))
    return ((normalized_floor + step - 1) // step) * step


def _floor_key(transaction: Transaction) -> HistoricalFloorKey:
    return (
        transaction.property_type,
        transaction.lawd_cd,
        transaction.legal_dong,
        transaction.building_name,
    )


def _city_code(transaction: Transaction, override: str | None) -> str:
    if override:
        return override
    extra_features = getattr(transaction, "extra_features", {}) or {}
    return str(extra_features.get("city_code") or "").strip().lower() or "unknown"


def _split_yyyymm(value: str) -> tuple[int, int]:
    if len(value) != 6 or not value.isdigit():
        raise ValueError("month must be in YYYYMM format")
    year = int(value[:4])
    month = int(value[4:])
    if not 1 <= month <= 12:
        raise ValueError("month must be between 01 and 12")
    return year, month


def _fetch_month_with_retries(
    fetcher: MonthlyFetcher,
    *,
    service_key: str,
    district: str,
    lawd_cd: str,
    deal_month: str,
    num_rows: int,
    max_retries: int,
    sleep_seconds: float,
    retry_backoff_seconds: float,
) -> list[Transaction]:
    last_error: Exception | None = None
    for attempt in range(max(0, max_retries) + 1):
        try:
            return fetcher(
                service_key=service_key,
                district=district,
                lawd_cd=lawd_cd,
                deal_ymd=deal_month,
                num_rows=num_rows,
                property_type="apartment",
            )
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            wait_seconds = retry_backoff_seconds * (attempt + 1)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
    assert last_error is not None
    raise RuntimeError(f"failed to fetch historical floor observations for {district} {lawd_cd} {deal_month}: {last_error}") from last_error
