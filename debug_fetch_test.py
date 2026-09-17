import os
import sys
from getpass import getpass
from pprint import pprint

import pandas as pd

try:
    from fetchfinancialsexcel import FundamentalDataFetcher
    import fetchfinancialsexcel.company_data_extraction_EODH as eodh
except Exception as exc:
    print(f"Failed to import package from workspace: {exc}")
    sys.exit(1)


TICKER = os.getenv("EODHD_TEST_TICKER", "TSLA.US")


def load_api_key():
    api_key = "6aa27d63e42461.56407887"
    #api_key = os.getenv("EODHD_API_KEY")
    #if api_key:
    #    return api_key.strip()

    #api_key = getpass("Enter EODHD API key: ").strip()
    #if not api_key:
    #    raise SystemExit("API key is required.")
    return api_key


def print_section(title):
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def unavailable_price_api(*args, **kwargs):
    raise AssertionError("The fundamentals-only pipeline called a price API.")


def run_metric(name, function, failures):
    try:
        result = function()
        print(f"{name}: {result}")
        return result
    except Exception as exc:
        failures.append((name, exc))
        print(f"{name}: ERROR - {type(exc).__name__}: {exc}")
        return None


def main():
    api_key = load_api_key()
    eodh.API_KEY = api_key

    # Fail loudly if an unavailable price endpoint is used accidentally.
    eodh.fetch_price_data = unavailable_price_api
    eodh.real_time_price = unavailable_price_api

    print_section(f"Fundamentals-only local test: {TICKER}")
    data = eodh.fetch_fundamentals(TICKER)

    print(f"Fundamentals type: {type(data).__name__}")
    print(f"Top-level sections: {sorted(data.keys()) if isinstance(data, dict) else data}")

    if not isinstance(data, dict) or not data:
        print("No fundamentals data returned.")
        return 1

    print_section("Raw fundamentals fields")
    general = data.get("General", {})
    highlights = data.get("Highlights", {})
    valuation = data.get("Valuation", {})

    print(f"CurrencyCode: {general.get('CurrencyCode')}")
    print(f"Sector: {general.get('Sector')}")
    print(f"ForwardPE: {valuation.get('ForwardPE')}")
    print(f"MarketCapitalization: {highlights.get('MarketCapitalization')}")

    failures = []
    print_section("Direct fundamentals metrics")
    metric_specs = [
        ("Selected highlights", lambda: eodh.get_selected_highlights(data)),
        ("ROCE", lambda: eodh.calculate_roce(data)),
        ("Revenue Growth", lambda: eodh.get_revenue_growth_data(data)),
        ("EPS Growth", lambda: eodh.get_eps_growth_full(data)),
        ("FCF Yield", lambda: eodh.fcf_yield_growth_latest(data)),
        ("Buybacks", lambda: eodh.buyback_extensive(data)),
        ("Insiders", lambda: eodh.get_percent_insiders(data)),
        ("Gross Profitability", lambda: eodh.gross_profitability(data)),
        ("Accruals", lambda: eodh.accruals(data)),
        ("Asset Growth", lambda: eodh.asset_growth(data)),
        ("Total Yield", lambda: eodh.total_yield(data)),
        ("COP/AT", lambda: eodh.compute_cop_at(data)),
        ("COP/AT Revised", lambda: eodh.compute_cop_at_generous(data)),
        ("NOA", lambda: eodh.get_NOA(data)),
    ]

    for name, function in metric_specs:
        run_metric(name, function, failures)

    print_section("FundamentalDataFetcher pipeline")
    fetcher = FundamentalDataFetcher(api_key=api_key)
    pipeline_result = run_metric(
        "fetch_company_data",
        lambda: fetcher.fetch_company_data(TICKER),
        failures,
    )
    combined, other = pipeline_result or ({}, {})

    print("Combined result:")
    pprint(combined)
    print("Other result:")
    pprint(other)

    analyzed = run_metric(
        "analyze_data",
        lambda: fetcher.analyze_data(
            pd.DataFrame([combined]),
            [dict(other, Ticker=TICKER)],
            factor_country="Europe",
        ),
        failures,
    )
    if analyzed is not None:
        print("Analyzed result:")
        pprint(analyzed.to_dict(orient="records"))

    if failures:
        print_section("FAILED")
        for name, error in failures:
            print(f"- {name}: {type(error).__name__}: {error}")
        return 1

    print_section("PASSED")
    print("The selected fundamentals-only functions completed without errors.")
    print("No EOD or real-time price API was called.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
