"""ORM models for Vantage Risk."""

import datetime
import uuid

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    portfolios = relationship("Portfolio", back_populates="owner", cascade="all, delete-orphan")


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    base_currency = Column(String, default="USD")
    benchmark_symbol = Column(String, default="^GSPC")  # S&P 500
    weighting_mode = Column(String, default="weight")  # "quantity" or "weight"
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="portfolios")
    holdings = relationship("Holding", back_populates="portfolio", cascade="all, delete-orphan")


class Holding(Base):
    __tablename__ = "holdings"

    id = Column(String, primary_key=True, default=_uuid)
    portfolio_id = Column(String, ForeignKey("portfolios.id"), nullable=False)
    symbol = Column(String, nullable=False)
    quantity = Column(Float, nullable=True)
    weight = Column(Float, nullable=True)
    added_at = Column(DateTime, default=datetime.datetime.utcnow)

    portfolio = relationship("Portfolio", back_populates="holdings")


class Security(Base):
    __tablename__ = "securities"

    symbol = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    exchange = Column(String, nullable=True)
    currency = Column(String, nullable=True)
    asset_type = Column(String, nullable=True)


class PriceBar(Base):
    __tablename__ = "price_bars"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, index=True)
    date = Column(String, nullable=False)  # ISO date string YYYY-MM-DD
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    adj_close = Column(Float)
    volume = Column(Float)

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_pricebar_symbol_date"),
        Index("ix_pricebar_symbol_date", "symbol", "date"),
    )


class CompanyFinancials(Base):
    __tablename__ = "company_financials"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, index=True)
    period = Column(String, nullable=True)
    revenue = Column(Float, nullable=True)
    earnings = Column(Float, nullable=True)
    total_assets = Column(Float, nullable=True)
    total_liabilities = Column(Float, nullable=True)
    total_debt = Column(Float, nullable=True)
    operating_cash_flow = Column(Float, nullable=True)
    free_cash_flow = Column(Float, nullable=True)
    fetched_at = Column(DateTime, default=datetime.datetime.utcnow)


class FXRate(Base):
    __tablename__ = "fx_rates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    base = Column(String, nullable=False)
    quote = Column(String, nullable=False)
    date = Column(String, nullable=False)
    rate = Column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint("base", "quote", "date", name="uq_fxrate_base_quote_date"),
    )
