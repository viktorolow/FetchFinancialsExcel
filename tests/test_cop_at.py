import copy
import unittest

from fetchfinancialsexcel import company_data_extraction_EODH as eodh


def make_data():
    """Minimal EODHD-liknande fundamentals med två kompletta räkenskapsår."""
    return {
        "Financials": {
            "Income_Statement": {"yearly": {
                "2025-12-31": {"operatingIncome": "100", "ebit": "100", "researchDevelopment": "10",
                               "depreciationAndAmortization": "20", "reconciledDepreciation": "20"},
                "2024-12-31": {"operatingIncome": "90", "ebit": "90", "researchDevelopment": "10",
                               "depreciationAndAmortization": "18"},
            }},
            "Balance_Sheet": {"yearly": {
                "2025-12-31": {"totalAssets": "1100", "netReceivables": "60", "inventory": "40",
                               "otherCurrentAssets": "15", "currentDeferredRevenue": None,
                               "accountsPayable": "35", "otherCurrentLiab": "25"},
                "2024-12-31": {"totalAssets": "1000", "netReceivables": "50", "inventory": "30",
                               "otherCurrentAssets": "10", "currentDeferredRevenue": None,
                               "accountsPayable": "30", "otherCurrentLiab": "20"},
            }},
            "Cash_Flow": {"yearly": {
                "2025-12-31": {"depreciation": "20"},
            }},
        }
    }

# (100 + 10 + 20 - 10 - 10 - 5 + 0 + 5 + 5) / 1000
EXPECTED = 0.115


class TestNum(unittest.TestCase):
    def test_handles_null_missing_and_strings(self):
        d = {"a": None, "b": "abc", "c": "12.5", "d": 3}
        self.assertIsNone(eodh._num(d, "a", "b", "x"))
        self.assertEqual(eodh._num(d, "a", "c"), 12.5)
        self.assertEqual(eodh._num(d, "d"), 3.0)
        self.assertIsNone(eodh._num(None, "a"))


class TestComputeCopAt(unittest.TestCase):
    def test_base_case(self):
        self.assertAlmostEqual(eodh.compute_cop_at(make_data())["cop_at"], EXPECTED)

    def test_null_da_falls_back_to_reconciled_depreciation(self):
        data = make_data()
        data["Financials"]["Income_Statement"]["yearly"]["2025-12-31"]["depreciationAndAmortization"] = None
        self.assertAlmostEqual(eodh.compute_cop_at(data)["cop_at"], EXPECTED)

    def test_da_falls_back_to_cash_flow_depreciation(self):
        data = make_data()
        inc = data["Financials"]["Income_Statement"]["yearly"]["2025-12-31"]
        inc["depreciationAndAmortization"] = None
        inc["reconciledDepreciation"] = None
        self.assertAlmostEqual(eodh.compute_cop_at(data)["cop_at"], EXPECTED)

    def test_null_ebit_uses_operating_income(self):
        data = make_data()
        data["Financials"]["Income_Statement"]["yearly"]["2025-12-31"]["ebit"] = None
        self.assertAlmostEqual(eodh.compute_cop_at(data)["cop_at"], EXPECTED)

    def test_null_operating_income_uses_ebit(self):
        data = make_data()
        data["Financials"]["Income_Statement"]["yearly"]["2025-12-31"]["operatingIncome"] = None
        self.assertAlmostEqual(eodh.compute_cop_at(data)["cop_at"], EXPECTED)

    def test_no_inventory_gives_zero_delta(self):
        data = make_data()
        for row in data["Financials"]["Balance_Sheet"]["yearly"].values():
            row.pop("inventory")
        # ΔInv = 10 faller bort
        self.assertAlmostEqual(eodh.compute_cop_at(data)["cop_at"], EXPECTED + 0.01)

    def test_all_da_missing_returns_none(self):
        data = make_data()
        inc = data["Financials"]["Income_Statement"]["yearly"]["2025-12-31"]
        inc["depreciationAndAmortization"] = None
        inc.pop("reconciledDepreciation")
        data["Financials"]["Cash_Flow"]["yearly"]["2025-12-31"]["depreciation"] = None
        self.assertIsNone(eodh.compute_cop_at(data)["cop_at"])

    def test_latest_income_row_missing_in_balance_sheet_uses_previous_complete_year(self):
        data = make_data()
        # nyare resultaträkningsrad utan matchande balansräkning -> 2025 ska användas
        data["Financials"]["Income_Statement"]["yearly"]["2026-12-31"] = {
            "operatingIncome": "999", "depreciationAndAmortization": "1"}
        self.assertAlmostEqual(eodh.compute_cop_at(data)["cop_at"], EXPECTED)

    def test_no_threshold(self):
        data = make_data()
        data["Financials"]["Income_Statement"]["yearly"]["2025-12-31"]["operatingIncome"] = "5000"
        self.assertGreater(eodh.compute_cop_at(data)["cop_at"], 1)

    def test_prior_year_gap_out_of_range_returns_none(self):
        data = make_data()
        bs = data["Financials"]["Balance_Sheet"]["yearly"]
        bs["2023-12-31"] = bs.pop("2024-12-31")
        self.assertIsNone(eodh.compute_cop_at(data)["cop_at"])

    def test_non_positive_prior_assets_returns_none(self):
        data = make_data()
        data["Financials"]["Balance_Sheet"]["yearly"]["2024-12-31"]["totalAssets"] = "0"
        self.assertIsNone(eodh.compute_cop_at(data)["cop_at"])


class TestComputeCopAtGenerous(unittest.TestCase):
    def test_no_inventory_gives_value(self):
        data = make_data()
        for row in data["Financials"]["Balance_Sheet"]["yearly"].values():
            row.pop("inventory")
        # (100 - 10) / 1100
        self.assertAlmostEqual(eodh.compute_cop_at_generous(data)["cop_at_revised"], round(90 / 1100, 4))

    def test_null_ebit_uses_operating_income(self):
        data = make_data()
        data["Financials"]["Income_Statement"]["yearly"]["2025-12-31"]["ebit"] = None
        self.assertAlmostEqual(eodh.compute_cop_at_generous(data)["cop_at_revised"], round(80 / 1100, 4))

    def test_above_threshold_does_not_overwrite_cop_at(self):
        data = make_data()
        data["Financials"]["Income_Statement"]["yearly"]["2025-12-31"]["ebit"] = "5000"
        cop_at = eodh.compute_cop_at(data)
        generous = eodh.compute_cop_at_generous(data)
        self.assertEqual(generous, {"cop_at_revised": None})
        combined = {**cop_at, **generous}  # samma ordning som core.py
        self.assertIsNotNone(combined["cop_at"])
        self.assertIsNone(combined["cop_at_revised"])


if __name__ == "__main__":
    unittest.main()
