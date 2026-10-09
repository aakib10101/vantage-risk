"""Risk analytics response schemas."""

from pydantic import BaseModel


class PerformanceResponse(BaseModel):
    total_return: float
    cagr: float
    volatility: float
    sharpe: float
    sortino: float
    alpha: float | None = None
    beta: float | None = None
    information_ratio: float | None = None
    returns: dict | None = None  # {"daily": [...], "monthly": [...], "annual": [...]}


class RiskResponse(BaseModel):
    var: float
    cvar: float
    max_drawdown: float
    drawdown_duration_days: int
    drawdown_recovered: bool
    downside_deviation: float


class RollingResponse(BaseModel):
    dates: list[str]
    values: list[float | None]
    metric: str
    window: int


class CorrelationResponse(BaseModel):
    symbols: list[str]
    correlation_matrix: list[list[float]]
    covariance_matrix: list[list[float]]


class RiskContributionItem(BaseModel):
    symbol: str
    weight: float
    marginal_contribution: float
    component_contribution: float
    percentage_contribution: float


class RiskContributionResponse(BaseModel):
    portfolio_volatility: float
    contributions: list[RiskContributionItem]


class EquityCurveResponse(BaseModel):
    dates: list[str]
    portfolio_values: list[float]
    benchmark_values: list[float] | None = None
    drawdown: list[float]
