"""
Price cache — cache-or-fetch layer over PriceBar table.
Rule: always compute off the cache, never off a live response.
"""

import datetime

import pandas as pd
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PriceBar
from app.services.data_provider import provider, DataProviderError


async def get_or_fetch(
    db: AsyncSession,
    symbol: str,
    start: datetime.date,
    end: datetime.date,
) -> pd.DataFrame:
    """
    Read PriceBar for [start, end]. Identify missing dates.
    Fetch only the gap from the provider, upsert, return from DB.
    """
    start_str = start.isoformat()
    end_str = end.isoformat()

    # Check what we already have
    stmt = (
        select(PriceBar)
        .where(PriceBar.symbol == symbol)
        .where(PriceBar.date >= start_str)
        .where(PriceBar.date <= end_str)
        .order_by(PriceBar.date)
    )
    result = await db.execute(stmt)
    cached_rows = result.scalars().all()

    cached_dates = {row.date for row in cached_rows}

    # Determine if we need to fetch
    # Simple heuristic: if we have fewer than expected trading days, fetch
    expected_days = (end - start).days * 5 / 7  # rough weekday estimate
    needs_fetch = len(cached_dates) < max(1, expected_days * 0.5)

    if needs_fetch:
        try:
            df = provider.get_prices(symbol, start, end)
            # Upsert new rows
            for _, row in df.iterrows():
                date_str = str(row["date"])
                if date_str not in cached_dates:
                    bar = PriceBar(
                        symbol=symbol,
                        date=date_str,
                        open=float(row["open"]) if pd.notna(row["open"]) else None,
                        high=float(row["high"]) if pd.notna(row["high"]) else None,
                        low=float(row["low"]) if pd.notna(row["low"]) else None,
                        close=float(row["close"]) if pd.notna(row["close"]) else None,
                        adj_close=float(row["adj_close"]) if pd.notna(row["adj_close"]) else None,
                        volume=float(row["volume"]) if pd.notna(row["volume"]) else None,
                    )
                    db.add(bar)
            await db.commit()

            # Re-read from DB for consistency
            result = await db.execute(stmt)
            cached_rows = result.scalars().all()
        except DataProviderError:
            if len(cached_rows) == 0:
                raise
            # Fall through to return whatever we have cached

    # Convert to DataFrame
    records = [{
        "date": row.date,
        "open": row.open,
        "high": row.high,
        "low": row.low,
        "close": row.close,
        "adj_close": row.adj_close,
        "volume": row.volume,
    } for row in cached_rows]

    if not records:
        raise DataProviderError(f"No price data available for '{symbol}' in [{start}, {end}]")

    return pd.DataFrame(records).sort_values("date").reset_index(drop=True)
