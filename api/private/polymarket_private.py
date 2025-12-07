"""
Polymarket Private Client - API authentifiée pour passer des ordres

⚠️ CE FICHIER NÉCESSITE VOS CREDENTIALS POUR FONCTIONNER

Endpoints privés:
- POST /order : Placer un ordre
- DELETE /order/{id} : Annuler un ordre
- GET /orders : Mes ordres actifs
- GET /positions : Mes positions

Authentification requise:
- API Key Polymarket
- Signature des requêtes
- Wallet connecté pour signer les transactions
"""

import hmac
import hashlib
import time
import json
import httpx
from typing import Optional, Any
from dataclasses import dataclass
from enum import Enum

from config import get_settings


class OrderSide(Enum):
    """Côté de l'ordre."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Type d'ordre."""
    LIMIT = "LMT"
    MARKET = "MKT"
    GTC = "GTC"  # Good Till Cancelled
    GTD = "GTD"  # Good Till Date
    FOK = "FOK"  # Fill Or Kill


@dataclass
class PolymarketCredentials:
    """
    Credentials pour API privée Polymarket.
    
    ⚠️ À REMPLIR avec vos propres credentials.
    """
    api_key: str = ""
    api_secret: str = ""
    passphrase: str = ""  # Si requis
    
    @property
    def is_valid(self) -> bool:
        """Vérifie si les credentials sont présentes."""
        return bool(self.api_key and self.api_secret)


@dataclass
class Order:
    """Représentation d'un ordre."""
    id: str
    market_id: str
    token_id: str
    side: OrderSide
    price: float
    size: float
    filled_size: float
    status: str
    created_at: str


@dataclass
class Position:
    """Représentation d'une position."""
    market_id: str
    token_id: str
    outcome: str  # "Yes" ou "No"
    size: float
    avg_price: float
    current_price: float
    unrealized_pnl: float


class PolymarketPrivateClient:
    """
    Client pour les endpoints privés de Polymarket CLOB.
    
    ⚠️ REQUIRES AUTHENTICATION
    
    Usage:
        credentials = PolymarketCredentials(
            api_key="your_key",
            api_secret="your_secret"
        )
        client = PolymarketPrivateClient(credentials)
        await client.place_order(...)
    """
    
    def __init__(self, credentials: PolymarketCredentials):
        self.credentials = credentials
        self.settings = get_settings()
        self.base_url = self.settings.polymarket_api_url
        self._client: Optional[httpx.AsyncClient] = None
        self._authenticated = False
    
    async def __aenter__(self):
        """Initialise le client HTTP."""
        if not self.credentials.is_valid:
            raise ValueError("Credentials invalides. Configurez api_key et api_secret.")
        
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.settings.request_timeout,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Ferme le client HTTP."""
        if self._client:
            await self._client.aclose()
    
    def _sign_request(
        self,
        method: str,
        endpoint: str,
        timestamp: str,
        body: str = ""
    ) -> str:
        """
        Signe une requête avec HMAC-SHA256.
        
        Args:
            method: Méthode HTTP
            endpoint: Endpoint de l'API
            timestamp: Timestamp Unix
            body: Corps de la requête (JSON)
            
        Returns:
            Signature HMAC
        """
        message = f"{timestamp}{method}{endpoint}{body}"
        signature = hmac.new(
            self.credentials.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _get_auth_headers(
        self,
        method: str,
        endpoint: str,
        body: str = ""
    ) -> dict:
        """Génère les headers d'authentification."""
        timestamp = str(int(time.time() * 1000))
        signature = self._sign_request(method, endpoint, timestamp, body)
        
        return {
            "POLY_API_KEY": self.credentials.api_key,
            "POLY_SIGNATURE": signature,
            "POLY_TIMESTAMP": timestamp,
            "POLY_PASSPHRASE": self.credentials.passphrase,
        }
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict] = None,
        params: Optional[dict] = None
    ) -> Any:
        """Effectue une requête authentifiée."""
        if not self._client:
            raise RuntimeError("Client non initialisé. Utilisez 'async with'.")
        
        body = json.dumps(data) if data else ""
        headers = self._get_auth_headers(method, endpoint, body)
        
        response = await self._client.request(
            method=method,
            url=endpoint,
            headers=headers,
            content=body if data else None,
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    # ═══════════════════════════════════════════════════════════════
    # ORDRES
    # ═══════════════════════════════════════════════════════════════
    
    async def place_order(
        self,
        token_id: str,
        side: OrderSide,
        price: float,
        size: float,
        order_type: OrderType = OrderType.GTC
    ) -> dict:
        """
        Place un ordre limit.
        
        Args:
            token_id: ID du token (YES ou NO)
            side: BUY ou SELL
            price: Prix de l'ordre (0.01 - 0.99)
            size: Taille en nombre de shares
            order_type: Type d'ordre
            
        Returns:
            Détails de l'ordre créé
        """
        data = {
            "tokenID": token_id,
            "side": side.value,
            "price": str(price),
            "size": str(size),
            "type": order_type.value,
        }
        
        return await self._request("POST", "/order", data=data)
    
    async def cancel_order(self, order_id: str) -> bool:
        """
        Annule un ordre.
        
        Args:
            order_id: ID de l'ordre à annuler
            
        Returns:
            True si annulé, False sinon
        """
        try:
            await self._request("DELETE", f"/order/{order_id}")
            return True
        except Exception:
            return False
    
    async def cancel_all_orders(self) -> int:
        """
        Annule tous les ordres actifs.
        
        Returns:
            Nombre d'ordres annulés
        """
        result = await self._request("DELETE", "/orders")
        return result.get("canceled", 0)
    
    async def get_orders(
        self,
        market_id: Optional[str] = None,
        status: str = "open"
    ) -> list[dict]:
        """
        Récupère les ordres.
        
        Args:
            market_id: Filtrer par marché (optionnel)
            status: "open", "filled", "canceled", "all"
            
        Returns:
            Liste des ordres
        """
        params = {"status": status}
        if market_id:
            params["market"] = market_id
        
        return await self._request("GET", "/orders", params=params)
    
    async def get_order(self, order_id: str) -> Optional[dict]:
        """Récupère un ordre spécifique."""
        try:
            return await self._request("GET", f"/order/{order_id}")
        except Exception:
            return None
    
    # ═══════════════════════════════════════════════════════════════
    # POSITIONS
    # ═══════════════════════════════════════════════════════════════
    
    async def get_positions(self) -> list[dict]:
        """
        Récupère toutes les positions actives.
        
        Returns:
            Liste des positions
        """
        return await self._request("GET", "/positions")
    
    async def get_position(self, market_id: str) -> Optional[dict]:
        """Récupère la position sur un marché spécifique."""
        try:
            return await self._request("GET", f"/positions/{market_id}")
        except Exception:
            return None
    
    # ═══════════════════════════════════════════════════════════════
    # COMPTE
    # ═══════════════════════════════════════════════════════════════
    
    async def get_balance(self) -> dict:
        """
        Récupère le solde du compte.
        
        Returns:
            Solde USDC disponible et total
        """
        return await self._request("GET", "/balance")
    
    async def get_trades(
        self,
        market_id: Optional[str] = None,
        limit: int = 100
    ) -> list[dict]:
        """
        Récupère l'historique des trades.
        
        Args:
            market_id: Filtrer par marché (optionnel)
            limit: Nombre max de résultats
            
        Returns:
            Liste des trades
        """
        params = {"limit": limit}
        if market_id:
            params["market"] = market_id
        
        return await self._request("GET", "/trades", params=params)
    
    # ═══════════════════════════════════════════════════════════════
    # HELPERS HFT
    # ═══════════════════════════════════════════════════════════════
    
    async def place_bilateral_orders(
        self,
        token_yes_id: str,
        token_no_id: str,
        price_yes: float,
        price_no: float,
        size: float
    ) -> tuple[dict, dict]:
        """
        Place deux ordres simultanés (YES et NO).
        
        Stratégie market-making: acheter des deux côtés.
        
        Args:
            token_yes_id: ID du token YES
            token_no_id: ID du token NO
            price_yes: Prix d'achat YES
            price_no: Prix d'achat NO
            size: Taille des ordres
            
        Returns:
            Tuple (ordre_yes, ordre_no)
        """
        order_yes = await self.place_order(
            token_id=token_yes_id,
            side=OrderSide.BUY,
            price=price_yes,
            size=size
        )
        
        order_no = await self.place_order(
            token_id=token_no_id,
            side=OrderSide.BUY,
            price=price_no,
            size=size
        )
        
        return order_yes, order_no
