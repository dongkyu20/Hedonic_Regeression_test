# Seoul Housing Hedonic Price Model

서울 전체 25개 구의 최근 24개월 공동주택 매매 실거래 데이터를 공공데이터포털에서 수집해 scikit-learn 기반 Hedonic Price Model 회귀 모델을 학습하는 Python CLI 프로젝트입니다.

## 데이터 출처

- 아파트: 공공데이터포털 `국토교통부_아파트 매매 실거래가 자료`
  - Endpoint: `https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade`
- 오피스텔: 공공데이터포털 `국토교통부_오피스텔 매매 실거래가 자료`
  - Endpoint: `https://apis.data.go.kr/1613000/RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade`
- 연립·다세대: 공공데이터포털 `국토교통부_연립다세대 매매 실거래가 자료`
  - Endpoint: `https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade`
- 주요 요청 파라미터: `serviceKey`, `LAWD_CD`, `DEAL_YMD`, `pageNo`, `numOfRows`

## 설정

`.env` 파일을 만들고 공공데이터포털의 일반 인증키 Decoding 값을 넣습니다.

```bash
PUBLIC_DATA_SERVICE_KEY=your_data_go_kr_decoding_service_key
```

## CSV 생성 및 학습 실행

먼저 의존성을 설치합니다.

```bash
python3 -m pip install --user -e .
```

가상환경을 사용한다면 아래처럼 활성화한 뒤 진행합니다.

```bash
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -e .
```

현재 작업공간에서 바로 실행하려면 `PYTHONPATH=src`를 붙입니다.

아파트 데이터만 CSV로 만들려면 아래 명령을 사용합니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price fetch --months 24 --output data/seoul_apartment_trades.csv
```

실행이 완료되면 `data/seoul_apartment_trades.csv` 파일이 생성됩니다. 서울 전체 25개 구와 24개월을 순차 호출하므로 API 응답 속도에 따라 몇 분 이상 걸릴 수 있습니다. 이 단계는 현재 별도 진행률 로그를 출력하지 않습니다.

아파트, 오피스텔, 연립·다세대 데이터를 모두 포함한 통합 CSV를 만들려면 `--property-types`를 지정합니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price fetch --months 24 --property-types apartment,officetel,rowhouse --output data/seoul_housing_trades.csv
```

`--property-types`에는 쉼표로 구분해 아래 값을 넣을 수 있습니다.

- `apartment`: 아파트
- `officetel`: 오피스텔
- `rowhouse`: 연립·다세대

통합 CSV에는 `property_type` 컬럼이 추가됩니다. 값은 `apartment`, `officetel`, `rowhouse` 중 하나입니다. 건물명은 `building_name`에 저장되지만, 학습 특성으로는 사용하지 않습니다. 연립·다세대 API에서 제공되는 경우 `house_type`, `land_area_m2`도 함께 저장됩니다.

오피스텔이나 연립·다세대 호출에서 `403 Forbidden` 오류가 나면 해당 API의 활용 신청이 현재 인증키에 승인되지 않은 상태일 수 있습니다. data.go.kr에서 아파트 API와 별도로 오피스텔, 연립·다세대 API 활용 신청을 확인해야 합니다.

API 응답에 `buildYear`가 없는 거래는 연식 특성을 만들 수 없으므로 CSV에서 제외합니다. 제외된 거래가 있으면 출력 CSV 옆에 JSONL 로그가 생성됩니다.

```text
data/seoul_officetel_trades.csv
data/seoul_officetel_trades.skipped.jsonl
```

로그 파일에는 제외 사유(`reason`), 주택유형, 자치구, 법정동, 건물명, 거래월, 전용면적, 층, 거래금액이 한 줄에 하나씩 기록됩니다. 로그 경로를 직접 지정하려면 `--skip-log-output`을 사용합니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price fetch --months 24 --property-types officetel --output data/seoul_officetel_trades.csv --skip-log-output logs/officetel_skipped.jsonl
```

CSV가 만들어지면 아래 명령으로 scikit-learn 기반 Hedonic Price Model을 학습합니다. 아파트 전용 CSV를 학습할 때는 기존 파일을 입력합니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price train --input data/seoul_apartment_trades.csv --model-output artifacts/hedonic_model.pkl
```

비아파트까지 포함한 통합 CSV를 학습할 때는 통합 CSV를 입력하고 별도 모델 파일로 저장합니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price train --input data/seoul_housing_trades.csv --model-output artifacts/hedonic_housing_model.pkl
```

학습 중에는 아래와 같은 진행 로그가 실시간으로 표시됩니다.

```text
[train] CSV 로드 시작 input=data/seoul_apartment_trades.csv
[train] CSV 로드 완료 rows=143940 elapsed_s=0.4
[train] 학습/검증 분할 완료 training_rows=108748 validation_rows=35192 first_month=202407 elapsed_s=0.6
[train] sklearn HistGradientBoosting 학습 training_rows=108748 max_iter=300 learning_rate=0.06 max_leaf_nodes=31 min_samples_leaf=30 l2_regularization=0.0 random_state=42 elapsed_s=9.8
[train] 평가 완료 rows=35192 mape=0.2347 r2_log=0.7984 elapsed_s=12.1
[train] 모델 저장 완료 output=artifacts/hedonic_model.pkl elapsed_s=12.3
```

학습이 끝나면 `artifacts/hedonic_model.pkl` 모델 파일이 생성되고, 마지막에 `mae_krw`, `rmse_krw`, `mape`, `r2_log` 같은 평가 지표가 JSON으로 출력됩니다.

CSV 생성과 학습을 한 번에 순서대로 실행하려면 아래처럼 입력합니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price fetch --months 24 --output data/seoul_apartment_trades.csv
PYTHONPATH=src python3 -m hedonic_house_price train --input data/seoul_apartment_trades.csv --model-output artifacts/hedonic_model.pkl
```

비아파트까지 포함해 한 번에 실행하려면 아래처럼 입력합니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price fetch --months 24 --property-types apartment,officetel,rowhouse --output data/seoul_housing_trades.csv
PYTHONPATH=src python3 -m hedonic_house_price train --input data/seoul_housing_trades.csv --model-output artifacts/hedonic_housing_model.pkl
```

학습된 모델로 CLI 예측을 실행하려면 아래 명령을 사용합니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price predict \
  --model artifacts/hedonic_model.pkl \
  --district 강남구 \
  --lawd-cd 11680 \
  --deal-year 2026 \
  --deal-month 6 \
  --legal-dong 역삼동 \
  --area 84.95 \
  --floor 15 \
  --build-year 2005
```

비아파트 포함 모델에서 오피스텔이나 연립·다세대를 예측하려면 `--property-type`을 지정합니다. 연립·다세대는 알고 있는 경우 `--house-type`, `--land-area`도 함께 넣을 수 있습니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price predict \
  --model artifacts/hedonic_housing_model.pkl \
  --property-type rowhouse \
  --house-type 다세대 \
  --land-area 18.2 \
  --district 강남구 \
  --lawd-cd 11680 \
  --deal-year 2026 \
  --deal-month 6 \
  --legal-dong 역삼동 \
  --area 29.43 \
  --floor 3 \
  --build-year 2011
```

브라우저 GUI를 실행하려면 학습된 모델 파일을 준비한 뒤 아래 명령을 사용합니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price gui --model artifacts/hedonic_model.pkl
```

기본 주소는 `http://127.0.0.1:8000`입니다. 포트를 바꾸려면 `--port 8001`처럼 지정합니다.

mac 터미널에서 명령어가 줄바꿈 때문에 끊기면 한 줄로 입력합니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price gui --model artifacts/hedonic_model.pkl --port 8000
```

## 모델 특성

종속변수는 `log(거래가격)`입니다. 기본 설명변수는 `log1p(전용면적)`, 거래월 추세, 자치구, 법정동, 계약월, 층 구간, 연식 구간, 주택유형(`property_type`)입니다. 연립·다세대 데이터에 대지권면적이 있으면 `log1p(land_area_m2)`, `has_land_area`도 사용하고, `house_type`이 있으면 범주형 특성으로 사용합니다. 건물명은 CSV에는 저장하지만 학습 요인에서는 제외합니다.

학습은 scikit-learn `Pipeline`으로 구성됩니다. `DictVectorizer(sparse=False)`가 범주형 변수를 원핫 인코딩하고, `HistGradientBoostingRegressor`가 로그 거래가격을 학습합니다. 기본값은 `max_iter=300`, `learning_rate=0.06`, `max_leaf_nodes=31`, `min_samples_leaf=30`, `l2_regularization=0.0`, `random_state=42`입니다. 트리 기반 모델이므로 선형모델용 스케일링 단계는 사용하지 않습니다. 모델 아티팩트는 sklearn 객체를 포함하므로 pickle 파일(`.pkl`)로 저장됩니다.

층은 단순히 높을수록 비싸다고 가정하지 않습니다. 원시 층수 대신 `floor_band`와 `low_floor`를 사용해 저층 할인, 중층/중고층 선호, 초고층의 다른 가격 패턴을 범주형 효과로 학습합니다. 또한 거래내역에서 단지별 관측 최고층을 그대로 `estimated_max_floor`로 사용하고, `relative_floor`, `is_first_floor`, `is_floor_2_3`, `is_estimated_top_floor`, `is_near_estimated_top_floor`를 추가합니다. 연식도 `deal_year - build_year`를 학습 시점에 계산한 뒤 `age_band`로 구간화합니다.

MySQL `model_training_features`로 학습할 때는 보강된 snapshot feature도 함께 사용합니다. 세대수와 총주차대수, 모든 거리/접근시간, 공원 면적 합계는 `log1p`로 변환하고, 지하철·버스·학교·학원·최근 거래량 같은 개수 변수는 구간화합니다. 동수 원본은 직접 쓰지 않고 `households_per_building`을 계산하며, 공원 면적은 `park_exists` 더미와 `log1p(park_area_total_m2_radius)`를 함께 사용합니다.

DB 학습은 현재 학습에 쓰는 보강 변수 중 하나라도 `NULL`인 거래를 제외하고, complete-case row만 사용합니다.

`train` 명령은 CSV 로드, 학습/검증 분할, 특성 생성, sklearn HistGradientBoosting 학습, 평가, 층 구간 잔차 계산, 모델 저장 단계를 `stderr`에 즉시 출력합니다. 최종 JSON 결과는 기존처럼 `stdout`에 출력됩니다.

## MySQL 데이터베이스 사용

CSV 흐름은 그대로 유지하면서 MySQL을 구조화된 저장소로 사용할 수 있습니다. MySQL 기능은 선택 사항이며, 사용하려면 MySQL 커넥터 의존성을 설치합니다.

```bash
python3 -m pip install -e ".[mysql]"
```

`.env` 또는 환경변수에 MySQL 접속 정보를 설정합니다.

```bash
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=hedonic_house_price
```

스키마와 서울/부산 행정구역 seed를 생성합니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price db-init
```

기존 서울 CSV를 MySQL로 적재합니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price db-import-csv \
  --input data/seoul_apartment_trades.csv \
  --city-code seoul
```

부산 CSV가 준비되면 같은 스키마에 `city-code busan`으로 적재합니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price db-import-csv \
  --input data/busan_apartment_trades.csv \
  --city-code busan
```

최고층 추정 보강용으로 2010년 1월 이후 서울/부산 아파트 거래를 조회해 단지별 관측 최고층 통계 CSV를 만들 수 있습니다. 이 파일은 가격 학습용 거래 DB에 자동 적재되지 않습니다.

```bash
PYTHON_BIN=python3 \
END_MONTH=202606 \
WORKERS=1 \
SLEEP_SECONDS=0.05 \
scripts/fetch_historical_floor_stats.sh
```

API가 `HTTP 429 Too Many Requests`를 반환하면 일정 시간 후 재실행하거나 `WORKERS=1`, `RETRY_BACKOFF_SECONDS=60` 이상의 보수 설정을 사용합니다.

MySQL의 `model_training_features` 뷰에서 거래를 읽어 학습하려면 `train --from-db`를 사용합니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price train \
  --from-db \
  --city-code seoul \
  --model-output artifacts/hedonic_mysql_seoul_model.pkl
```

학습 1회 단위로 전처리 문서, 실제 feature 목록, metrics, 모델 파일, manifest를 함께 보관하려면 `--run-output-dir`을 지정합니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price train \
  --from-db \
  --property-types apartment \
  --model-output artifacts/hedonic_db_hist_gradient_boosting_model.pkl \
  --max-iter 300 \
  --learning-rate 0.06 \
  --max-leaf-nodes 31 \
  --min-samples-leaf 30 \
  --l2-regularization 0.0 \
  --random-state 42 \
  --run-output-dir artifacts/training_runs/20260610_hist_gradient_boosting_complete_case
```

run 폴더에는 `run_manifest.json`, `model.pkl`, `preprocessing.md`, `feature_names.csv`, `dropped_features.json`, `metrics.json`, `residuals_by_floor_band.json`이 생성됩니다.

`housing_transactions.city_code`와 `administrative_regions.city_code`는 `seoul` 또는 `busan` 값으로 서울/부산 여부를 명확히 구분합니다. 교통, 생활·교육·자연환경, 도시 경쟁력 값은 각 snapshot 테이블에 월 단위로 적재하면 `model_training_features` 뷰에서 거래 월과 정확히 일치하는 값만 조인됩니다.

## 검증

```bash
python3 -m unittest discover -v
```
