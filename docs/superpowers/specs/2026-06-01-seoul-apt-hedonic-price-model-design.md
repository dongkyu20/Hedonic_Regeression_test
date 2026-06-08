# Seoul Apartment Hedonic Price Model Design

## Goal

Build a Python command-line project that fetches Seoul apartment sale transactions from the public data.go.kr MOLIT apartment trade API, trains a hedonic regression model on the most recent 24 months, and predicts sale prices for apartment-like inputs.

## Data Source

Use `국토교통부_아파트 매매 실거래가 자료`, a REST/XML API from data.go.kr. Requests use:

- `serviceKey`: read from `PUBLIC_DATA_SERVICE_KEY`
- `LAWD_CD`: first five digits of the legal-dong code
- `DEAL_YMD`: contract year-month in `YYYYMM`
- `pageNo` and `numOfRows` for pagination

The default collection scope is all 25 Seoul districts for the most recent 24 completed or current months. District-level law codes are built into the package so the project can run without an external code table.

## Project Shape

The project will be a Python package with a CLI:

- `fetch`: collect raw transactions and save a normalized CSV cache
- `train`: transform transactions into hedonic features, train the model, and save a model artifact
- `predict`: load the artifact and estimate a sale price from user-provided property attributes

The package will keep data fetching, date/law-code utilities, XML parsing, feature engineering, model training, and CLI concerns in separate modules.

## Hedonic Regression Design

The target is `log(price_krw)`, derived from the API's transaction amount in ten-thousand KRW units. Predictions are converted back to KRW and ten-thousand KRW for reporting.

Numeric features:

- `log_area_m2`: log of exclusive-use area
- `age`: transaction year minus build year
- `age_squared`: squared age to allow non-linear aging and redevelopment expectation effects
- `deal_month_index`: elapsed month index within the training window

Floor features:

- `floor_band`: categorical floor bucket such as `floor_1`, `floor_2_3`, `floor_4_7`, `floor_8_12`, `floor_13_18`, `floor_19_25`, `floor_26_plus`
- `low_floor`: binary flag for floors 1 through 3
- `floor_spline`: smooth non-linear spline basis for floor

The floor model intentionally avoids a simple monotonic assumption. The model can assign a higher premium to mid or mid-high floor bands than to very high floors if the Seoul transaction data supports that pattern.

Categorical features:

- `district`: Seoul district name
- `legal_dong`: legal-dong name when available
- `calendar_month`: contract month from 1 to 12

Apartment name is intentionally excluded from the model features. It remains in raw transaction rows for traceability, but it is not encoded, grouped, or used during training or prediction.

## Model

Use a scikit-learn pipeline:

- `DictVectorizer` for numeric and categorical feature dictionaries
- `StandardScaler(with_mean=False)` so sparse one-hot matrices remain sparse
- `Ridge` regression for a stable hedonic model with many categorical dummy variables

The model artifact stores the fitted scikit-learn pipeline, district code map, training window, and evaluation metrics in a pickle file.

## Evaluation

Use a chronological split:

- Train on older months
- Validate on the most recent six months, unless there is too little data

Report:

- MAE in KRW
- RMSE in KRW
- MAPE
- R2 on log price

Also report average residuals by `floor_band` so the floor treatment can be inspected for mid-floor preference or low-floor discount behavior.

## Error Handling

The fetcher should fail clearly when:

- `PUBLIC_DATA_SERVICE_KEY` is missing
- the API returns an error response
- XML cannot be parsed
- no transaction rows are returned for the requested scope

The trainer should fail clearly when required columns are missing or no usable rows remain after cleaning.

The predictor should fail clearly when the model artifact path is missing or required input fields are absent.

## Testing

Tests cover:

- month-window generation for recent 24 months
- Seoul law-code coverage for 25 districts
- XML response parsing and numeric normalization
- floor banding, low-floor flags, age features, and apartment-name exclusion
- train/evaluate/predict pipeline on a small synthetic transaction set
- CLI argument parsing for the main commands

Production code will be written after failing tests, following TDD.

## Out Of Scope

This version does not include a web UI, geocoding, school/subway/park external features, redevelopment designation data, or a production API server. Those can be added after the core public-data hedonic model is stable.
