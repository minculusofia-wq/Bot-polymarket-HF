"""
CoinGecko Public Client - Alternative à Binance pour data volatilité
"""

import httpx
from typing import Optional, Dict, List
from dataclasses import dataclass
import asyncio


@dataclass
class CryptoPrice:
    """Prix et volatilité d'un asset crypto."""
    symbol: str           # BTC, ETH, etc.
    price: float          # Prix spot actuel
    change_24h: float     # % change 24h
    high_24h: float       # Plus haut 24h
    low_24h: float        # Plus bas 24h
    
    @property
    def volatility_score(self) -> float:
        """Score de volatilité 0-100 basé sur le range 24h."""
        if self.price == 0:
            return 0
        range_pct = ((self.high_24h - self.low_24h) / self.price) * 100
        # Normaliser sur 100 (20% range = score 100)
        return min(100, range_pct * 5)


class CoinGeckoClient:
    """
    Client pour l'API publique CoinGecko (Free Tier).
    Rate limit: ~30 calls/minute
    """
    
    BASE_URL = "https://api.coingecko.com/api/v3"
    
    # Mapping Symbol -> CoinGecko ID
    ASSETS = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "XRP": "ripple",
        "DOGE": "dogecoin",
        "PEPE": "pepe",
        "TON": "the-open-network",
        "BNB": "binancecoin",
    }
    
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=10,
            headers={"Accept": "application/json"}
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
    
    async def get_volatility_ranking(self) -> List[tuple[str, float]]:
        """
        Récupère les données et retourne le ranking de volatilité.
        """
        if not self._client:
            return []
            
        try:
            ids = ",".join(self.ASSETS.values())
            response = await self._client.get(
                "/coins/markets",
                params={
                    "vs_currency": "usd",
                    "ids": ids,
                    "order": "market_cap_desc",
                    "per_page": 20,
                    "page": 1,
                    "sparkline": "false"
                }
            )
            response.raise_for_status()
            data = response.json()
            
            # Map ID back to Symbol for output
            id_to_symbol = {v: k for k, v in self.ASSETS.items()}
            
            ranking = []
            for item in data:
                cg_id = item['id']
                if cg_id in id_to_symbol:
                    symbol = id_to_symbol[cg_id]
                    price_obj = CryptoPrice(
                        symbol=symbol,
                        price=float(item.get('current_price', 0) or 0),
                        change_24h=float(item.get('price_change_percentage_24h', 0) or 0),
                        high_24h=float(item.get('high_24h', 0) or 0),
                        low_24h=float(item.get('low_24h', 0) or 0)
                    )
                    ranking.append((symbol, price_obj.volatility_score))
            
            # Sort by volatility desc
            return sorted(ranking, key=lambda x: x[1], reverse=True)
            
        except Exception as e:
            print(f"⚠️ Erreur CoinGecko: {e}")
            return []
