"""
Polymarket Public Client - API publique sans authentification

Endpoints utilisés:
- GET /markets : Liste des marchés actifs
- GET /book : Orderbook d'un marché spécifique
- GET /price : Prix actuel YES/NO
- GET /trades : Trades récents

Aucune clé API requise.
"""

import httpx
from typing import Optional, Any
from dataclasses import dataclass
from datetime import datetime
import asyncio

from config import get_settings


@dataclass
class Market:
    """Représentation d'un marché Polymarket."""
    id: str
    condition_id: str
    question: str
    slug: str
    
    # Tokens
    token_yes_id: str
    token_no_id: str
    
    # Prix
    price_yes: float
    price_no: float
    
    # Métadonnées
    volume: float
    liquidity: float
    end_date: Optional[datetime]
    active: bool
    
    # Spread calculé
    @property
    def spread(self) -> float:
        """Calcule le spread bid/ask."""
        return abs(1.0 - self.price_yes - self.price_no)
    
    def matches_keywords(self, keywords: list[str]) -> bool:
        """Vérifie si le marché contient les mots-clés."""
        question_lower = self.question.lower()
        return any(kw.lower() in question_lower for kw in keywords)
    
    def matches_type(self, types: list[str]) -> bool:
        """Vérifie si le marché est du type recherché (Up/Down)."""
        question_lower = self.question.lower()
        return any(t.lower() in question_lower for t in types)


@dataclass
class OrderBook:
    """Orderbook d'un marché."""
    market_id: str
    
    # Bids (achats) - prix décroissants
    bids_yes: list[tuple[float, float]]  # [(price, size), ...]
    bids_no: list[tuple[float, float]]
    
    # Asks (ventes) - prix croissants
    asks_yes: list[tuple[float, float]]
    asks_no: list[tuple[float, float]]
    
    @property
    def best_bid_yes(self) -> Optional[float]:
        """Meilleur prix d'achat YES."""
        return self.bids_yes[0][0] if self.bids_yes else None
    
    @property
    def best_ask_yes(self) -> Optional[float]:
        """Meilleur prix de vente YES."""
        return self.asks_yes[0][0] if self.asks_yes else None
    
    @property
    def best_bid_no(self) -> Optional[float]:
        """Meilleur prix d'achat NO."""
        return self.bids_no[0][0] if self.bids_no else None
    
    @property
    def best_ask_no(self) -> Optional[float]:
        """Meilleur prix de vente NO."""
        return self.asks_no[0][0] if self.asks_no else None
    
    @property
    def spread_yes(self) -> Optional[float]:
        """Spread sur YES."""
        if self.best_bid_yes and self.best_ask_yes:
            return self.best_ask_yes - self.best_bid_yes
        return None
    
    @property
    def spread_no(self) -> Optional[float]:
        """Spread sur NO."""
        if self.best_bid_no and self.best_ask_no:
            return self.best_ask_no - self.best_bid_no
        return None


class PolymarketPublicClient:
    """
    Client pour les endpoints publics de Polymarket CLOB.
    
    Usage:
        async with PolymarketPublicClient() as client:
            markets = await client.get_markets()
            orderbook = await client.get_orderbook(market_id)
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.polymarket_api_url
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        """Initialise le client HTTP."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.settings.request_timeout,
            headers={
                "Accept": "application/json",
                "User-Agent": "HFT-Scalper-Bot/1.0"
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Ferme le client HTTP."""
        if self._client:
            await self._client.aclose()
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        retries: int = 3
    ) -> Any:
        """Effectue une requête HTTP avec retry."""
        if not self._client:
            raise RuntimeError("Client non initialisé. Utilisez 'async with'.")
        
        last_error = None
        for attempt in range(retries):
            try:
                response = await self._client.request(
                    method=method,
                    url=endpoint,
                    params=params
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code >= 500:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                raise
            except httpx.RequestError as e:
                last_error = e
                await asyncio.sleep(1 * (attempt + 1))
                continue
        
        raise last_error or Exception("Requête échouée après plusieurs tentatives")
    
    async def get_markets(
        self,
        next_cursor: Optional[str] = None,
        limit: int = 100,
        active: bool = True
    ) -> tuple[list[dict], Optional[str]]:
        """
        Récupère la liste des marchés.
        
        Returns:
            Tuple (liste de marchés, next_cursor pour pagination)
        """
        params = {"limit": limit}
        if next_cursor:
            params["next_cursor"] = next_cursor
        if active:
            params["active"] = "true"
        
        response = await self._request("GET", "/markets", params)
        
        markets = response.get("data", response) if isinstance(response, dict) else response
        next_cursor = response.get("next_cursor") if isinstance(response, dict) else None
        
        return markets, next_cursor
    
    async def get_all_markets(self, active: bool = True) -> list[dict]:
        """
        Récupère TOUS les marchés (avec pagination automatique).
        
        Returns:
            Liste complète des marchés
        """
        all_markets = []
        next_cursor = None
        
        while True:
            markets, next_cursor = await self.get_markets(
                next_cursor=next_cursor,
                active=active
            )
            all_markets.extend(markets)
            
            if not next_cursor:
                break
            
            # Petit délai pour éviter le rate limiting
            await asyncio.sleep(0.1)
        
        return all_markets
    
    async def get_market(self, condition_id: str) -> Optional[dict]:
        """Récupère un marché spécifique par son condition_id."""
        try:
            response = await self._request("GET", f"/markets/{condition_id}")
            return response
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
    
    async def get_orderbook(self, token_id: str) -> dict:
        """
        Récupère l'orderbook d'un token.
        
        Args:
            token_id: ID du token (YES ou NO)
            
        Returns:
            Orderbook avec bids et asks
        """
        response = await self._request("GET", f"/book", params={"token_id": token_id})
        return response
    
    async def get_price(self, token_id: str) -> Optional[float]:
        """Récupère le prix actuel d'un token."""
        try:
            response = await self._request("GET", f"/price", params={"token_id": token_id})
            return float(response.get("price", 0))
        except Exception:
            return None
    
    async def get_midpoint(self, token_id: str) -> Optional[float]:
        """Récupère le midpoint price d'un token."""
        try:
            response = await self._request("GET", f"/midpoint", params={"token_id": token_id})
            return float(response.get("mid", 0))
        except Exception:
            return None
    
    async def get_spread(self, token_id: str) -> Optional[dict]:
        """Récupère le spread d'un token."""
        try:
            response = await self._request("GET", f"/spread", params={"token_id": token_id})
            return response
        except Exception:
            return None
    
    def parse_market(self, data: dict) -> Optional[Market]:
        """Parse les données brutes en objet Market."""
        try:
            # Extraire les tokens
            tokens = data.get("tokens", [])
            token_yes = next((t for t in tokens if t.get("outcome") == "Yes"), None)
            token_no = next((t for t in tokens if t.get("outcome") == "No"), None)
            
            if not token_yes or not token_no:
                return None
            
            # Parser la date de fin
            end_date = None
            if data.get("end_date_iso"):
                try:
                    end_date = datetime.fromisoformat(data["end_date_iso"].replace("Z", "+00:00"))
                except Exception:
                    pass
            
            return Market(
                id=data.get("id", ""),
                condition_id=data.get("condition_id", ""),
                question=data.get("question", ""),
                slug=data.get("slug", ""),
                token_yes_id=token_yes.get("token_id", ""),
                token_no_id=token_no.get("token_id", ""),
                price_yes=float(token_yes.get("price", 0.5)),
                price_no=float(token_no.get("price", 0.5)),
                volume=float(data.get("volume", 0)),
                liquidity=float(data.get("liquidity", 0)),
                end_date=end_date,
                active=data.get("active", True)
            )
        except Exception as e:
            return None
    
    async def get_crypto_updown_markets(self) -> list[Market]:
        """
        Récupère les marchés crypto Up/Down filtrés.
        
        Returns:
            Liste des marchés correspondant aux critères
        """
        all_markets = await self.get_all_markets(active=True)
        
        filtered = []
        for market_data in all_markets:
            market = self.parse_market(market_data)
            if market is None:
                continue
            
            # Filtre par mots-clés crypto
            if not market.matches_keywords(self.settings.target_keywords):
                continue
            
            # Filtre par type Up/Down
            if not market.matches_type(self.settings.market_types):
                continue
            
            filtered.append(market)
        
        return filtered
