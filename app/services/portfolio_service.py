"""Portfolio service — holdings math, weight normalization, portfolio return computation."""

import datetime

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Portfolio, Holding
from app.services import price_cache


async def get_portfolio_returns(
    db: AsyncSession,
    portfolio: Portfolio,
    start: datetime.date | None = None,
    end: datetime.date | None = None,
) -> tuple[pd.Series, pd.DataFrame, list[str], np.ndarray, list[str]]:
    """
    Compute portfolio-level daily log returns from holdings.

    Returns:
        portfolio_returns: pd.Series of daily portfolio log returns
        returns_df: pd.DataFrame with per-asset daily log returns (columns = symbols)
        dates: list of date strings
        weights: np.ndarray of normalized weights
        symbols: list of symbols
    """
    if not portfolio.holdings:
        raise ValueError("Portfolio has no holdings")

    if end is None:
        end = datetime.date.today()
    if start is None:
        start = end - datetime.timedelta(days=365 * 3)

    symbols = [h.symbol for h in portfolio.holdings]

    # Get weights
    if portfolio.weighting_mode == "weight":
        raw_weights = [h.weight or 0.0 for h in portfolio.holdings]
    else:
        raw_weights = [h.quantity or 0.0 for h in portfolio.holdings]

    w_sum = sum(raw_weights)
    if w_sum <= 0:
        raise ValueError("Portfolio weights sum to zero")
    weights = np.array([w / w_sum for w in raw_weights])

    # Fetch prices for each holding
    price_frames = {}
    for symbol in symbols:
        df = await price_cache.get_or_fetch(db, symbol, start, end)
        price_frames[symbol] = df.set_index("date")["adj_close"]

    # Align on common dates
    price_df = pd.DataFrame(price_frames).dropna()
    if len(price_df) < 2:
        raise ValueError("Not enough overlapping price data to compute returns")

    # Log returns
    returns_df = np.log(price_df / price_df.shift(1)).dropna()
    dates = returns_df.index.tolist()

    # Portfolio returns (weighted sum)
    portfolio_returns = returns_df.values @ weights
    portfolio_returns = pd.Series(portfolio_returns, index=dates)

    return portfolio_returns, returns_df, dates, weights, symbols


async def get_benchmark_returns(
    db: AsyncSession,
    benchmark_symbol: str,
    start: datetime.date,
    end: datetime.date,
) -> pd.Series:
    """Fetch benchmark returns as a pd.Series of log returns."""
    df = await price_cache.get_or_fetch(db, benchmark_symbol, start, end)
    prices = df.set_index("date")["adj_close"]
    returns = np.log(prices / prices.shift(1)).dropna()
    return returns
