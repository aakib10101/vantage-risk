"""Portfolio CRUD routes — create, list, get, update, delete, holdings, CSV/Excel import."""

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.base import get_db
from app.db.models import Portfolio, Holding
from app.api.routes_auth import get_current_user
from app.db.models import User
from app.schemas.portfolio import (
    HoldingCreate,
    HoldingResponse,
    HoldingUpdate,
    PortfolioCreate,
    PortfolioResponse,
    PortfolioUpdate,
)
from app.services.data_provider import provider, DataProviderError

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


async def _get_portfolio_or_404(
    portfolio_id: str, user: User, db: AsyncSession
) -> Portfolio:
    """Fetch portfolio with holdings, or raise 404."""
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


@router.post("", response_model=PortfolioResponse, status_code=201)
async def create_portfolio(
    body: PortfolioCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    portfolio = Portfolio(
        user_id=user.id,
        name=body.name,
        base_currency=body.base_currency,
        benchmark_symbol=body.benchmark_symbol,
        weighting_mode=body.weighting_mode,
    )
    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)
    # Reload with holdings
    return await _get_portfolio_or_404(portfolio.id, user, db)


@router.get("", response_model=list[PortfolioResponse])
async def list_portfolios(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    stmt = (
        select(Portfolio)
        .options(selectinload(Portfolio.holdings))
        .where(Portfolio.user_id == user.id)
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{portfolio_id}", response_model=PortfolioResponse)
async def get_portfolio(
    portfolio_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_portfolio_or_404(portfolio_id, user, db)


@router.put("/{portfolio_id}", response_model=PortfolioResponse)
async def update_portfolio(
    portfolio_id: str,
    body: PortfolioUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    portfolio = await _get_portfolio_or_404(portfolio_id, user, db)
    if body.name is not None:
        portfolio.name = body.name
    if body.base_currency is not None:
        portfolio.base_currency = body.base_currency
    if body.benchmark_symbol is not None:
        portfolio.benchmark_symbol = body.benchmark_symbol
    await db.commit()
    await db.refresh(portfolio)
    return await _get_portfolio_or_404(portfolio_id, user, db)


@router.delete("/{portfolio_id}", status_code=204)
async def delete_portfolio(
    portfolio_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    portfolio = await _get_portfolio_or_404(portfolio_id, user, db)
    await db.delete(portfolio)
    await db.commit()


# ---- Holdings ----

@router.post("/{portfolio_id}/holdings", response_model=HoldingResponse, status_code=201)
async def add_holding(
    portfolio_id: str,
    body: HoldingCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    portfolio = await _get_portfolio_or_404(portfolio_id, user, db)

    # Validate symbol resolves
    try:
        results = provider.search(body.symbol)
        if not results:
            raise HTTPException(
                status_code=422,
                detail=f"Symbol '{body.symbol}' could not be resolved. Verify the ticker is valid.",
            )
    except DataProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Validate weight/quantity matches mode
    if portfolio.weighting_mode == "weight":
        if body.weight is None:
            raise HTTPException(status_code=422, detail="Portfolio is weight-based; provide 'weight'")
        holding = Holding(portfolio_id=portfolio.id, symbol=body.symbol.upper(), weight=body.weight)
    else:
        if body.quantity is None:
            raise HTTPException(status_code=422, detail="Portfolio is quantity-based; provide 'quantity'")
        holding = Holding(portfolio_id=portfolio.id, symbol=body.symbol.upper(), quantity=body.quantity)

    db.add(holding)
    await db.commit()
    await db.refresh(holding)
    return holding


@router.put("/{portfolio_id}/holdings/{holding_id}", response_model=HoldingResponse)
async def update_holding(
    portfolio_id: str,
    holding_id: str,
    body: HoldingUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_portfolio_or_404(portfolio_id, user, db)
    result = await db.execute(
        select(Holding).where(Holding.id == holding_id, Holding.portfolio_id == portfolio_id)
    )
    holding = result.scalar_one_or_none()
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")

    if body.quantity is not None:
        holding.quantity = body.quantity
    if body.weight is not None:
        holding.weight = body.weight
    await db.commit()
    await db.refresh(holding)
    return holding


@router.delete("/{portfolio_id}/holdings/{holding_id}", status_code=204)
async def delete_holding(
    portfolio_id: str,
    holding_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_portfolio_or_404(portfolio_id, user, db)
    result = await db.execute(
        select(Holding).where(Holding.id == holding_id, Holding.portfolio_id == portfolio_id)
    )
    holding = result.scalar_one_or_none()
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    await db.delete(holding)
    await db.commit()


# ---- CSV/Excel Import ----

@router.post("/{portfolio_id}/import", status_code=201)
async def import_holdings(
    portfolio_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """CSV/Excel upload — bulk holdings. Expects columns: symbol, weight (or quantity)."""
    portfolio = await _get_portfolio_or_404(portfolio_id, user, db)

    content = await file.read()
    errors = []
    holdings_to_add = []

    if file.filename and file.filename.endswith((".xlsx", ".xls")):
        import pandas as pd
        try:
            df = pd.read_excel(io.BytesIO(content))
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Could not parse Excel file: {e}")
    else:
        try:
            text = content.decode("utf-8")
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
            if not rows:
                raise HTTPException(status_code=422, detail="CSV is empty")
            import pandas as pd
            df = pd.DataFrame(rows)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Could not parse CSV: {e}")

    # Normalize columns
    df.columns = [c.strip().lower() for c in df.columns]

    if "symbol" not in df.columns:
        raise HTTPException(status_code=422, detail="CSV must have a 'symbol' column")

    value_col = "weight" if portfolio.weighting_mode == "weight" else "quantity"
    if value_col not in df.columns:
        raise HTTPException(
            status_code=422,
            detail=f"CSV must have a '{value_col}' column (portfolio mode: {portfolio.weighting_mode})",
        )

    for idx, row in df.iterrows():
        line_num = idx + 2  # 1-indexed + header
        symbol = str(row["symbol"]).strip().upper()
        try:
            val = float(row[value_col])
        except (ValueError, TypeError):
            errors.append({"line": line_num, "symbol": symbol, "error": f"Invalid {value_col} value"})
            continue

        if portfolio.weighting_mode == "weight" and not (0 < val <= 1):
            errors.append({"line": line_num, "symbol": symbol, "error": "weight must be in (0, 1]"})
            continue
        if portfolio.weighting_mode == "quantity" and val <= 0:
            errors.append({"line": line_num, "symbol": symbol, "error": "quantity must be > 0"})
            continue

        if portfolio.weighting_mode == "weight":
            holdings_to_add.append(Holding(portfolio_id=portfolio.id, symbol=symbol, weight=val))
        else:
            holdings_to_add.append(Holding(portfolio_id=portfolio.id, symbol=symbol, quantity=val))

    if errors:
        raise HTTPException(status_code=422, detail={"message": "Validation errors in import", "errors": errors})

    for h in holdings_to_add:
        db.add(h)
    await db.commit()

    return {"imported": len(holdings_to_add), "message": f"Successfully imported {len(holdings_to_add)} holdings"}
