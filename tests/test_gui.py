import json
import unittest

from hedonic_house_price.gui import build_prediction_input, render_index_html
from hedonic_house_price.modeling import predict_price, train_hedonic_model
from hedonic_house_price.transactions import Transaction


def sample_model():
    transactions = []
    for idx in range(8):
        transactions.append(
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
    return train_hedonic_model(
        transactions,
        max_iter=20,
        random_state=42,
        min_apartment_count=2,
        validation_months=2,
    )


class GuiTests(unittest.TestCase):
    def test_render_index_html_contains_prediction_form_fields(self):
        html = render_index_html(model_path="artifacts/hedonic_model.pkl")

        self.assertIn("id=\"prediction-form\"", html)
        self.assertIn("name=\"property_type\"", html)
        self.assertIn("name=\"district\"", html)
        self.assertIn("name=\"deal_year\"", html)
        self.assertIn("name=\"deal_month\"", html)
        self.assertIn("name=\"legal_dong\"", html)
        self.assertIn("name=\"area\"", html)
        self.assertIn("name=\"floor\"", html)
        self.assertIn("name=\"build_year\"", html)
        self.assertNotIn("name=\"apartment_name\"", html)
        self.assertIn("오피스텔", html)
        self.assertIn("연립·다세대", html)
        self.assertIn("강남구", html)

    def test_build_prediction_input_coerces_form_payload_and_infers_lawd_code(self):
        prediction_input = build_prediction_input(
            {
                "district": "강남구",
                "property_type": "rowhouse",
                "deal_year": "2026",
                "deal_month": "6",
                "deal_day": "",
                "legal_dong": "역삼동",
                "area": "84.95",
                "floor": "15",
                "build_year": "1981",
            }
        )

        self.assertEqual(prediction_input.lawd_cd, "11680")
        self.assertEqual(prediction_input.property_type, "rowhouse")
        self.assertEqual(prediction_input.deal_day, 15)
        self.assertEqual(prediction_input.exclusive_area_m2, 84.95)
        self.assertEqual(prediction_input.floor, 15)

    def test_build_prediction_input_reports_missing_required_field(self):
        with self.assertRaisesRegex(ValueError, "legal_dong"):
            build_prediction_input(
                {
                    "district": "강남구",
                    "property_type": "apartment",
                    "deal_year": "2026",
                    "deal_month": "6",
                    "legal_dong": "",
                    "area": "84.95",
                    "floor": "15",
                    "build_year": "1981",
                }
            )

    def test_prediction_payload_works_with_existing_model_api(self):
        prediction_input = build_prediction_input(
            {
                "district": "강남구",
                "property_type": "apartment",
                "deal_year": "2025",
                "deal_month": "6",
                "legal_dong": "역삼동",
                "area": "84.9",
                "floor": "15",
                "build_year": "2008",
            }
        )

        prediction = predict_price(sample_model(), prediction_input)

        self.assertGreater(prediction["price_krw"], 100_000_000)
        json.dumps(prediction, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
