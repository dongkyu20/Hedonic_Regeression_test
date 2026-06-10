# 모델 변수 전처리 문서

이 문서는 `model_training_features` 뷰와 거래 원천값이 학습 전에 어떻게 변환되는지 정리합니다.

현재 모델의 종속변수는 `log(price_krw)`입니다. 문자열 변수는 `DictVectorizer(sparse=False)`를 통해 원핫 인코딩되고, 숫자 변수는 별도 스케일링 없이 `HistGradientBoostingRegressor`에 입력됩니다.

## 핵심 거래 변수

| 원천 변수 | 학습 변수 | 전처리 방식 |
|---|---|---|
| `price_krw` | `target_log_price` | 종속변수. `log(price_krw)`로 변환합니다. |
| `exclusive_area_m2` | `log_area_m2` | `log1p(exclusive_area_m2)`로 변환합니다. 0 이하이면 학습 row 생성 단계에서 에러를 냅니다. |
| `land_area_m2` | `log_land_area_m2`, `has_land_area` | 값이 0보다 크면 `log1p(land_area_m2)`, `has_land_area = 1`; 없으면 `0.0`, `0`으로 둡니다. |
| `deal_yyyymm` | `deal_month_index` | 학습 데이터의 첫 거래월부터 몇 개월 지났는지 계산합니다. |
| `deal_month` | `calendar_month` | `1`-`12` 문자열 범주로 사용하며 원핫 인코딩됩니다. |
| `district` | `district` | 구 단위 문자열 범주로 사용하며 원핫 인코딩됩니다. |
| `legal_dong` | `legal_dong` | 법정동 문자열 범주로 사용하며 원핫 인코딩됩니다. |
| `property_type` | `property_type` | 주택유형 문자열 범주로 사용하며 원핫 인코딩됩니다. 현재 DB 학습은 주로 `apartment`만 사용합니다. |
| `house_type` | `house_type` | 세부 주택유형 문자열 범주입니다. 빈 값은 `unknown`으로 바꿉니다. |
| `building_name` | 없음 | 건물명/단지명은 학습 변수에서 제외합니다. |

## 집 자체 조건

| 원천 변수 | 학습 변수 | 전처리 방식 |
|---|---|---|
| `floor` | `floor_band` | 층을 구간화합니다: `floor_1`, `floor_2_3`, `floor_4_7`, `floor_8_12`, `floor_13_18`, `floor_19_25`, `floor_26_plus`. 문자열 범주라서 원핫 인코딩됩니다. |
| `floor` | `low_floor` | 3층 이하이면 `1`, 아니면 `0`입니다. |
| `kapt_max_floor`, `floor`, 단지별 거래내역 | `estimated_max_floor` | KAPT 단지 기본정보의 최고층(`kapt_max_floor`)이 있으면 우선 사용합니다. 없으면 `(property_type, lawd_cd, legal_dong, building_name)` 단위의 학습 split 관측 최고 거래층을 4층 단위로 올림해 사용합니다. 예: 관측 최고 21층은 24층, 7층은 8층으로 추정합니다. |
| `kapt_max_floor`, 단지별 거래내역 | `max_floor_source` | 최고층 기준의 출처를 `kapt`, `transaction_estimate`, `current_floor_estimate`, `current_floor` 범주로 기록합니다. 문자열 범주라서 원핫 인코딩됩니다. |
| `floor`, `estimated_max_floor` | `relative_floor` | `floor / estimated_max_floor`로 계산합니다. 같은 20층이라도 단지 최고층 대비 상대 위치를 반영합니다. |
| `relative_floor` | `relative_floor_bin` | 상대층수를 `relative_floor_0_25`, `relative_floor_25_50`, `relative_floor_50_75`, `relative_floor_75_100`, `relative_floor_100`으로 구간화합니다. |
| `floor`, `estimated_max_floor` | `floors_below_estimated_top` | 추정/공식 최고층에서 현재 거래층을 뺀 값입니다. 최상단까지 남은 층수를 숫자로 반영합니다. |
| `floors_below_estimated_top` | `floors_below_estimated_top_bin` | 최상단까지 남은 층수를 `below_top_0`, `below_top_1_2`, `below_top_3_5`, `below_top_6_10`, `below_top_11_plus`로 구간화합니다. |
| `floor` | `is_first_floor` | 1층이면 `1`, 아니면 `0`입니다. |
| `floor` | `is_floor_2_3` | 2~3층이면 `1`, 아니면 `0`입니다. |
| `floor`, `estimated_max_floor` | `is_estimated_top_floor` | 거래층이 추정 최고층과 같으면 `1`, 아니면 `0`입니다. |
| `floor`, `estimated_max_floor` | `is_near_estimated_top_floor` | 거래층이 추정 최고층보다 2층 이하로 낮은 최상단부이면 `1`, 아니면 `0`입니다. |
| `build_year`, `deal_year` | `age_band` | `max(0, deal_year - build_year)`로 거래 시점 연식을 계산한 뒤 `age_0_4`, `age_5_9`, `age_10_19`, `age_20_29`, `age_30_39`, `age_40_plus`로 구간화합니다. |
| `household_count` | `log_household_count` | `log1p(household_count)`로 변환합니다. 결측/음수이면 `0.0`과 `household_count_missing = 1`을 넣습니다. |
| `building_count`, `household_count` | `households_per_building` | `household_count / building_count`를 계산합니다. `building_count` 원본은 직접 쓰지 않습니다. 계산 불가이면 `0.0`과 `households_per_building_missing = 1`을 넣습니다. |
| `total_parking_spaces` | `log_total_parking_spaces` | `log1p(total_parking_spaces)`로 변환합니다. 결측/음수이면 `0.0`과 `total_parking_spaces_missing = 1`을 넣습니다. |
| `parking_spaces_per_household` | `parking_spaces_per_household` | 세대당 주차대수는 원값을 숫자 변수로 유지합니다. 결측이면 `0.0`과 `parking_spaces_per_household_missing = 1`을 넣습니다. |
| `has_community_facilities` | `has_community_facilities` | 입주 편의/커뮤니티 시설 여부는 더미 숫자로 유지합니다. 결측이면 `0.0`과 `has_community_facilities_missing = 1`을 넣습니다. |

## 교통 접근성

| 원천 변수 | 학습 변수 | 전처리 방식 |
|---|---|---|
| `city_code` | `city_code` | `seoul`, `busan`, `unknown` 범주로 사용하며 원핫 인코딩됩니다. |
| `nearest_subway_distance_m` | `log_nearest_subway_distance_m` | `log1p(value)`로 변환합니다. 결측/음수이면 `0.0`과 `_missing` 플래그를 넣습니다. |
| `subway_count_radius` | `subway_count_radius_bin` | 개수 구간으로 바꾼 뒤 원핫 인코딩합니다. |
| `nearest_bus_stop_distance_m` | `log_nearest_bus_stop_distance_m` | `log1p(value)`로 변환합니다. 결측/음수이면 `0.0`과 `_missing` 플래그를 넣습니다. |
| `bus_stop_count_radius` | `bus_stop_count_radius_bin` | 개수 구간으로 바꾼 뒤 원핫 인코딩합니다. |
| `car_intercity_bus_terminal_minutes` | `log_car_intercity_bus_terminal_minutes` | `log1p(value)`로 변환합니다. |
| `car_airport_minutes` | `log_car_airport_minutes` | `log1p(value)`로 변환합니다. |
| `car_rail_station_minutes` | `log_car_rail_station_minutes` | `log1p(value)`로 변환합니다. |
| `car_general_hospital_minutes` | `log_car_general_hospital_minutes` | `log1p(value)`로 변환합니다. |
| `transit_intercity_bus_terminal_minutes` | `log_transit_intercity_bus_terminal_minutes` | `log1p(value)`로 변환합니다. |
| `transit_airport_minutes` | `log_transit_airport_minutes` | `log1p(value)`로 변환합니다. |
| `transit_rail_station_minutes` | `log_transit_rail_station_minutes` | `log1p(value)`로 변환합니다. |
| `transit_general_hospital_minutes` | `log_transit_general_hospital_minutes` | `log1p(value)`로 변환합니다. |

모든 접근시간 변수는 결측/음수일 때 `0.0`과 `<원천변수명>_missing = 1`을 함께 넣습니다.

## 생활, 교육, 자연환경

| 원천 변수 | 학습 변수 | 전처리 방식 |
|---|---|---|
| `nearest_elementary_school_distance_m` | `log_nearest_elementary_school_distance_m` | `log1p(value)`로 변환합니다. 결측/음수이면 `0.0`과 `_missing` 플래그를 넣습니다. |
| `nearest_middle_school_distance_m` | `log_nearest_middle_school_distance_m` | `log1p(value)`로 변환합니다. 결측/음수이면 `0.0`과 `_missing` 플래그를 넣습니다. |
| `school_count_radius` | `school_count_radius_bin` | 개수 구간으로 바꾼 뒤 원핫 인코딩합니다. |
| `academy_count_radius` | `academy_count_radius_bin` | 개수 구간으로 바꾼 뒤 원핫 인코딩합니다. |
| `nearest_hospital_distance_m` | `log_nearest_hospital_distance_m` | `log1p(value)`로 변환합니다. 결측/음수이면 `0.0`과 `_missing` 플래그를 넣습니다. |
| `nearest_pharmacy_distance_m` | `log_nearest_pharmacy_distance_m` | `log1p(value)`로 변환합니다. 결측/음수이면 `0.0`과 `_missing` 플래그를 넣습니다. |
| `nearest_park_distance_m` | `log_nearest_park_distance_m` | `log1p(value)`로 변환합니다. 결측/음수이면 `0.0`과 `_missing` 플래그를 넣습니다. |
| `park_area_total_m2_radius` | `park_exists` | 공원 면적 합계가 있고 0보다 크면 `1`, 아니면 `0`입니다. |
| `park_area_total_m2_radius` | `log_park_area_total_m2_radius` | `log1p(value)`로 변환합니다. 결측/음수이면 `0.0`과 `park_area_total_m2_radius_missing = 1`을 넣습니다. |

## 도시 경쟁력

| 원천 변수 | 학습 변수 | 전처리 방식 |
|---|---|---|
| `recent_transaction_count` | `recent_transaction_count_bin` | 개수 구간으로 바꾼 뒤 원핫 인코딩합니다. |
| `population_count`, `population_growth_rate`, `employment_rate`, `income_level_krw`, `unsold_housing_count`, `completed_housing_supply_count` | 없음 | DB 스키마와 뷰에는 있지만, 현재 학습 reader에는 아직 포함하지 않습니다. |

## 개수 변수 구간 기준

반경 내 지하철 수, 버스 정류장 수, 학교 수, 학원 수, 최근 거래량은 아래 기준으로 구간화합니다.

| 원천 개수 | 범주 |
|---:|---|
| 결측 | `missing` |
| `<= 0` | `count_0` |
| `1-2` | `count_1_2` |
| `3-5` | `count_3_5` |
| `6-10` | `count_6_10` |
| `11-20` | `count_11_20` |
| `>= 21` | `count_21_plus` |

## 결측 처리 규칙

DB 학습에서는 `model_training_features`에서 현재 학습 reader가 선택하는 보강 변수 중 하나라도 `NULL`인 거래 row를 조회 단계에서 제외합니다. 즉 `train --from-db`는 complete-case 데이터만 사용합니다.

로그 변환 숫자 변수는 결측값을 다음처럼 처리합니다.

| 상태 | 변환값 | 결측 플래그 |
|---|---:|---:|
| 값 있음 | `log1p(value)` | `0` |
| 결측 또는 음수 | `0.0` | `1` |

개수 구간 변수는 결측이면 `missing` 범주가 됩니다.

위 결측 플래그와 `missing` 범주는 전처리 함수의 안전장치입니다. DB 학습 기본 경로에서는 complete-case 필터가 먼저 적용되므로, 실제 학습에는 결측 보강값이 있는 거래가 들어가지 않습니다.

## 상수 변수 제거

학습 split에서 feature row를 만든 뒤, 값이 하나뿐인 feature는 모델 학습 전에 제거합니다. 예를 들어 아파트만 학습할 때 `property_type=apartment`처럼 모든 row에서 동일한 변수나, 모든 row가 결측인 optional 변수는 모델에 들어가지 않습니다. 같은 제거 목록은 validation과 잔차 계산에도 적용됩니다.

## 잔차 리포트용 해석 구간

조건별 잔차 리포트는 모델 입력 변수를 그대로 보는 것 외에, 사람이 해석하기 쉬운 구간을 추가로 사용합니다. 아래 구간은 진단 리포트용이며, 모두가 학습 feature와 1:1로 같지는 않습니다.

| 진단 변수 | 구간 |
|---|---|
| `area_m2_bin` | `area_0_40`, `area_40_60`, `area_60_85`, `area_85_102`, `area_102_135`, `area_135_plus` |
| `household_count_bin` | `households_0_299`, `households_300_499`, `households_500_999`, `households_1000_1999`, `households_2000_plus`, `missing` |
| `households_per_building_bin` | `households_per_building_0_99`, `households_per_building_100_199`, `households_per_building_200_299`, `households_per_building_300_plus`, `missing` |
| `parking_spaces_per_household_bin` | `parking_0_0.8`, `parking_0.8_1.0`, `parking_1.0_1.3`, `parking_1.3_1.8`, `parking_1.8_plus`, `missing` |
| 거리 구간 | `distance_0_250`, `distance_250_500`, `distance_500_1000`, `distance_1000_2000`, `distance_2000_plus`, `missing` |
| 접근시간 구간 | `minutes_0_15`, `minutes_15_30`, `minutes_30_45`, `minutes_45_60`, `minutes_60_plus`, `missing` |
| `park_area_total_m2_radius_bin` | `park_area_0`, `park_area_1_10000`, `park_area_10000_50000`, `park_area_50000_plus`, `missing` |
