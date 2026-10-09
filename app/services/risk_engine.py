"""
Vantage Risk — Risk Engine

Pure functions: pandas/numpy in, dicts/floats out.
NO FastAPI or SQLAlchemy imports allowed here.
Every formula from the spec (§8), unit-testable in isolation.
"""

import numpy as np
import pandas as pd
from scipy import stats

TRADING_DAYS = 252


# ---------------------------------------------------------------------------
# §8.1  Performance metrics
# ---------------------------------------------------------------------------

def compute_performance(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series | None = None,
    rf: float = 0.03,
) -> dict:
    """Compute full performance metrics for a portfolio return series (log returns)."""
    n_days = len(portfolio_returns)
    if n_days < 2:
        return _empty_performance()

    # Total return (from cumulative log return)
    cum_log_return = portfolio_returns.sum()
    total_return = np.exp(cum_log_return) - 1

    # CAGR
    cagr = (1 + total_return) ** (TRADING_DAYS / n_days) - 1

    # Annualized volatility
    volatility = portfolio_returns.std() * np.sqrt(TRADING_DAYS)

    # Annualized return (simple mean * 252)
    ann_return = portfolio_returns.mean() * TRADING_DAYS

    # Sharpe ratio
    sharpe = (ann_return - rf) / volatility if volatility > 1e-12 else 0.0

    # Sortino ratio
    downside = portfolio_returns[portfolio_returns < 0]
    downside_deviation = np.sqrt((downside**2).mean()) * np.sqrt(TRADING_DAYS) if len(downside) > 0 else 1e-12
    sortino = (ann_return - rf) / downside_deviation

    result = {
        "total_return": float(total_return),
        "cagr": float(cagr),
        "volatility": float(volatility),
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "alpha": None,
        "beta": None,
        "information_ratio": None,
    }

    # Benchmark-relative metrics
    if benchmark_returns is not None and len(benchmark_returns) > 0:
        # Align lengths
        min_len = min(len(portfolio_returns), len(benchmark_returns))
        pf_r = portfolio_returns.iloc[:min_len].values
        bm_r = benchmark_returns.iloc[:min_len].values

        # Beta
        cov_pb = np.cov(pf_r, bm_r, ddof=1)
        beta = cov_pb[0, 1] / cov_pb[1, 1] if cov_pb[1, 1] > 1e-18 else 0.0

        # Alpha (Jensen's / CAPM)
        ann_benchmark_return = bm_r.mean() * TRADING_DAYS
        alpha = ann_return - (rf + beta * (ann_benchmark_return - rf))

        # Information ratio
        active = pf_r - bm_r
        tracking_error = np.std(active, ddof=1) * np.sqrt(TRADING_DAYS)
        information_ratio = (np.mean(active) * TRADING_DAYS) / tracking_error if tracking_error > 1e-12 else 0.0

        result["alpha"] = float(alpha)
        result["beta"] = float(beta)
        result["information_ratio"] = float(information_ratio)

    return result


def _empty_performance() -> dict:
    return {
        "total_return": 0.0, "cagr": 0.0, "volatility": 0.0, "sharpe": 0.0,
        "sortino": 0.0, "alpha": None, "beta": None, "information_ratio": None,
    }


# ---------------------------------------------------------------------------
# §8.2  VaR / CVaR
# ---------------------------------------------------------------------------

def historical_var(
    portfolio_returns: pd.Series,
    confidence: float = 0.95,
    horizon: int = 1,
) -> dict:
    """Historical VaR using rolling horizon-day sum of log returns (overlapping windows)."""
    if horizon == 1:
        sorted_returns = portfolio_returns
    else:
        sorted_returns = portfolio_returns.rolling(horizon).sum().dropna()

    if len(sorted_returns) == 0:
        return {"var": 0.0, "cvar": 0.0}

    cutoff = np.percentile(sorted_returns, (1 - confidence) * 100)
    var_val = -cutoff
    tail = sorted_returns[sorted_returns <= cutoff]
    cvar = -tail.mean() if len(tail) > 0 else var_val

    return {"var": float(var_val), "cvar": float(cvar)}


def parametric_var(
    mu_daily: float,
    sigma_daily: float,
    confidence: float = 0.95,
    horizon: int = 1,
) -> dict:
    """Parametric (Gaussian) VaR using scipy.stats.norm."""
    mu_h = mu_daily * horizon
    sigma_h = sigma_daily * np.sqrt(horizon)
    z = stats.norm.ppf(1 - confidence)  # negative
    var_val = -(mu_h + z * sigma_h)
    alpha = 1 - confidence
    cvar = -(mu_h - sigma_h * stats.norm.pdf(z) / alpha)

    return {"var": float(var_val), "cvar": float(cvar)}


# ---------------------------------------------------------------------------
# §8.3  Max drawdown
# ---------------------------------------------------------------------------

def compute_drawdown(portfolio_returns: pd.Series) -> dict:
    """Compute max drawdown, duration, and full drawdown series from log returns."""
    wealth = np.exp(portfolio_returns.cumsum())
    wealth = pd.Series(np.concatenate([[1.0], wealth.values]))
    running_max = wealth.cummax()
    drawdown = wealth / running_max - 1
    max_drawdown = drawdown.min()

    # Drawdown duration: longest run from a peak to recovery
    in_dd = drawdown < -1e-10
    max_duration = 0
    current_duration = 0
    recovered = True

    for i in range(len(in_dd)):
        if in_dd.iloc[i]:
            current_duration += 1
        else:
            if current_duration > max_duration:
                max_duration = current_duration
            current_duration = 0

    if current_duration > 0:
        if current_duration > max_duration:
            max_duration = current_duration
        recovered = False

    return {
        "max_drawdown": float(max_drawdown),
        "drawdown_duration_days": int(max_duration),
        "drawdown_recovered": recovered,
        "drawdown_series": drawdown.tolist(),
        "wealth_index": wealth.tolist(),
    }


# ---------------------------------------------------------------------------
# §8.4  Rolling metrics
# ---------------------------------------------------------------------------

def rolling_volatility(
    portfolio_returns: pd.Series, window: int = 21
) -> pd.Series:
    """Annualized rolling standard deviation."""
    return portfolio_returns.rolling(window).std() * np.sqrt(TRADING_DAYS)


def rolling_sharpe(
    portfolio_returns: pd.Series, window: int = 21, rf: float = 0.03
) -> pd.Series:
    """Rolling Sharpe ratio."""
    roll_mean = portfolio_returns.rolling(window).mean() * TRADING_DAYS
    roll_std = portfolio_returns.rolling(window).std() * np.sqrt(TRADING_DAYS)
    return (roll_mean - rf) / roll_std.replace(0, np.nan)


def rolling_beta(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    window: int = 21,
) -> pd.Series:
    """Rolling beta: rolling_cov(p, b) / rolling_var(b)."""
    min_len = min(len(portfolio_returns), len(benchmark_returns))
    pf = portfolio_returns.iloc[:min_len].reset_index(drop=True)
    bm = benchmark_returns.iloc[:min_len].reset_index(drop=True)

    roll_cov = pf.rolling(window).cov(bm)
    roll_var = bm.rolling(window).var()
    return roll_cov / roll_var.replace(0, np.nan)


# ---------------------------------------------------------------------------
# §8.5  Correlation & Covariance
# ---------------------------------------------------------------------------

def compute_correlation(returns_df: pd.DataFrame) -> dict:
    """Asset-level correlation and annualized covariance matrices."""
    corr = returns_df.corr()
    cov = returns_df.cov() * TRADING_DAYS

    return {
        "symbols": list(returns_df.columns),
        "correlation_matrix": corr.values.tolist(),
        "covariance_matrix": cov.values.tolist(),
    }


# ---------------------------------------------------------------------------
# §8.6  Risk contribution (Euler decomposition)
# ---------------------------------------------------------------------------

def compute_risk_contribution(
    returns_df: pd.DataFrame,
    weights: np.ndarray,
) -> dict:
    """
    Euler decomposition of portfolio volatility.
    Σ = annualized covariance, w = weight vector
    MCTR_i = (Σw)_i / σ_p
    CCTR_i = w_i · MCTR_i
    Identity: Σ_i CCTR_i = σ_p  (Euler's theorem)
    """
    cov_annual = returns_df.cov().values * TRADING_DAYS
    w = np.array(weights, dtype=np.float64)
    sigma_p = np.sqrt(w @ cov_annual @ w)

    if sigma_p < 1e-18:
        n = len(w)
        return {
            "portfolio_volatility": 0.0,
            "contributions": [
                {
                    "symbol": returns_df.columns[i],
                    "weight": float(w[i]),
                    "marginal_contribution": 0.0,
                    "component_contribution": 0.0,
                    "percentage_contribution": 0.0,
                }
                for i in range(n)
            ],
        }

    mctr = (cov_annual @ w) / sigma_p
    cctr = w * mctr

    contributions = []
    for i, col in enumerate(returns_df.columns):
        contributions.append({
            "symbol": col,
            "weight": float(w[i]),
            "marginal_contribution": float(mctr[i]),
            "component_contribution": float(cctr[i]),
            "percentage_contribution": float(cctr[i] / sigma_p) if sigma_p > 1e-12 else 0.0,
        })

    return {
        "portfolio_volatility": float(sigma_p),
        "contributions": contributions,
    }


# ---------------------------------------------------------------------------
# §8.7  Equity curve
# ---------------------------------------------------------------------------

def compute_equity_curve(
    portfolio_returns: pd.Series,
    dates: list[str],
    benchmark_returns: pd.Series | None = None,
    start_value: float = 100.0,
) -> dict:
    """Cumulative wealth index for portfolio (and benchmark), rebased to start_value."""
    pf_wealth = np.exp(portfolio_returns.cumsum()) * start_value
    pf_values = np.concatenate([[start_value], pf_wealth.values]).tolist()

    dd_info = compute_drawdown(portfolio_returns)

    bm_values = None
    if benchmark_returns is not None and len(benchmark_returns) > 0:
        min_len = min(len(portfolio_returns), len(benchmark_returns))
        bm_wealth = np.exp(benchmark_returns.iloc[:min_len].cumsum()) * start_value
        bm_values = np.concatenate([[start_value], bm_wealth.values]).tolist()

    return {
        "dates": dates,
        "portfolio_values": pf_values,
        "benchmark_values": bm_values,
        "drawdown": dd_info["drawdown_series"],
    }


# ---------------------------------------------------------------------------
# Downside deviation helper (used by risk endpoint)
# ---------------------------------------------------------------------------

def downside_deviation(portfolio_returns: pd.Series, mar: float = 0.0) -> float:
    """Annualized downside deviation with MAR = 0."""
    excess = portfolio_returns - mar
    downside = excess[excess < 0]
    if len(downside) == 0:
        return 0.0
    return float(np.sqrt((downside**2).mean()) * np.sqrt(TRADING_DAYS))
