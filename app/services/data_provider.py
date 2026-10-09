"""
Market data provider — abstract Protocol + YFinance implementation.
Provider failures raise DataProviderError → routed to HTTP 503.
"""

from __future__ import annotations

import datetime
from typing import Protocol

import pandas as pd
import yfinance as yf


class DataProviderError(Exception):
    """Raised when the underlying market data provider fails."""
    pass


class DataProvider(Protocol):
    def search(self, query: str) -> list[dict]:
        ...

    def get_prices(
        self, symbol: str, start: datetime.date, end: datetime.date
    ) -> pd.DataFrame:
        ...

    def get_financials(self, symbol: str) -> dict:
        ...


class YFinanceProvider:
    """YFinance implementation of DataProvider."""

    def search(self, query: str) -> list[dict]:
        try:
            ticker = yf.Ticker(query)
            info = ticker.info
            if not info or "symbol" not in info:
                return []
            return [{
                "symbol": info.get("symbol", query),
                "name": info.get("longName") or info.get("shortName", ""),
                "exchange": info.get("exchange", ""),
                "currency": info.get("currency", ""),
                "asset_type": info.get("quoteType", ""),
            }]
        except Exception as e:
            raise DataProviderError(f"Search failed for '{query}': {e}")

    def get_prices(
        self, symbol: str, start: datetime.date, end: datetime.date
    ) -> pd.DataFrame:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(
                start=start.isoformat(),
                end=(end + datetime.timedelta(days=1)).isoformat(),
                auto_adjust=False,
            )
            if df.empty:
                raise DataProviderError(f"No price data for '{symbol}' in [{start}, {end}]")

            df = df.reset_index()
            # Normalize column names
            df.columns = [c.lower().replace(" ", "_") for c in df.columns]
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

            rename_map = {}
            if "adj_close" not in df.columns and "adj close" in [c.replace("_", " ") for c in df.columns]:
                for c in df.columns:
                    if c.replace("_", " ") == "adj close":
                        rename_map[c] = "adj_close"
            if rename_map:
                df = df.rename(columns=rename_map)

            if "adj_close" not in df.columns:
                df["adj_close"] = df["close"]

            return df[["date", "open", "high", "low", "close", "adj_close", "volume"]]
        except DataProviderError:
            raise
        except Exception as e:
            raise DataProviderError(f"Failed to fetch prices for '{symbol}': {e}")

    def get_financials(self, symbol: str) -> dict:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            bs = ticker.balance_sheet
            cf = ticker.cashflow

            result = {
                "symbol": symbol,
                "revenue": info.get("totalRevenue"),
                "earnings": info.get("netIncomeToCommon"),
                "total_assets": None,
                "total_liabilities": None,
                "total_debt": info.get("totalDebt"),
                "operating_cash_flow": info.get("operatingCashflow"),
                "free_cash_flow": info.get("freeCashflow"),
            }

            if bs is not None and not bs.empty:
                latest = bs.iloc[:, 0]
                result["total_assets"] = latest.get("Total Assets")
                result["total_liabilities"] = latest.get("Total Liabilities Net Minority Interest")

            return result
        except Exception as e:
            raise DataProviderError(f"Failed to fetch financials for '{symbol}': {e}")


# Singleton
provider = YFinanceProvider()
