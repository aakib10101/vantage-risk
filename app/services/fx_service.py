"""FX rate service — currency conversion support."""

import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FXRate
from app.services.data_provider import provider, DataProviderError


async def get_fx_rate(
    db: AsyncSession,
    base: str,
    quote: str,
    date: datetime.date | None = None,
) -> float:
    """Get FX rate for base/quote pair. Uses yfinance XXXYYY=X format."""
    if base == quote:
        return 1.0

    date_str = (date or datetime.date.today()).isoformat()

    # Check cache
    stmt = select(FXRate).where(
        FXRate.base == base,
        FXRate.quote == quote,
        FXRate.date == date_str,
    )
    result = await db.execute(stmt)
    cached = result.scalar_one_or_none()
    if cached:
        return cached.rate

    # Fetch from yfinance
    try:
        symbol = f"{base}{quote}=X"
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info = ticker.info
        rate = info.get("regularMarketPrice") or info.get("previousClose")
        if rate is None:
            raise DataProviderError(f"Could not get FX rate for {base}/{quote}")

        # Cache it
        fx = FXRate(base=base, quote=quote, date=date_str, rate=float(rate))
        db.add(fx)
        await db.commit()

        return float(rate)
    except DataProviderError:
        raise
    except Exception as e:
        raise DataProviderError(f"FX rate fetch failed: {e}")
