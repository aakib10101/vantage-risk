"""Risk analytics routes — performance, risk, rolling, correlation, risk-contribution, equity-curve."""

import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.base import get_db
from app.db.models import Portfolio, User
from app.api.routes_auth import get_current_user
from app.services import portfolio_service
from app.services.data_provider import DataProviderError
from app.services.risk_engine import (
    compute_performance,
    historical_var,
    parametric_var,
    compute_drawdown,
    rolling_volatility,
    rolling_sharpe,
    rolling_beta,
    compute_correlation,
    compute_risk_contribution,
    compute_equity_curve,
    downside_deviation,
)

router = APIRouter(prefix="/portfolios", tags=["risk"])


async def _load_portfolio(portfolio_id: str, user: User, db: AsyncSession) -> Portfolio:
    stmt = (
        select(Portfolio)
        .options(selectinload(Portfolio.holdings))
        .where(Portfolio.id == portfolio_id, Portfolio.user_id == user.id)
    )
    result = await db.execute(stmt)
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio


def _parse_dates(start: str | None, end: str | None):
    end_date = datetime.date.fromisoformat(end) if end else datetime.date.today()
    start_date = datetime.date.fromisoformat(start) if start else end_date - datetime.timedelta(days=365 * 3)
    return start_date, end_date


@router.get("/{portfolio_id}/performance")
async def get_performance(
    portfolio_id: str,
    start: str = Query(None),
    end: str = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    portfolio = await _load_portfolio(portfolio_id, user, db)
    start_date, end_date = _parse_dates(start, end)

    try:
        pf_returns, returns_df, dates, weights, symbols = await portfolio_service.get_portfolio_returns(
            db, portfolio, start_date, end_date
        )
    except DataProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Fetch benchmark returns if configured
    benchmark_returns = None
    if portfolio.benchmark_symbol:
        try:
            benchmark_returns = await portfolio_service.get_benchmark_returns(
                db, portfolio.benchmark_symbol, start_date, end_date
            )
        except Exception:
            pass  # Non-fatal

    result = compute_performance(pf_returns, benchmark_returns, rf=0.03)
    return result


@router.get("/{portfolio_id}/risk")
async def get_risk(
    portfolio_id: str,
    confidence: float = Query(0.95, ge=0.5, le=0.999),
    horizon: int = Query(1, ge=1, le=252),
    method: str = Query("historical", description="historical|parametric"),
    start: str = Query(None),
    end: str = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    portfolio = await _load_portfolio(portfolio_id, user, db)
    start_date, end_date = _parse_dates(start, end)

    try:
        pf_returns, returns_df, dates, weights, symbols = await portfolio_service.get_portfolio_returns(
            db, portfolio, start_date, end_date
        )
    except DataProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if method == "parametric":
        var_result = parametric_var(
            pf_returns.mean(), pf_returns.std(), confidence, horizon
        )
    else:
        var_result = historical_var(pf_returns, confidence, horizon)

    dd = compute_drawdown(pf_returns)
    dd_dev = downside_deviation(pf_returns)

    return {
        "var": var_result["var"],
        "cvar": var_result["cvar"],
        "max_drawdown": dd["max_drawdown"],
        "drawdown_duration_days": dd["drawdown_duration_days"],
        "drawdown_recovered": dd["drawdown_recovered"],
        "downside_deviation": dd_dev,
    }


@router.get("/{portfolio_id}/rolling")
async def get_rolling(
    portfolio_id: str,
    metric: str = Query("volatility", description="volatility|sharpe|beta"),
    window: int = Query(21, ge=5, le=252),
    start: str = Query(None),
    end: str = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    portfolio = await _load_portfolio(portfolio_id, user, db)
    start_date, end_date = _parse_dates(start, end)

    try:
        pf_returns, returns_df, dates, weights, symbols = await portfolio_service.get_portfolio_returns(
            db, portfolio, start_date, end_date
        )
    except DataProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if metric == "volatility":
        values = rolling_volatility(pf_returns, window)
    elif metric == "sharpe":
        values = rolling_sharpe(pf_returns, window)
    elif metric == "beta":
        if not portfolio.benchmark_symbol:
            raise HTTPException(status_code=422, detail="No benchmark configured for rolling beta")
        try:
            bm_returns = await portfolio_service.get_benchmark_returns(
                db, portfolio.benchmark_symbol, start_date, end_date
            )
        except DataProviderError as e:
            raise HTTPException(status_code=503, detail=str(e))
        values = rolling_beta(pf_returns, bm_returns, window)
    else:
        raise HTTPException(status_code=422, detail="metric must be volatility, sharpe, or beta")

    values_list = [None if v != v else float(v) for v in values]  # NaN → None

    return {"dates": dates, "values": values_list, "metric": metric, "window": window}


@router.get("/{portfolio_id}/correlation")
async def get_correlation(
    portfolio_id: str,
    start: str = Query(None),
    end: str = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    portfolio = await _load_portfolio(portfolio_id, user, db)
    start_date, end_date = _parse_dates(start, end)

    try:
        pf_returns, returns_df, dates, weights, symbols = await portfolio_service.get_portfolio_returns(
            db, portfolio, start_date, end_date
        )
    except DataProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return compute_correlation(returns_df)


@router.get("/{portfolio_id}/risk-contribution")
async def get_risk_contribution(
    portfolio_id: str,
    start: str = Query(None),
    end: str = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    portfolio = await _load_portfolio(portfolio_id, user, db)
    start_date, end_date = _parse_dates(start, end)

    try:
        pf_returns, returns_df, dates, weights, symbols = await portfolio_service.get_portfolio_returns(
            db, portfolio, start_date, end_date
        )
    except DataProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return compute_risk_contribution(returns_df, weights)


@router.get("/{portfolio_id}/equity-curve")
async def get_equity_curve(
    portfolio_id: str,
    start: str = Query(None),
    end: str = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    portfolio = await _load_portfolio(portfolio_id, user, db)
    start_date, end_date = _parse_dates(start, end)

    try:
        pf_returns, returns_df, dates, weights, symbols = await portfolio_service.get_portfolio_returns(
            db, portfolio, start_date, end_date
        )
    except DataProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    benchmark_returns = None
    if portfolio.benchmark_symbol:
        try:
            benchmark_returns = await portfolio_service.get_benchmark_returns(
                db, portfolio.benchmark_symbol, start_date, end_date
            )
        except Exception:
            pass

    return compute_equity_curve(pf_returns, dates, benchmark_returns)
