"""
Order Executor - Exécute les trades automatiquement

Fonctionnalités:
1. Reçoit les opportunités de l'analyzer
2. Vérifie les conditions de trading
3. Place les ordres bilatéraux (YES + NO)
4. Monitore l'exécution
5. Gère les erreurs et retries
"""

import asyncio
from typing import Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from core.analyzer import Opportunity, OpportunityAction
from core.order_manager import OrderManager, ActiveOrder
from api.private import PolymarketPrivateClient, PolymarketCredentials
from api.private.polymarket_private import OrderSide
from config import get_settings, get_trading_params, TradingParams


class ExecutorState(Enum):
    """États de l'executor."""
    STOPPED = "stopped"
    READY = "ready"
    EXECUTING = "executing"
    PAUSED = "paused"


@dataclass
class TradeResult:
    """Résultat d'un trade."""
    opportunity_id: str
    success: bool
    order_yes_id: Optional[str] = None
    order_no_id: Optional[str] = None
    error_message: Optional[str] = None
    executed_at: datetime = field(default_factory=datetime.now)
    
    @property
    def is_partial(self) -> bool:
        """Vérifie si un seul ordre a réussi."""
        return (self.order_yes_id is not None) != (self.order_no_id is not None)


class OrderExecutor:
    """
    Exécute les trades automatiquement quand les opportunités sont détectées.
    
    Usage:
        executor = OrderExecutor(credentials)
        await executor.start()
        result = await executor.execute_opportunity(opportunity)
    """
    
    def __init__(
        self,
        credentials: Optional[PolymarketCredentials] = None,
        order_manager: Optional[OrderManager] = None
    ):
        self.settings = get_settings()
        self._params: TradingParams = get_trading_params()
        self._credentials = credentials
        self._order_manager = order_manager or OrderManager()
        
        self._state = ExecutorState.STOPPED
        self._client: Optional[PolymarketPrivateClient] = None

        # Stats
        self._trades_today = 0
        self._successful_trades = 0
        self._failed_trades = 0
        self._last_trade_time: Optional[datetime] = None

        # 5.2: Locks par marché (au lieu d'un lock global)
        # Permet des trades parallèles sur différents marchés
        from typing import Dict
        self._market_locks: Dict[str, asyncio.Lock] = {}
        
        # Callbacks
        self.on_trade_start: Optional[Callable[[Opportunity], None]] = None
        self.on_trade_success: Optional[Callable[[TradeResult], None]] = None
        self.on_trade_failure: Optional[Callable[[TradeResult], None]] = None
        self.on_state_change: Optional[Callable[[ExecutorState], None]] = None
    
    @property
    def state(self) -> ExecutorState:
        """État actuel de l'executor."""
        return self._state
    
    @property
    def is_ready(self) -> bool:
        """Vérifie si l'executor est prêt à trader."""
        return self._state == ExecutorState.READY and self._credentials is not None
    
    @property
    def stats(self) -> dict:
        """Statistiques de trading."""
        return {
            "trades_today": self._trades_today,
            "successful": self._successful_trades,
            "failed": self._failed_trades,
            "win_rate": self._successful_trades / max(1, self._trades_today) * 100,
            "last_trade": self._last_trade_time.isoformat() if self._last_trade_time else None,
        }
    
    def set_credentials(self, credentials: PolymarketCredentials) -> None:
        """Configure les credentials."""
        self._credentials = credentials
    
    def update_params(self, params: TradingParams) -> None:
        """Met à jour les paramètres de trading."""
        self._params = params
    
    def _set_state(self, state: ExecutorState) -> None:
        """Change l'état."""
        self._state = state
        if self.on_state_change:
            self.on_state_change(state)
    
    async def start(self) -> bool:
        """
        Démarre l'executor.
        
        Returns:
            True si démarré, False si erreur
        """
        if not self._credentials or not self._credentials.is_valid:
            return False
        
        try:
            self._client = PolymarketPrivateClient(self._credentials)
            await self._client.__aenter__()
            self._set_state(ExecutorState.READY)
            return True
        except Exception as e:
            self._set_state(ExecutorState.STOPPED)
            return False
    
    async def stop(self) -> None:
        """Arrête l'executor."""
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None
        self._set_state(ExecutorState.STOPPED)
    
    def pause(self) -> None:
        """Met l'executor en pause."""
        if self._state == ExecutorState.READY:
            self._set_state(ExecutorState.PAUSED)
    
    def resume(self) -> None:
        """Reprend l'execution."""
        if self._state == ExecutorState.PAUSED:
            self._set_state(ExecutorState.READY)
    
    async def can_trade(self) -> tuple[bool, str]:
        """
        Vérifie si on peut trader maintenant.
        
        Returns:
            Tuple (peut_trader, raison si non)
        """
        # Vérifier l'état
        if self._state != ExecutorState.READY:
            return False, f"Executor non prêt (état: {self._state.value})"
        
        # Vérifier le trading automatique
        if not self._params.auto_trading_enabled:
            return False, "Trading automatique désactivé"
        
        # Vérifier le délai entre trades
        if self._last_trade_time:
            elapsed = (datetime.now() - self._last_trade_time).total_seconds()
            if elapsed < self._params.min_time_between_trades:
                remaining = self._params.min_time_between_trades - elapsed
                return False, f"Attendre {remaining:.0f}s avant prochain trade"
        
        # Vérifier le nombre de positions ouvertes
        open_positions = self._order_manager.open_positions_count
        if open_positions >= self._params.max_open_positions:
            return False, f"Limite de positions atteinte ({open_positions}/{self._params.max_open_positions})"
        
        # Vérifier l'exposition totale
        current_exposure = self._order_manager.total_exposure
        if current_exposure + self._params.capital_per_trade > self._params.max_total_exposure:
            return False, f"Exposition max atteinte (${current_exposure:.2f}/${self._params.max_total_exposure:.2f})"
        
        return True, ""
    
    def _get_market_lock(self, market_id: str) -> asyncio.Lock:
        """5.2: Récupère ou crée un lock pour un marché spécifique."""
        if market_id not in self._market_locks:
            self._market_locks[market_id] = asyncio.Lock()
        return self._market_locks[market_id]

    async def execute_opportunity(self, opportunity: Opportunity) -> TradeResult:
        """
        Exécute un trade sur une opportunité.

        Args:
            opportunity: L'opportunité à trader

        Returns:
            TradeResult avec les détails du trade
        """
        # 5.2: Lock par marché - permet des trades parallèles sur différents marchés
        market_lock = self._get_market_lock(opportunity.market_id)
        async with market_lock:
            self._set_state(ExecutorState.EXECUTING)
            
            try:
                # Vérifier si on peut trader
                can_trade, reason = await self.can_trade()
                if not can_trade:
                    return TradeResult(
                        opportunity_id=opportunity.id,
                        success=False,
                        error_message=reason
                    )
                
                # Vérifier l'opportunité
                if opportunity.action != OpportunityAction.TRADE:
                    return TradeResult(
                        opportunity_id=opportunity.id,
                        success=False,
                        error_message="Opportunité non éligible au trading"
                    )
                
                # Callback de début
                if self.on_trade_start:
                    self.on_trade_start(opportunity)
                
                # Calculer la taille des ordres
                size = self._calculate_order_size(opportunity)
                
                # Placer les ordres
                result = await self._place_bilateral_orders(opportunity, size)
                
                # Mettre à jour les stats
                self._trades_today += 1
                self._last_trade_time = datetime.now()
                
                if result.success:
                    self._successful_trades += 1
                    if self.on_trade_success:
                        self.on_trade_success(result)
                else:
                    self._failed_trades += 1
                    if self.on_trade_failure:
                        self.on_trade_failure(result)
                
                return result
                
            finally:
                self._set_state(ExecutorState.READY)
    
    def _calculate_order_size(self, opportunity: Opportunity) -> float:
        """
        Calcule la taille optimale des ordres.
        
        Basé sur:
        - Capital alloué par trade
        - Prix des tokens
        - Spread disponible
        """
        capital = self._params.capital_per_trade
        
        # Calculer le nombre de shares basé sur le prix moyen
        avg_price = (opportunity.recommended_price_yes + opportunity.recommended_price_no) / 2
        
        # On divise le capital entre YES et NO
        capital_per_side = capital / 2
        
        # Nombre de shares par côté
        shares = capital_per_side / avg_price
        
        return round(shares, 2)
    
    async def _place_bilateral_orders(
        self,
        opportunity: Opportunity,
        size: float
    ) -> TradeResult:
        """
        Place les ordres bilatéraux (YES + NO).
        
        Args:
            opportunity: Opportunité à trader
            size: Taille des ordres
            
        Returns:
            TradeResult
        """
        if not self._client:
            return TradeResult(
                opportunity_id=opportunity.id,
                success=False,
                error_message="Client non initialisé"
            )
        
        order_yes_id = None
        order_no_id = None

        try:
            # 5.1: Exécution PARALLÈLE des ordres YES et NO (50% latence gagnée)
            results = await asyncio.gather(
                self._client.place_order(
                    token_id=opportunity.token_yes_id,
                    side=OrderSide.BUY,
                    price=opportunity.recommended_price_yes,
                    size=size
                ),
                self._client.place_order(
                    token_id=opportunity.token_no_id,
                    side=OrderSide.BUY,
                    price=opportunity.recommended_price_no,
                    size=size
                ),
                return_exceptions=True  # Capturer les erreurs individuellement
            )

            order_yes, order_no = results

            # Traiter résultat YES
            if isinstance(order_yes, Exception):
                raise order_yes  # Propager l'erreur
            order_yes_id = order_yes.get("id")

            # Traiter résultat NO
            if isinstance(order_no, Exception):
                raise order_no  # Propager l'erreur
            order_no_id = order_no.get("id")
            
            # Enregistrer dans l'order manager
            if order_yes_id:
                self._order_manager.add_order(ActiveOrder(
                    id=order_yes_id,
                    opportunity_id=opportunity.id,
                    market_id=opportunity.market_id,
                    token_id=opportunity.token_yes_id,
                    side="YES",
                    price=opportunity.recommended_price_yes,
                    size=size,
                    status="open"
                ))
            
            if order_no_id:
                self._order_manager.add_order(ActiveOrder(
                    id=order_no_id,
                    opportunity_id=opportunity.id,
                    market_id=opportunity.market_id,
                    token_id=opportunity.token_no_id,
                    side="NO",
                    price=opportunity.recommended_price_no,
                    size=size,
                    status="open"
                ))
            
            return TradeResult(
                opportunity_id=opportunity.id,
                success=True,
                order_yes_id=order_yes_id,
                order_no_id=order_no_id
            )
            
        except Exception as e:
            # Si un ordre a réussi, essayer de l'annuler
            if order_yes_id and not order_no_id:
                try:
                    await self._client.cancel_order(order_yes_id)
                except Exception:
                    pass
            
            return TradeResult(
                opportunity_id=opportunity.id,
                success=False,
                order_yes_id=order_yes_id,
                order_no_id=order_no_id,
                error_message=str(e)
            )
    
    async def cancel_all_orders(self) -> int:
        """
        Annule tous les ordres actifs.
        
        Returns:
            Nombre d'ordres annulés
        """
        if not self._client:
            return 0
        
        try:
            count = await self._client.cancel_all_orders()
            self._order_manager.clear()
            return count
        except Exception:
            return 0
