"""
Gamma Client - API Gamma Markets pour métadonnées enrichies

Gamma Markets fournit des données supplémentaires sur les marchés Polymarket:
- Métadonnées détaillées
- Historique de volume
- Informations sur les événements

API publique, pas de clé requise.
"""

import httpx
from typing import Optional, Any
from dataclasses import dataclass
from datetime import datetime

from config import get_settings


@dataclass
class GammaMarket:
    """Métadonnées enrichies d'un marché."""
    id: str
    condition_id: str
    question: str
    
    # Volume et liquidité
    volume_24h: float
    volume_total: float
    liquidity: float
    
    # Événement parent
    event_id: Optional[str]
    event_title: Optional[str]
    
    # Timing
    created_at: Optional[datetime]
    end_date: Optional[datetime]
    
    # Status
    active: bool
    closed: bool


class GammaClient:
    """
    Client pour l'API Gamma Markets.
    
    Usage:
        async with GammaClient() as client:
            markets = await client.get_markets()
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.gamma_api_url
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
        params: Optional[dict] = None
    ) -> Any:
        """Effectue une requête HTTP."""
        if not self._client:
            raise RuntimeError("Client non initialisé. Utilisez 'async with'.")
        
        try:
            response = await self._client.request(
                method=method,
                url=endpoint,
                params=params
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise
        except httpx.RequestError as e:
            raise
    
    async def get_markets(
        self,
        limit: int = 100,
        offset: int = 0,
        active: bool = True,
        closed: bool = False
    ) -> list[dict]:
        """
        Récupère la liste des marchés depuis Gamma.
        
        Args:
            limit: Nombre max de résultats
            offset: Décalage pour pagination
            active: Filtrer les marchés actifs
            closed: Inclure les marchés fermés
            
        Returns:
            Liste des marchés
        """
        params = {
            "limit": limit,
            "offset": offset,
            "active": str(active).lower(),
            "closed": str(closed).lower()
        }
        
        return await self._request("GET", "/markets", params)
    
    async def get_market(self, condition_id: str) -> Optional[dict]:
        """Récupère un marché spécifique."""
        try:
            return await self._request("GET", f"/markets/{condition_id}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
    
    async def get_events(
        self,
        limit: int = 100,
        offset: int = 0,
        active: bool = True
    ) -> list[dict]:
        """Récupère la liste des événements."""
        params = {
            "limit": limit,
            "offset": offset,
            "active": str(active).lower()
        }
        
        return await self._request("GET", "/events", params)
    
    async def search_markets(
        self,
        query: str,
        limit: int = 50
    ) -> list[dict]:
        """
        Recherche des marchés par texte.
        
        Args:
            query: Terme de recherche
            limit: Nombre max de résultats
            
        Returns:
            Liste des marchés correspondants
        """
        params = {
            "q": query,
            "limit": limit
        }
        
        return await self._request("GET", "/markets", params)
    
    async def get_crypto_markets(self) -> list[dict]:
        """
        Récupère les marchés liés aux cryptos.
        
        Effectue une recherche pour chaque mot-clé crypto.
        """
        crypto_markets = []
        
        for keyword in self.settings.target_keywords:
            try:
                results = await self.search_markets(keyword, limit=50)
                
                # Filtrer pour les Up/Down
                for market in results:
                    question = market.get("question", "").lower()
                    if any(t.lower() in question for t in self.settings.market_types):
                        if market not in crypto_markets:
                            crypto_markets.append(market)
            except Exception:
                continue
        
        return crypto_markets
    
    def parse_market(self, data: dict) -> Optional[GammaMarket]:
        """Parse les données brutes en objet GammaMarket."""
        try:
            # Parser les dates
            created_at = None
            if data.get("created_at"):
                try:
                    created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
                except Exception:
                    pass
            
            end_date = None
            if data.get("end_date"):
                try:
                    end_date = datetime.fromisoformat(data["end_date"].replace("Z", "+00:00"))
                except Exception:
                    pass
            
            return GammaMarket(
                id=data.get("id", ""),
                condition_id=data.get("condition_id", data.get("id", "")),
                question=data.get("question", ""),
                volume_24h=float(data.get("volume_24h", 0)),
                volume_total=float(data.get("volume", 0)),
                liquidity=float(data.get("liquidity", 0)),
                event_id=data.get("event_id"),
                event_title=data.get("event_title"),
                created_at=created_at,
                end_date=end_date,
                active=data.get("active", True),
                closed=data.get("closed", False)
            )
        except Exception:
            return None
