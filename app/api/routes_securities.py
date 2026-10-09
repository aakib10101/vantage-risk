"""Securities routes — search, prices, financials, benchmarks."""

import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.services.data_provider import provider, DataProviderError
from app.services import price_cache

router = APIRouter(prefix="/securities", tags=["securities"])


@router.get("/search")
async def search_securities(q: str = Query(..., min_length=1)):
    """Symbol/name lookup."""
    try:
        results = provider.search(q)
        return {"results": results}
    except DataProviderError as e:
        raise HTTPException(status_code=503, detail=str(e), headers={"X-Error-Code": "PROVIDER_UNAVAILABLE"})


@router.get("/{symbol}/prices")
async def get_prices(
    symbol: str,
    start: str = Query(None, description="YYYY-MM-DD"),
    end: str = Query(None, description="YYYY-MM-DD"),
    frequency: str = Query("daily", description="daily|weekly|monthly"),
    db: AsyncSession = Depends(get_db),
):
    """Historical prices (cache-or-fetch)."""
    end_date = datetime.date.fromisoformat(end) if end else datetime.date.today()
    start_date = datetime.date.fromisoformat(start) if start else end_date - datetime.timedelta(days=365 * 3)

    if start_date >= end_date:
        raise HTTPException(status_code=422, detail="start must be before end")

    try:
        df = await price_cache.get_or_fetch(db, symbol, start_date, end_date)
    except DataProviderError as e:
        raise HTTPException(status_code=503, detail=str(e), headers={"X-Error-Code": "PROVIDER_UNAVAILABLE"})

    # Resample if needed
    if frequency in ("weekly", "monthly"):
        import pandas as pd
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        rule = "W" if frequency == "weekly" else "ME"
        df = df.resample(rule).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "adj_close": "last",
            "volume": "sum",
        }).dropna().reset_index()
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    return {"symbol": symbol, "frequency": frequency, "data": df.to_dict(orient="records")}


@router.get("/{symbol}/financials")
async def get_financials(symbol: str):
    """Revenue, earnings, assets, liabilities, debt, cash flow."""
    try:
        data = provider.get_financials(symbol)
        return data
    except DataProviderError as e:
        raise HTTPException(status_code=503, detail=str(e), headers={"X-Error-Code": "PROVIDER_UNAVAILABLE"})


@router.get("/benchmarks", name="list_benchmarks")
async def list_benchmarks():
    """List available benchmarks."""
    return {
        "benchmarks": [
            {"symbol": "^GSPC", "name": "S&P 500"},
            {"symbol": "^IXIC", "name": "NASDAQ Composite"},
            {"symbol": "^DJI", "name": "Dow Jones Industrial Average"},
            {"symbol": "^NSEI", "name": "NIFTY 50"},
            {"symbol": "^FTSE", "name": "FTSE 100"},
            {"symbol": "^N225", "name": "Nikkei 225"},
            {"symbol": "^STOXX50E", "name": "EURO STOXX 50"},
        ]
    }
