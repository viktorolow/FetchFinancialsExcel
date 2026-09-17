import os
import requests
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import List, Tuple, Optional, Dict, Any
import time
import random

from . import company_data_extraction_EODH as eodh
from . import data_analysis as analyse

class FundamentalDataFetcher:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.current_date = datetime.today().strftime("%Y-%m-%d")
        eodh.API_KEY = api_key
        self._search_cache: Dict[str, Optional[str]] = {}
        self._search_cache_lock = Lock()
    
    def extract_tickers_from_excel(self, file_path):
        df = pd.read_excel(file_path, header=None)
        tickers = []
        company_list = []
        isin_list = []
        
        for index, row in df.iterrows():
            if index < 1:
                continue
                
            company = ""
            if len(row) > 0 and not pd.isna(row[0]):
                company = str(row[0]).strip().upper()

            ticker = ""
            if len(row) > 1 and not pd.isna(row[1]):
                ticker = str(row[1]).strip().upper()
                ticker = ''.join(c for c in ticker if c.isalpha() or c.isdigit() or c == '.' or c == '-')
                ticker = ticker.strip('.-')

            isin = None
            if len(row) > 2 and not pd.isna(row[2]):
                isin = str(row[2]).strip().upper()

            if not any([company, ticker, isin]):
                continue
            
            tickers.append(ticker)
            company_list.append(company)
            isin_list.append(isin)
                
        return company_list, tickers, isin_list
    
    def fetch_company_data(self, company_ticker):
        # Fetch fundamental data
        data = eodh.fetch_fundamentals(company_ticker)

        # Initialize empty dictionaries
        general = roce = revenue = buybacks = share_issuance = share_issuance_3y = share_issuance_5y = share_change_6m = share_change_12m = buyback_yield_kpi = net_buyback_yield_kpi = eps = total_yield = gross_p = accrual = asset_g = insiders = fcf = cop_at = cop_at_generous = noa = {}
        
        # Fetch all indicators with error handling
        try: 
            general = eodh.get_selected_highlights(data)
            print(f"Highlights fetched for {company_ticker}.")
        except Exception as e:
            print(f"Error fetching highlights: {e}")

        try: 
            roce = eodh.calculate_roce(data)
            print(f"ROCE calculated for {company_ticker}.")
        except Exception as e:
            print(f"Error calculating ROCE: {e}")

        try: 
            revenue = eodh.get_revenue_growth_data(data)
            print(f"Revenue data fetched for {company_ticker}.")
        except Exception as e:
            print(f"Error fetching revenue data: {e}")
        
        try: 
            eps = eodh.get_eps_growth_full(data)
            print(f"EPS data fetched for {company_ticker}.")
        except Exception as e:
            print(f"Error fetching EPS data: {e}")
        
        try: 
            fcf = eodh.fcf_yield_growth_latest(data)
            print(f"FCF data fetched for {company_ticker}.")
        except Exception as e:
            print(f"Error fetching FCF data: {e}")
        
        try: 
            buybacks = eodh.buyback_extensive(data)
            print(f"Buyback data fetched for {company_ticker}.")
        except Exception as e:
            print(f"Error fetching buyback data: {e}")

        try:
            share_issuance = eodh.net_share_issuance_1y(data)
            print(f"Net share issuance 1Y calculated for {company_ticker}.")
        except Exception as e:
            print(f"Error calculating net share issuance 1Y: {e}")

        try:
            share_issuance_3y = eodh.net_share_issuance_3y(data)
            print(f"Net share issuance 3Y calculated for {company_ticker}.")
        except Exception as e:
            print(f"Error calculating net share issuance 3Y: {e}")

        try:
            share_issuance_5y = eodh.net_share_issuance_5y(data)
            print(f"Net share issuance 5Y calculated for {company_ticker}.")
        except Exception as e:
            print(f"Error calculating net share issuance 5Y: {e}")

        try:
            share_change_6m = eodh.share_count_change_6m(data)
            print(f"Share count change 6M calculated for {company_ticker}.")
        except Exception as e:
            print(f"Error calculating share count change 6M: {e}")

        try:
            share_change_12m = eodh.share_count_change_12m(data)
            print(f"Share count change 12M calculated for {company_ticker}.")
        except Exception as e:
            print(f"Error calculating share count change 12M: {e}")

        try:
            buyback_yield_kpi = eodh.buyback_yield(data)
            print(f"Buyback yield calculated for {company_ticker}.")
        except Exception as e:
            print(f"Error calculating buyback yield: {e}")

        try:
            net_buyback_yield_kpi = eodh.net_buyback_yield(data)
            print(f"Net buyback yield calculated for {company_ticker}.")
        except Exception as e:
            print(f"Error calculating net buyback yield: {e}")

        try:
            insiders = eodh.get_percent_insiders(data)
            print(f"Insider data fetched for {company_ticker}.")
        except Exception as e:
            print(f"Error fetching insider data: {e}")

        try: 
            gross_p = eodh.gross_profitability(data)
            print(f"Gross profitability calculated for {company_ticker}.")
        except Exception as e:
            print(f"Error calculating gross profitability: {e}")
        
        try: 
            accrual = eodh.accruals(data)
            print(f"Accruals calculated for {company_ticker}.")
        except Exception as e:
            print(f"Error calculating accruals: {e}")

        try: 
            asset_g = eodh.asset_growth(data)
            print(f"Asset growth calculated for {company_ticker}.")
        except Exception as e:
            print(f"Error calculating asset growth: {e}")

        try: 
            total_yield = eodh.total_yield(data)
            print(f"Total yield calculated for {company_ticker}.")
        except Exception as e:
            print(f"Error calculating total yield: {e}")

        try: 
            cop_at = eodh.compute_cop_at(data)
            print(f"COP/AT calculated for {company_ticker}.")
        except Exception as e:
            print(f"Error calculating COP/AT: {e}")

        try: 
            cop_at_generous = eodh.compute_cop_at_generous(data)
            print(f"COP/AT Revised calculated for {company_ticker}.")
        except Exception as e:
            print(f"Error calculating COP/AT Revised: {e}")

        try: 
            noa = eodh.get_NOA(data)
            print(f"NOA calculated for {company_ticker}.")
        except Exception as e:
            print(f"Error calculating NOA: {e}")

        # Combine all indicators
        combined = {**general, **roce, **revenue, **eps, **fcf, **buybacks, **share_issuance, **share_issuance_3y, **share_issuance_5y, **share_change_6m, **share_change_12m, **buyback_yield_kpi, **net_buyback_yield_kpi, **insiders, **gross_p, **accrual, **asset_g, **total_yield, **cop_at, **cop_at_generous, **noa}
        other = {}
        
        return combined, other
    
    def add_company_data(self, data_df: pd.DataFrame, company_name: str, company_ticker: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        company_data = {
            'Bolag': company_name,
            'Ticker': company_ticker
        }

        company_data_separate = {
            'Ticker': company_ticker
        }

        if not company_ticker:
            data_df = pd.concat([data_df, pd.DataFrame([company_data])], ignore_index=True)
            return data_df, company_data_separate

        indicators, other = self.fetch_company_data(company_ticker)

        if indicators is not None:
            company_data.update(indicators)
            company_data_separate.update(other)
        else:
            print(f"No data found for {company_ticker}, adding empty row.")

        try:
            data_df = pd.concat([data_df, pd.DataFrame([company_data])], ignore_index=True)
        except Exception as e:
            print("Error adding to DataFrame, adding empty row instead.")
            data_df = pd.concat([data_df, pd.DataFrame([{'Ticker': company_ticker, 'Bolag': company_name}])], ignore_index=True)

        return data_df, company_data_separate
    
    def fetch_all_data(self, company_list: List[str], ticker_list: List[str], max_workers: int = 10) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
        data_df = pd.DataFrame()
        separate_data_list = []

        # Combine company names and tickers
        combined = list(zip(company_list, ticker_list))

        def process_company(args):
            company, ticker = args
            return self.add_company_data(pd.DataFrame(), company, ticker)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(process_company, combined))

        for df, separate_data in results:
            data_df = pd.concat([data_df, df], ignore_index=True)
            separate_data_list.append(separate_data)

        return data_df, separate_data_list
    
    def analyze_data(self, df, separate_data_list, factor_country="US"):
        
        # Create COP/AT Revised composite score
        df_analyzed = analyse.create_cop_at_noa_composite_score(df)

        # Calculate quality score
        df_analyzed = analyse.quality_score(df_analyzed)
        
        # Add last updated date
        df_analyzed["Last Updated"] = self.current_date
        
        return df_analyzed


    def search(self, keyword):

        url = f'https://eodhd.com/api/search/{keyword}?limit=1&api_token={self.api_key}&fmt=json'
        
        try:
            for attempt in range(5):
                response = requests.get(url, timeout=10)

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    if retry_after is not None:
                        sleep_seconds = max(float(retry_after), 1)
                    else:
                        sleep_seconds = min(2 ** attempt, 30)

                    sleep_seconds += random.uniform(0, 1)
                    time.sleep(sleep_seconds)
                    continue

                response.raise_for_status() 

                data = response.json()
                break
            else:
                return None
            
            # kontrollera att svaret är en lista med minst ett element
            if not isinstance(data, list) or len(data) == 0:
                print(f"Inget resultat för sökordet: {keyword}")
                return None

            # Kontrollera att nyckeln 'Code' finns
            company_code = data[0].get('Code')
            exchange = data[0].get('Exchange')

            ticker = f"{company_code}.{exchange}"

            if not company_code or not exchange:
                print(f"Inget fält 'Code' hittades i svaret: {data[0]}")
                return None

            return ticker

        except requests.exceptions.RequestException as e:
            print(f"Nätverksfel: {e}")
            return None
        except ValueError:
            print("Fel vid avkodning av JSON.")
            return None
        except Exception as e:
            print(f"Oväntat fel: {e}")
            return None
    
    # ger det bästa resultatet, ticker från ISIN/namn/ticker
    def resolve_ticker(self, company_name: Optional[str], fallback_ticker: str, isin: Optional[str] = None) -> str:
        for keyword in (isin, fallback_ticker, company_name):
            if keyword:
                normalized = keyword.upper()
                with self._search_cache_lock:
                    if normalized in self._search_cache:
                        cached = self._search_cache[normalized]
                        if cached:
                            return cached
                        continue
                resolved = self.search(keyword)
                resolved_upper = resolved.upper() if resolved else None
                with self._search_cache_lock:
                    self._search_cache[normalized] = resolved_upper
                if resolved_upper:
                    return resolved_upper
        return ""
    
    def process_ticker_list_using_search_api(
        self,
        ticker_list: List[str],
        company_list: List[str],
        isin_list: Optional[List[Optional[str]]] = None,
        max_workers: int = 8
    ) -> List[str]:
        results: List[str] = [""] * len(ticker_list)

        def resolve_index(idx: int) -> Tuple[int, str]:
            ticker = ticker_list[idx]
            company = company_list[idx] if idx < len(company_list) else None
            isin = isin_list[idx] if isin_list and idx < len(isin_list) else None
            resolved = self.resolve_ticker(company, ticker, isin)
            return idx, resolved

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for idx, resolved in executor.map(resolve_index, range(len(ticker_list))):
                results[idx] = resolved or ""

        return results
    
    def process_excel_file(self, input_file: str, output_file: str, max_workers: int = 10, factor_country: str = "US") -> None:
        print(f"Processing file: {input_file}")
        
        # Extract tickers from Excel file
        company_list, ticker_list, isin_list = self.extract_tickers_from_excel(input_file)

        # använd search på ticker_list
        ticker_list = self.process_ticker_list_using_search_api(ticker_list, company_list, isin_list, max_workers)

        print(f"Found {len(ticker_list)} tickers to process")
        
        # Fetch all data
        print("Fetching financial data...")
        df, separate_data_list = self.fetch_all_data(company_list, ticker_list, max_workers)
        
        # Analyze data
        print("Performing financial analysis...")
        df_analyzed = self.analyze_data(df, separate_data_list, factor_country)
        
        # Clean data before saving to Excel
        print(f"Saving results to: {output_file}")
        
        # Comprehensive data cleaning to prevent Excel XML errors
        import numpy as np
        df_cleaned = df_analyzed.copy()
        
        # Debug: Check for problematic data types and values
        print("Debug: Checking for problematic values...")
        problematic_cols = []
        for col in df_cleaned.columns:
            if df_cleaned[col].dtype == 'object':
                # Check for very long strings that might cause issues
                max_length = df_cleaned[col].astype(str).str.len().max()
                if max_length > 1000:
                    problematic_cols.append(f"{col} (long strings: max {max_length})")
            
            # Check for inf values
            if pd.api.types.is_numeric_dtype(df_cleaned[col]):
                inf_count = np.isinf(df_cleaned[col]).sum()
                if inf_count > 0:
                    problematic_cols.append(f"{col} (inf values: {inf_count})")
        
        if problematic_cols:
            print(f"Found potentially problematic columns: {problematic_cols}")
        
        # Replace inf, -inf, and NaN with None for Excel compatibility
        df_cleaned = df_cleaned.replace([float('inf'), float('-inf'), np.inf, -np.inf], None)
        
        # Handle any remaining NaN values
        df_cleaned = df_cleaned.where(pd.notnull(df_cleaned), None)
        
        # Clean column names - remove/replace problematic characters
        df_cleaned.columns = [str(col).strip().replace('/', '_').replace('\\', '_').replace('*', '_').replace('[', '_').replace(']', '_').replace(':', '_').replace('?', '_') for col in df_cleaned.columns]
        
        # Convert any complex data types to strings
        for col in df_cleaned.columns:
            if df_cleaned[col].dtype == 'object':
                df_cleaned[col] = df_cleaned[col].astype(str)
                # Replace 'None' strings back to actual None
                df_cleaned[col] = df_cleaned[col].replace('None', None)
        
        # Try writing with different engines in case of issues
        try:
            df_cleaned.to_excel(output_file, index=False, engine='openpyxl')
        except Exception as e:
            print(f"Error with openpyxl engine: {e}")
            print("Trying with xlsxwriter engine...")
            try:
                df_cleaned.to_excel(output_file, index=False, engine='xlsxwriter')
            except Exception as e2:
                print(f"Error with xlsxwriter engine: {e2}")
                # Fallback to CSV if Excel fails
                csv_file = output_file.replace('.xlsx', '.csv')
                print(f"Saving as CSV instead: {csv_file}")
                df_cleaned.to_csv(csv_file, index=False)
        print("Processing complete!") 