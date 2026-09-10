import requests
import datetime 
from collections import defaultdict
import concurrent.futures
import statistics
import time
import random

# =============== Globals ===============
API_KEY = None  # set by the FundamentalDataFetcher class
now = datetime.datetime.today()
CURRENT_YEAR = now.strftime("%Y")
# ========================================

def _request_with_retry(url, timeout=20, max_retries=5):
    for attempt in range(max_retries):
        response = requests.get(url, timeout=timeout)

        if response.status_code != 429:
            response.raise_for_status()
            return response

        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            sleep_seconds = max(float(retry_after), 1)
        else:
            sleep_seconds = min(2 ** attempt, 30)

        sleep_seconds += random.uniform(0, 1)
        time.sleep(sleep_seconds)

    response.raise_for_status()
    return response

# huvudfunktion 
def fetch_fundamentals(ticker):
	try:
		url = f"https://eodhd.com/api/fundamentals/{ticker}?api_token={API_KEY}&fmt=json"
		resp = _request_with_retry(url)
		return resp.json()
	except Exception as e:
		print(f"Fel vid hämtning av data: {e}")
		return {}

# hämta prisdata, separat API call
def fetch_price_data(ticker):
    today = datetime.datetime.today().date()
    from_date = f"{int(CURRENT_YEAR)-5}-01-01"  
    to_date = today.isoformat()      

    url = f"https://eodhd.com/api/eod/{ticker}?from={from_date}&to={to_date}&period=d&api_token={API_KEY}&fmt=json"

    try:
        response = _request_with_retry(url)
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data for {ticker}: {e}")
        return {ticker: {}}
    
    return data

# returnerar {'price': 212.43}
def real_time_price(ticker, data):
    try:
        url = f"https://eodhd.com/api/real-time/{ticker}?api_token={API_KEY}&fmt=json"
        
        general = data.get("General", {})
        
        resp = _request_with_retry(url)
        resp = resp.json()
        return {
            "Price": resp.get("open"),
            "Currency": general.get("CurrencyCode"),
			"Sector": general.get("Sector")
        }
	
    except Exception as e:
        print(f"Fel vid hämtning av realtidsdata: {e}")
        return {}

# ROE, Avkastning, Rörelsemarginal, Utdelning
def get_selected_highlights(data):
	highlights = data.get("Highlights", {})

	# Kolumnnamn --> API 
	key_map = {
		"ROE": "ReturnOnEquityTTM",
		f"Rörelsemarginal": "OperatingMarginTTM", 
		"Direktavkastning": "DividendYield",
		"Utdelning": "DividendShare", 
        "MarketCap (mln)": "MarketCapitalizationMln"
	}

	selected = {readable: highlights.get(api_key) for readable, api_key in key_map.items()}
	return selected

# ROCE 
def calculate_roce(data):
	income_statement = data.get("Financials", {}).get("Income_Statement", {}).get("yearly", {})
	balance_sheet = data.get("Financials", {}).get("Balance_Sheet", {}).get("yearly", {})

	if not income_statement or not balance_sheet:
		return {"ROCE": None}

	# Hämta senaste året
	latest_year = sorted(income_statement.keys(), reverse=True)[0]

	try:
		ebit = float(income_statement[latest_year].get("ebit", 0))
		total_assets = float(balance_sheet[latest_year].get("totalAssets", 0))
		current_liabilities = float(balance_sheet[latest_year].get("totalCurrentLiabilities", 0))
	except (ValueError, TypeError):
		return {"ROCE": None}

	if total_assets == 0:
		return {"ROCE": None}

	# Capital Employed = Total Assets - Current Liabilities
	capital_employed = total_assets - current_liabilities
	if capital_employed <= 0:
		return {"ROCE": None}

	roce = ebit / capital_employed
	return {"ROCE": round(roce, 4)}

# Returnerar: {'Omsättningstillväxt 2026': 0.0751, '2025': -0.0365, 'Genomsnittlig tillväxt (5 år)': -0.0049}
def get_revenue_growth_data(data):
	trend_data = data.get("Earnings", {}).get("Trend", {})

	if not trend_data:
		return {}

	growths = {}
	current_year_str = str(CURRENT_YEAR)
	next_year_str = str(int(CURRENT_YEAR) + 1)

	for year in [current_year_str, next_year_str]:
		# Filtrera alla datum som börjar med det aktuella året
		dates_for_year = [d for d in trend_data if d.startswith(year)]
		if dates_for_year:
			# Ta det senaste datumet (t.ex. "2025-12" över "2025-06")
			latest_date = max(dates_for_year)
			period_data = trend_data[latest_date]
			growth_value = period_data.get('revenueEstimateGrowth')
			try:
				growth_value = float(growth_value) if growth_value is not None else None
			except ValueError:
				growth_value = None

			key = f"RPS {year}"
			growths[key] = growth_value

	# Räkna ut genomsnittlig tillväxt över senaste 5 åren (om möjligt)
	sorted_dates = sorted(trend_data.keys(), reverse=True)
	growth_values = []
	for date in sorted_dates:
		period_data = trend_data.get(date, {})
		growth_value = period_data.get('revenueEstimateGrowth')
		try:
			if growth_value is not None:
				growth_values.append(float(growth_value))
		except ValueError:
			continue

		if len(growth_values) == 5:
			break

	if len(growth_values) >= 5:
		avg_growth = sum(growth_values) / len(growth_values)
		growths["RPS Genomsnitt (5y)"] = round(avg_growth, 4)
	else:
		growths["RPS Genomsnitt (5y)"] = None

	return growths

# Returnerar: {'Target Price': 228.7593, 'EPS f2025': 7.1778, 'EPS f2026': 7.8284, 'Genomsnittlig EPS (5 år)': None}
def get_eps_growth_full(data):
    highlights = data.get("Highlights", {})

    def safe_float(val):
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    # get data
    est_current = safe_float(highlights.get("EPSEstimateCurrentYear"))
    est_next = safe_float(highlights.get("EPSEstimateNextYear"))
    latest_eps = safe_float(highlights.get("DilutedEpsTTM"))
    eps_per_year = calculate_eps_per_year(data)  

    # growth from latest actual to current estimate
    if latest_eps and est_current and latest_eps != 0:
        growth_actual_to_est = (est_current - latest_eps) / abs(latest_eps)
    else:
        growth_actual_to_est = None

    # growth from current estimate to next estimate
    if est_current and est_next and est_current != 0:
        growth_est_to_est = (est_next - est_current) / abs(est_current)
    else:
        growth_est_to_est = None

	# control 
    if growth_actual_to_est > 1.2 or growth_actual_to_est < -0.65: 
        growth_actual_to_est = None 
        
    # CAGR (5-year) eps using the eps_per_year data
    cagr = None
    if eps_per_year and len(eps_per_year) >= 2:
        # Get sorted list of years (newest first)
        sorted_years = sorted(eps_per_year.keys(), reverse=True)
        
        # We need at least 2 years to calculate growth
        if len(sorted_years) >= 4:
            # Take up to 6 years (for 5-year growth)
            years_to_use = sorted_years[:6]
            # Sort chronologically for calculation
            years_to_use_sorted = sorted(years_to_use)
            start_year = years_to_use_sorted[0]
            end_year = years_to_use_sorted[-1]
            start_eps = eps_per_year[start_year]
            end_eps = eps_per_year[end_year]
            years_between = int(end_year) - int(start_year)
        
            if start_eps != 0 and years_between >= 4:
                cagr = (end_eps / start_eps) ** (1 / years_between) - 1
                

    return {
        f"EPS Growth {CURRENT_YEAR}": round(growth_actual_to_est, 4) if growth_actual_to_est is not None else None,
        f"EPS Growth {int(CURRENT_YEAR)+1}": round(growth_est_to_est, 4) if growth_est_to_est is not None else None,
        "EPS Genomsnitt (5y)": round(cagr, 4) if cagr is not None else None
    }

# {'200DayMA': 226.3156, '50DayMA': 209.441}
def get_moving_averages(data):
	technicals = data.get("Technicals", {})

	key_map = {
		"200 Day MA": "200DayMA",
		"50 Day MA": "50DayMA",
	}

	selected = {readable: technicals.get(api_key) for readable, api_key in key_map.items()}
	return selected

# Returnerar {'FCF Yield Growth (YoY)': 0.051, 'Average FCF Yield (5y)': 0.0388}
def fcf_yield_growth_latest(data):
    cf_data = data.get("Financials", {}).get("Cash_Flow", {}).get("yearly", {})
    highlights = data.get("Highlights", {})
    balance_sheet = data.get("Financials", {}).get("Balance_Sheet", {}).get("yearly", {})

    if not cf_data or not highlights or not balance_sheet:
        return {}

    market_cap = highlights.get("MarketCapitalization")
    if not market_cap:
        return {}

    latest_date = max(balance_sheet.keys())
    latest_bs = balance_sheet[latest_date]

    net_debt = latest_bs.get("netDebt")

    try:
        market_cap = float(market_cap)
        net_debt = float(net_debt)
    except (TypeError, ValueError):
        return {}

	# formel "enterprise value"
    ev = market_cap + net_debt
    
    if ev <= 0:
        return {}

    fcf_yields = []
    for year, values in cf_data.items():
        try:
            fcf = float(values.get("freeCashFlow", 0))
            yield_val = fcf / ev
            fcf_yields.append((year, yield_val))
        except (TypeError, ValueError):
            continue

    # Sortera efter år, extrahera år från datumsträngen
    fcf_yields.sort(key=lambda x: int(x[0][:4]), reverse=True)

    if len(fcf_yields) < 2:
        return {}

    latest_yield = fcf_yields[0]

    last_5_yields = [y for _, y in fcf_yields[:5]]
    avg_5y_yield = sum(last_5_yields) / len(last_5_yields) if last_5_yields else None

    return {
        "FCF Yield": round(latest_yield[1], 4),
        "FCF Yield Genomsnitt (5y)": round(avg_5y_yield, 4) if avg_5y_yield is not None else None
    }

# eps de senaste 5 åren 
def calculate_eps_per_year(data):
    def safe_float(val):
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    # Hämta EPS från "Earnings" -> "Annual"
    annual_eps_data = data.get("Earnings", {}).get("Annual", {})

    result_eps = {}
    # Vi går bakåt från föregående år i 5 år
    target_years = [str(year) for year in range(int(CURRENT_YEAR) - 1, int(CURRENT_YEAR) - 6, -1)]

    for entry_date, report in annual_eps_data.items():
        year = entry_date[:4]
        if year in target_years:
            eps = safe_float(report.get("epsActual"))
            result_eps[year] = round(eps, 4) if eps is not None else None

    # Se till att alla target_years finns med (även om värdet blir None)
    for year in target_years:
        if year not in result_eps:
            result_eps[year] = None

    return result_eps

# closing prices  
def get_average_annual_close_prices(data, ticker):
    start_year = int(CURRENT_YEAR) - 5
    end_year = int(CURRENT_YEAR) - 1
    cutoff_date = f"{end_year}-12-31"

    # Group adjusted close prices by year
    yearly_prices = defaultdict(list)
    
    for entry in data:
        date = entry['date']
        if date > cutoff_date:
            continue  # Skip dates beyond the cutoff

        year = date[:4]
        adjusted_close = entry.get('adjusted_close')
        if adjusted_close is not None:
            yearly_prices[year].append(float(adjusted_close))
    
    results = {}
    for year in range(start_year, end_year + 1):
        year_str = str(year)
        prices = yearly_prices.get(year_str, [])
        
        if prices:
            average_close = sum(prices) / len(prices)
            results[year_str] = {
                "average_close": round(average_close, 4),
                "data_points": len(prices)
            }
        else:
            print(f"No price data for year {year} for {ticker}.")

    return {ticker: results}

# PE-värde, forward, genomsnitt 
def calculate_five_year_average_pe(ticker, data, price_data):
    forwardPE = data.get("Valuation", {}).get("ForwardPE", {})
    # correct
    if forwardPE == 0:
        forwardPE = None
    elif abs(forwardPE) > 125:
        forwardPE = None

    eps_data = calculate_eps_per_year(data)
    close_prices_data = get_average_annual_close_prices(price_data, ticker)
    close_prices = close_prices_data.get(ticker, {})

    pe_ratios = []
    for year in sorted(eps_data.keys()):
        eps = eps_data[year]
        close = close_prices.get(str(year), {}).get("average_close")  # Updated key name

        if eps and eps != 0 and close:
            pe = close / eps
            pe_ratios.append(pe)

    # Compute raw average
    average_pe = round(sum(pe_ratios) / len(pe_ratios), 4) if pe_ratios else None

    # filtrera bort bortom 2 std
    if pe_ratios and len(pe_ratios) >= 3:
        mean_pe = statistics.mean(pe_ratios)
        std_pe = statistics.stdev(pe_ratios)

        # Remove any value more than 2 std deviations from the mean
        filtered_pe_ratios = [pe for pe in pe_ratios if abs(pe - mean_pe) <= 2 * std_pe]

        if filtered_pe_ratios:
            average_pe = round(sum(filtered_pe_ratios) / len(filtered_pe_ratios), 4)
        else:
            average_pe = None

    # Ta bort extrema
    if average_pe > 65 or average_pe < -20:
        average_pe = None

    return {
        f"PE {CURRENT_YEAR}": forwardPE,
        "PE Genomsnitt (5y)": average_pe
    }

# andel insiders
def get_percent_insiders(data):
	percent_insiders = data.get("SharesStats", {}).get("PercentInsiders")
	return {
		"Andel Insiders": round(percent_insiders/100, 4)
	}

# {'change_in_stocks': -0.0063}
def buyback_change_latest(data):
	inc_data = data.get("Financials", {}).get("Balance_Sheet", {}).get("yearly", {})

	shares_dict = {}
	for date, values in inc_data.items():
		try:
			shares = float(values.get("commonStockSharesOutstanding", 0))
			shares_dict[date] = shares
		except (TypeError, ValueError):
			continue

	if len(shares_dict) < 2:
		return {}

	# Sortera datumen i fallande ordning (senaste först)
	sorted_quarters = sorted(shares_dict.items(), reverse=True)

	_, latest_shares = sorted_quarters[0]
	_, prev_shares = sorted_quarters[1]

	diff = latest_shares - prev_shares
	percent_change = (diff / prev_shares) if prev_shares != 0 else None

	return {
		"Förändring Antal Aktier": round(percent_change, 4) if percent_change is not None else None
	}

def buyback_extensive(data):
    try:
        # Hämta årsdata ur balansräkningen
        balance_sheet = data.get("Financials", {}).get("Balance_Sheet", {}).get("yearly", {})
        sorted_dates = sorted(balance_sheet.keys(), reverse=True)

        if len(sorted_dates) < 2:
            return {}

        # Hjälpfunktion för att hämta och konvertera aktieantal
        def get_shares(date_key):
            try:
                return float(balance_sheet[date_key].get("commonStockSharesOutstanding", 0))
            except (TypeError, ValueError):
                return 0.0

        # Hämta värden
        this_year_shares = get_shares(sorted_dates[0])
        one_year_ago_shares = get_shares(sorted_dates[1])
        three_years_ago_shares = get_shares(sorted_dates[3]) if len(sorted_dates) > 3 else None
        five_years_ago_shares = get_shares(sorted_dates[5]) if len(sorted_dates) > 5 else None

        results = {}

        # 1 år
        if one_year_ago_shares and one_year_ago_shares != 0:
            results["Förändring antal aktier 1y"] = round((this_year_shares - one_year_ago_shares) / one_year_ago_shares,4)

        # 3 år
        if three_years_ago_shares and three_years_ago_shares != 0:
            results["Förändring antal aktier 3y"] = round((this_year_shares - three_years_ago_shares) / three_years_ago_shares,4)

        # 5 år
        if five_years_ago_shares and five_years_ago_shares != 0:
            results["Förändring antal aktier 5y"] = round((this_year_shares - five_years_ago_shares) / five_years_ago_shares,4)

        return results

    except Exception as e:
        return {}


# beräknar total yield 
def total_yield(data): 
	try: 
		### Debt Paydown Yield 
		highlights = data.get("Highlights", {})
		market_cap = highlights.get("MarketCapitalization")

		balance_sheet = data.get("Financials", {}).get("Balance_Sheet", {}).get("yearly", {})
		sorted_dates = sorted(balance_sheet.keys(), reverse=True)

		latest_year = sorted_dates[0]
		second_latest_year = sorted_dates[1]

		latest_bs = balance_sheet[latest_year]
		previous_bs = balance_sheet[second_latest_year]

		latest_net_debt = float(latest_bs.get("netDebt"))
		previous_net_debt = float(previous_bs.get("netDebt"))

		# Make sure we have all necessary values
		if market_cap and latest_net_debt is not None and previous_net_debt is not None:
			change_in_net_debt = previous_net_debt - latest_net_debt
			debt_paydown_yield = change_in_net_debt / market_cap
		else:
			print("Missing data to compute Debt Paydown Yield.")

		### Buyback Yield 
		buyback_rate = buyback_change_latest(data).get("Förändring Antal Aktier")
		# positiva värden blir negativa, negativa blir positiva 
		buyback_yield_korrigerad = (-1 * buyback_rate) 
		
		### Dividend Yield 
		dividend_yield = highlights.get("DividendYield") 

		### Total Yield = dividend_yield + buyback_yield_korrigerad # + debt_paydown_yield
		total_yield = dividend_yield + buyback_yield_korrigerad #+ debt_paydown_yield

		return {
			"Total Avkastning": total_yield
		}
	except (TypeError, ValueError, KeyError, IndexError, ZeroDivisionError):
		return {}

# bruttovinstmarginal, vinst i förhållande till intäkt 
def gross_profitability(data):
    try:
        highlights = data.get("Highlights", {})
        gross_profit_ttm = float(highlights.get("GrossProfitTTM", {}))

        balance_sheet = data.get("Financials", {}).get("Balance_Sheet", {}).get("yearly", {})
        latest_year = sorted(balance_sheet.keys(), reverse=True)[0]
        total_assets = float(balance_sheet.get(latest_year, {}).get("totalAssets", {}))

        # gross profitability = gross profit / total assets 
        g_profitability = gross_profit_ttm / total_assets

        return {"Bruttovinstmarginal": round(g_profitability, 4)}
    
    except (TypeError, ValueError, KeyError, IndexError, ZeroDivisionError):
        return {}

# accruals, skillnaden mellan rapporterad inkomst och fritt kassaflöde 
def accruals(data):
    try:
        # netIncome & CashFlowFromOperations
        chash_flow = data.get("Financials", {}).get("Cash_Flow", {}).get("yearly", {})
        latest_year = sorted(chash_flow.keys(), reverse=True)[0]
        net_income = float(chash_flow.get(latest_year, {}).get("netIncome", {}))
        cash_flow_operating = float(chash_flow.get(latest_year, {}).get("totalCashFromOperatingActivities", {}))
        
        # totalAssets
        balance_sheet = data.get("Financials", {}).get("Balance_Sheet", {}).get("yearly", {})
        latest_year = sorted(balance_sheet.keys(), reverse=True)[0]
        total_Assets = float(balance_sheet.get(latest_year, {}).get("totalAssets", {}))

        # accruals = netIncome - cashFlowOperating  / totalAssets
        accruals = (net_income - cash_flow_operating) / total_Assets

        return {"Accruals": round(accruals, 4)}
    except (TypeError, ValueError, KeyError, IndexError, ZeroDivisionError):
        return {}

# tillgångstillväxt: tillväxt i totalAssets 
def asset_growth(data):
    try: 
        balance_sheet = data.get("Financials", {}).get("Balance_Sheet", {}).get("yearly", {})
        last_two_y = sorted(balance_sheet.keys(), reverse=True)[0:2]
        total_Assets_now = float(balance_sheet.get(last_two_y[0], {}).get("totalAssets", {}))
        total_Assets_then = float(balance_sheet.get(last_two_y[1], {}).get("totalAssets", {}))

        # assetGrowth = TotalAssetsNow - totalAssetsThen / totalAssetsThen
        asset_g = (total_Assets_now - total_Assets_then) / total_Assets_then
        return {"Tillgångstillväxt": round(asset_g, 4)}
    except (TypeError, ValueError, KeyError, IndexError, ZeroDivisionError):
        return {}
    
def compute_cop_at(data):
    # tröskelvärde, vissa cop_at exploderar
    THRESHOLD = 1

    try:
        # cash based operating profits
        income_statement = data.get("Financials", {}).get("Income_Statement", {}).get("yearly", {})
        balance_sheet = data.get("Financials", {}).get("Balance_Sheet", {}).get("yearly", {})

        # Ensure we have at least two years of data
        if len(income_statement) < 2 or len(balance_sheet) < 2:
            return {"cop_at": None}

        # Hämta senaste året
        sorted_years_income = sorted(income_statement.keys(), reverse=True)
        sorted_years_balance = sorted(balance_sheet.keys(), reverse=True)

        latest_year = sorted_years_income[0]
        second_latest_year = sorted_years_income[1]

        # ebit
        ebit = float(income_statement[latest_year].get("ebit", 0))

        # set ebit to operating income if ebit is None
        if ebit is None: 
            ebit = float(income_statement[latest_year].get("operatingIncome", 0))

        # deprication and amortization
        deprication_and_amortization = float(income_statement[latest_year].get("depreciationAndAmortization", 0))

        if deprication_and_amortization is None:
            deprication_and_amortization = float(income_statement[latest_year].get("reconciledDepreciation", 0))

        # Ensure total_assets_now is not zero before proceeding to avoid ZeroDivisionError later
        total_assets_now = float(balance_sheet[latest_year].get("totalAssets", 0))
        if total_assets_now == 0:
            return {"cop_at": None}

        total_liabilities_now = float(balance_sheet[latest_year].get("totalCurrentLiabilities", 0))

        total_assets_then = float(balance_sheet[second_latest_year].get("totalAssets", 0))
        total_liabilities_then = float(balance_sheet[second_latest_year].get("totalCurrentLiabilities", 0))

        working_capital_now = total_assets_now - total_liabilities_now
        working_capital_then = total_assets_then - total_liabilities_then

        # förändring i working capital, föregående år till i år
        change_in_working_capital = working_capital_now - working_capital_then

        #### cash_based_operating_profits
        cash_based_operating_profits = ebit + deprication_and_amortization - change_in_working_capital

        #### cash based operating profits to book assets
        cop_at = cash_based_operating_profits / total_assets_now

        # Apply the threshold filter
        if abs(cop_at) > THRESHOLD:
            return {"cop_at": None}
        else:
            return {"cop_at": round(cop_at, 4)}

    except (TypeError, ValueError, KeyError, IndexError, ZeroDivisionError):
        # If any error occurs, return None for cop_at
        return {"cop_at": None}

def compute_cop_at_generous(data):
    THRESHOLD = 1  # cap extreme values
    
    try:
        income_statement = data.get("Financials", {}).get("Income_Statement", {}).get("yearly", {})
        balance_sheet = data.get("Financials", {}).get("Balance_Sheet", {}).get("yearly", {})

        # Ensure we have at least two years of data
        if len(income_statement) < 2 or len(balance_sheet) < 2:
            return {"cop_at_revised": None}

        # Sort years (latest first)
        sorted_years_income = sorted(income_statement.keys(), reverse=True)
        sorted_years_balance = sorted(balance_sheet.keys(), reverse=True)

        latest_year = sorted_years_income[0]
        second_latest_year = sorted_years_income[1]

        # Extract required values
        ebit = income_statement[latest_year].get("ebit")
        if ebit is None: 
            ebit = float(income_statement[latest_year].get("operatingIncome", 0))
    
        total_assets_now = balance_sheet[latest_year].get("totalAssets")
        netReceivables_now = balance_sheet[latest_year].get("netReceivables")
        netReceivables_then = balance_sheet[second_latest_year].get("netReceivables")
        inventory_now = balance_sheet[latest_year].get("inventory")
        inventory_then = balance_sheet[second_latest_year].get("inventory")

        # If *any* required value is missing → return None
        required = [ebit, total_assets_now, netReceivables_now,
                    netReceivables_then, inventory_now, inventory_then]
        if any(v is None for v in required):
            return {"cop_at_revised": None}

        # Convert to floats
        ebit = float(ebit)
        total_assets_now = float(total_assets_now)
        netReceivables_now = float(netReceivables_now)
        netReceivables_then = float(netReceivables_then)
        inventory_now = float(inventory_now)
        inventory_then = float(inventory_then)

        # Prevent divide-by-zero
        if total_assets_now == 0:
            return {"cop_at_revised": None}

        # Changes
        change_in_netReceivables = netReceivables_now - netReceivables_then
        change_in_inventory = inventory_now - inventory_then

        # COP_AT
        numerator = ebit - change_in_netReceivables - change_in_inventory
        denominator = total_assets_now
        cop_at = numerator / denominator

        # Threshold filter
        if abs(cop_at) > THRESHOLD:
            return {"cop_at": None}
        return {"cop_at_revised": round(cop_at, 4)}

    except Exception:
        return {"cop_at_revised": None}


def get_operating_assets_helper(fundamental_data, year):
    inc_data = fundamental_data.get("Financials", {}).get("Balance_Sheet", {}).get("yearly", {})

    diff = int(CURRENT_YEAR) - year - 1
    relevant_years = sorted(inc_data.keys(), reverse=True)[diff:(diff + 2)]
    
    # Check if we have enough years of data
    if len(relevant_years) < 2:
        return [None, None]

    # totala tillgångar
    last_year_total_assets = inc_data.get(relevant_years[0], {}).get("totalAssets")
    second_latest_year_total_assets = inc_data.get(relevant_years[1], {}).get("totalAssets")
  
    # kontanter och kortfristiga investeringar
    last_year_cashAndShortTermInvestments = inc_data.get(relevant_years[0], {}).get("cashAndShortTermInvestments")
    second_latest_year_cashAndShortTermInvestments = inc_data.get(relevant_years[1], {}).get("cashAndShortTermInvestments")
    
    if None in [last_year_total_assets, second_latest_year_total_assets,
                last_year_cashAndShortTermInvestments, second_latest_year_cashAndShortTermInvestments,
                ]:
        return [None, None]
    # operativa tillgångar = totala tillgångar - kontanter och kortfristiga investeringar
    last_year_operating_assets = float(last_year_total_assets) - float(last_year_cashAndShortTermInvestments)
    second_latest_year_operating_assets = float(second_latest_year_total_assets) - float(second_latest_year_cashAndShortTermInvestments)

    return [last_year_operating_assets, second_latest_year_operating_assets]

# hjälpfunktion för NOA, beräknar operativa skulder
def get_operating_liabilities_helper(fundamental_data, year):
    inc_data = fundamental_data.get("Financials", {}).get("Balance_Sheet", {}).get("yearly", {})

    diff = int(CURRENT_YEAR) - year - 1
    relevant_years = sorted(inc_data.keys(), reverse=True)[diff:(diff + 2)]
    
    # Check if we have enough years of data
    if len(relevant_years) < 2:
        return [None, None]

    # totala tillgångar
    last_year_total_assets = inc_data.get(relevant_years[0], {}).get("totalAssets")
    second_latest_year_total_assets = inc_data.get(relevant_years[1], {}).get("totalAssets")

    # kortfristiga och långfristiga skulder
    last_year_shortLongTermDebtTotal = inc_data.get(relevant_years[0], {}).get("shortLongTermDebtTotal")
    second_latest_year_shortLongTermDebtTotal = inc_data.get(relevant_years[1], {}).get("shortLongTermDebtTotal")

    # totala aktieägares eget kapital
    last_year_totalStockholderEquity = inc_data.get(relevant_years[0], {}).get("totalStockholderEquity")
    second_latest_year_totalStockholderEquity = inc_data.get(relevant_years[1], {}).get("totalStockholderEquity")

    if None in [last_year_total_assets, second_latest_year_total_assets,
                last_year_shortLongTermDebtTotal, second_latest_year_shortLongTermDebtTotal,
                last_year_totalStockholderEquity, second_latest_year_totalStockholderEquity]:
        return [None, None]

    # operativa skulder = totala tillgångar - totala aktieägares eget kapital - kort- och långfristiga skulder
    last_year_operating_liabilities = float(last_year_total_assets) - float(last_year_totalStockholderEquity) - float(last_year_shortLongTermDebtTotal)
    second_latest_year_operating_liabilities = float(second_latest_year_total_assets) - float(second_latest_year_totalStockholderEquity) - float(second_latest_year_shortLongTermDebtTotal)

    return [last_year_operating_liabilities, second_latest_year_operating_liabilities]

# hjälpfunktion för NOA, beräknar totala tillgångar
def get_total_assets_helper(fundamental_data, year):
    inc_data = fundamental_data.get("Financials", {}).get("Balance_Sheet", {}).get("yearly", {})

    diff = int(CURRENT_YEAR) - year - 1
    relevant_years = sorted(inc_data.keys(), reverse=True)[diff:(diff + 3)]
    
    # Check if we have enough years of data
    if len(relevant_years) < 3:
        return [None, None, None]

    last_year_total_assets = inc_data.get(relevant_years[0], {}).get("totalAssets")
    second_latest_year_total_assets = inc_data.get(relevant_years[1], {}).get("totalAssets")
    third_latest_year_total_assets = inc_data.get(relevant_years[2], {}).get("totalAssets")

    if None in [last_year_total_assets, second_latest_year_total_assets, third_latest_year_total_assets]:
        return [None, None, None]

    return [last_year_total_assets, second_latest_year_total_assets, third_latest_year_total_assets]

# NOA
def get_NOA(fundamental_data):
    year = int(CURRENT_YEAR) - 1
    operating_assets = get_operating_assets_helper(fundamental_data, year)
    operating_liabilities = get_operating_liabilities_helper(fundamental_data, year)
    total_assets = get_total_assets_helper(fundamental_data, year)
    
    if None in operating_assets + operating_liabilities + total_assets:
        return {
            "NOA_GR1A": None
        }

    if total_assets[1] == 0 or total_assets[2] == 0:
        return {"NOA_GR1A": None}
    
    # NOA_t = årets operativa tillgångar - årets operativa skulder / föregående års totala tillgångar
    last_year_NOA = float((operating_assets[0] - operating_liabilities[0])) / float(total_assets[1])

    # NOA_t-1 = föregående års operativa tillgångar - föregående års operativa skulder / året före föregående års totala tillgångar
    second_latest_year_NOA = float((operating_assets[1] - operating_liabilities[1])) / float(total_assets[2])
    
    noa_gra = last_year_NOA - second_latest_year_NOA
    
    return {
        "NOA_GR1A": round(noa_gra, 4)
    }
