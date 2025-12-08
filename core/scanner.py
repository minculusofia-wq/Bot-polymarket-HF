"""
Market Scanner - Scanne les marchés crypto Up/Down en temps réel

Fonctionnalités:
1. Récupère tous les marchés actifs de Polymarket
2. Filtre par mots-clés (BTC, SOL, ETH, XRP)
3. Filtre par type (Up/Down)
4. Analyse les orderbooks en temps réel
5. Émet des événements quand une opportunité est détectée
"""

import asyncio
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from api.public import PolymarketPublicClient, GammaClient, WebSocketFeed
from api.public.polymarket_public import Market, OrderBook
from config import get_settings, get_trading_params


class ScannerState(Enum):
    """États du scanner."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class MarketData:
    """Données complètes d'un marché."""
    market: Market
    orderbook_yes: Optional[dict] = None
    orderbook_no: Optional[dict] = None
    
    # Prix best bid/ask
    best_bid_yes: Optional[float] = None
    best_ask_yes: Optional[float] = None
    best_bid_no: Optional[float] = None
    best_ask_no: Optional[float] = None
    
    # Spreads calculés
    spread_yes: Optional[float] = None
    spread_no: Optional[float] = None
    
    # Métadonnées
    last_update: datetime = field(default_factory=datetime.now)
    
    @property
    def effective_spread(self) -> float:
        """Spread effectif moyen."""
        spreads = [s for s in [self.spread_yes, self.spread_no] if s is not None]
        return sum(spreads) / len(spreads) if spreads else 0.0
    
    @property
    def is_valid(self) -> bool:
        """Vérifie si les données sont complètes."""
        return (
            self.best_bid_yes is not None and
            self.best_ask_yes is not None and
            self.spread_yes is not None
        )


class MarketScanner:
    """
    Scanne les marchés crypto Up/Down de Polymarket.
    
    Usage:
        scanner = MarketScanner()
        scanner.on_market_update = my_callback
        await scanner.start()
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._state = ScannerState.STOPPED
        self._markets: dict[str, MarketData] = {}
        self._scan_task: Optional[asyncio.Task] = None
        self._ws_task: Optional[asyncio.Task] = None
        
        # Clients API
        self._polymarket_client: Optional[PolymarketPublicClient] = None
        self._gamma_client: Optional[GammaClient] = None
        self._ws_feed: Optional[WebSocketFeed] = None
        
        # Callbacks
        self.on_market_update: Optional[Callable[[MarketData], None]] = None
        self.on_new_market: Optional[Callable[[Market], None]] = None
        self.on_market_removed: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[Exception], None]] = None
        self.on_state_change: Optional[Callable[[ScannerState], None]] = None
    
    @property
    def state(self) -> ScannerState:
        """État actuel du scanner."""
        return self._state
    
    @property
    def markets(self) -> dict[str, MarketData]:
        """Marchés actuellement suivis."""
        return self._markets.copy()
    
    @property
    def market_count(self) -> int:
        """Nombre de marchés suivis."""
        return len(self._markets)
    
    def _set_state(self, state: ScannerState) -> None:
        """Change l'état du scanner."""
        self._state = state
        if self.on_state_change:
            self.on_state_change(state)
    
    async def start(self) -> None:
        """
        Démarre le scanner.
        
        1. Initialise les clients API
        2. Charge les marchés initiaux
        3. Démarre la boucle de scan
        """
        if self._state == ScannerState.RUNNING:
            return
        
        self._set_state(ScannerState.STARTING)
        
        try:
            # Initialiser les clients
            self._polymarket_client = PolymarketPublicClient()
            self._gamma_client = GammaClient()
            
            await self._polymarket_client.__aenter__()
            await self._gamma_client.__aenter__()
            
            # Charger les marchés initiaux
            await self._load_markets()
            
            # Démarrer la boucle de scan
            self._scan_task = asyncio.create_task(self._scan_loop())
            
            self._set_state(ScannerState.RUNNING)
            
        except Exception as e:
            self._set_state(ScannerState.ERROR)
            if self.on_error:
                self.on_error(e)
            raise
    
    async def stop(self) -> None:
        """Arrête le scanner."""
        self._set_state(ScannerState.STOPPED)
        
        # Annuler les tâches
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        
        # Fermer les clients
        if self._polymarket_client:
            await self._polymarket_client.__aexit__(None, None, None)
        if self._gamma_client:
            await self._gamma_client.__aexit__(None, None, None)
        if self._ws_feed:
            await self._ws_feed.disconnect()
    
    def pause(self) -> None:
        """Met le scanner en pause."""
        if self._state == ScannerState.RUNNING:
            self._set_state(ScannerState.PAUSED)
    
    def resume(self) -> None:
        """Reprend le scan."""
        if self._state == ScannerState.PAUSED:
            self._set_state(ScannerState.RUNNING)
    
    async def _load_markets(self) -> None:
        """Charge et filtre les marchés crypto Up/Down via Gamma API (rapide)."""
        if not self._polymarket_client or not self._gamma_client:
            return
        
        try:
            # 1. Découverte rapide via Gamma API
            gamma_markets = await self._gamma_client.get_crypto_markets()
            
            # 2. Récupération des détails via CLOB API (nécessaire pour Token IDs)
            for gm in gamma_markets:
                condition_id = gm.get("condition_id") or gm.get("id")
                if not condition_id:
                    continue
                    
                # Vérifier si on l'a déjà
                if any(m.market.condition_id == condition_id for m in self._markets.values()):
                    continue
                
                try:
                    # Récupérer les détails complets (Tokens IDs etc)
                    market_details = await self._polymarket_client.get_market(condition_id)
                    if not market_details:
                        continue
                        
                    market = self._polymarket_client.parse_market(market_details)
                    if market and market.active:
                        self._markets[market.id] = MarketData(market=market)
                        if self.on_new_market:
                            self.on_new_market(market)
                            
                    # Petit délai pour éviter rate limiting
                    await asyncio.sleep(0.05)
                    
                except Exception:
                    continue
                    
        except Exception as e:
            if self.on_error:
                self.on_error(e)

    async def _scan_loop(self) -> None:
        """Boucle principale de scan."""
        while self._state in (ScannerState.RUNNING, ScannerState.PAUSED):
            try:
                if self._state == ScannerState.PAUSED:
                    await asyncio.sleep(1)
                    continue
                
                # Rafraîchir les marchés périodiquement
                await self._refresh_markets()
                
                # Mettre à jour les orderbooks
                await self._update_orderbooks()
                
                # Attendre avant le prochain scan
                await asyncio.sleep(self.settings.scan_interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self.on_error:
                    self.on_error(e)
                await asyncio.sleep(5)  # Attendre avant retry

    async def _refresh_markets(self) -> None:
        """Rafraîchit la liste des marchés via Gamma."""
        # Même logique que _load_markets pour l'instant
        await self._load_markets()
    
    async def _update_orderbooks(self) -> None:
        """Met à jour les orderbooks de tous les marchés."""
        if not self._polymarket_client:
            return
        
        for market_id, market_data in list(self._markets.items()):
            try:
                # Récupérer l'orderbook YES
                orderbook_yes = await self._polymarket_client.get_orderbook(
                    market_data.market.token_yes_id
                )
                
                # Parser les données
                bids = orderbook_yes.get("bids", [])
                asks = orderbook_yes.get("asks", [])
                
                market_data.orderbook_yes = orderbook_yes
                market_data.best_bid_yes = float(bids[0]["price"]) if bids else None
                market_data.best_ask_yes = float(asks[0]["price"]) if asks else None
                
                if market_data.best_bid_yes and market_data.best_ask_yes:
                    market_data.spread_yes = market_data.best_ask_yes - market_data.best_bid_yes
                
                # Récupérer l'orderbook NO
                orderbook_no = await self._polymarket_client.get_orderbook(
                    market_data.market.token_no_id
                )
                
                bids = orderbook_no.get("bids", [])
                asks = orderbook_no.get("asks", [])
                
                market_data.orderbook_no = orderbook_no
                market_data.best_bid_no = float(bids[0]["price"]) if bids else None
                market_data.best_ask_no = float(asks[0]["price"]) if asks else None
                
                if market_data.best_bid_no and market_data.best_ask_no:
                    market_data.spread_no = market_data.best_ask_no - market_data.best_bid_no
                
                market_data.last_update = datetime.now()
                
                # Notifier de la mise à jour
                if self.on_market_update:
                    self.on_market_update(market_data)
                
                # Petit délai pour éviter le rate limiting
                await asyncio.sleep(0.1)
                
            except Exception as e:
                # Ignorer les erreurs individuelles
                continue
    
    async def get_market_data(self, market_id: str) -> Optional[MarketData]:
        """Récupère les données d'un marché spécifique."""
        return self._markets.get(market_id)
    
    async def force_refresh(self) -> None:
        """Force un rafraîchissement immédiat."""
        await self._refresh_markets()
        await self._update_orderbooks()
