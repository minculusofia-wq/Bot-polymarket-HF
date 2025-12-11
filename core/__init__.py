"""
Core Module - Logique principale du Bot HFT
"""

from .scanner import MarketScanner, MarketData
from .analyzer import OpportunityAnalyzer, Opportunity
from .order_manager import OrderManager
from .trade_manager import TradeManager, Trade, TradeStatus, TradeSide, CloseReason
from .market_maker import MarketMaker, MMConfig, MMPosition, MMStatus
from .gabagool import GabagoolEngine, GabagoolConfig, PairPosition, GabagoolStatus
from .performance import (
    setup_uvloop,
    json_dumps,
    json_loads,
    MarketCache,
    orderbook_cache,
    market_cache,
    get_performance_status,
)

__all__ = [
    "MarketScanner",
    "MarketData",
    "OpportunityAnalyzer",
    "Opportunity",
    "OrderManager",
    "TradeManager",
    "Trade",
    "TradeStatus",
    "TradeSide",
    "CloseReason",
    # Market Maker
    "MarketMaker",
    "MMConfig",
    "MMPosition",
    "MMStatus",
    # Gabagool
    "GabagoolEngine",
    "GabagoolConfig",
    "PairPosition",
    "GabagoolStatus",
    # Performance
    "setup_uvloop",
    "json_dumps",
    "json_loads",
    "MarketCache",
    "orderbook_cache",
    "market_cache",
    "get_performance_status",
]
