"""Local market research and historical strategy simulations."""

from .service import TradingLab, register_trading_tools
from .paper_trading import PaperTrading

__all__ = ["TradingLab", "register_trading_tools", "PaperTrading"]
