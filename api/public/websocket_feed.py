"""
WebSocket Feed - Flux temps réel des prix et orderbooks

Se connecte au WebSocket Polymarket pour recevoir:
- Updates de prix en temps réel
- Changements d'orderbook
- Trades exécutés

Permet une réaction rapide aux changements de marché.
"""

import json
import asyncio
import websockets
from typing import Optional, Callable, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from config import get_settings


class MessageType(Enum):
    """Types de messages WebSocket."""
    PRICE_UPDATE = "price"
    BOOK_UPDATE = "book"
    TRADE = "trade"
    HEARTBEAT = "heartbeat"
    ERROR = "error"


@dataclass
class PriceUpdate:
    """Mise à jour de prix."""
    token_id: str
    price: float
    timestamp: datetime


@dataclass
class BookUpdate:
    """Mise à jour d'orderbook."""
    token_id: str
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]
    timestamp: datetime


@dataclass
class TradeUpdate:
    """Notification de trade."""
    token_id: str
    price: float
    size: float
    side: str  # "buy" ou "sell"
    timestamp: datetime


class WebSocketFeed:
    """
    Connexion WebSocket pour données temps réel.
    
    Usage:
        feed = WebSocketFeed()
        feed.on_price_update = my_callback
        await feed.connect()
        await feed.subscribe(["token_id_1", "token_id_2"])
        await feed.listen()
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.ws_url = self.settings.polymarket_ws_url
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._subscriptions: set[str] = set()
        self._running: bool = False
        self._reconnect_attempts: int = 0
        self._max_reconnect_attempts: int = 10
        
        # Callbacks
        self.on_price_update: Optional[Callable[[PriceUpdate], None]] = None
        self.on_book_update: Optional[Callable[[BookUpdate], None]] = None
        self.on_trade: Optional[Callable[[TradeUpdate], None]] = None
        self.on_error: Optional[Callable[[Exception], None]] = None
        self.on_connect: Optional[Callable[[], None]] = None
        self.on_disconnect: Optional[Callable[[], None]] = None
    
    @property
    def is_connected(self) -> bool:
        """Vérifie si le WebSocket est connecté."""
        return self._ws is not None and self._ws.open
    
    async def connect(self) -> bool:
        """
        Établit la connexion WebSocket.
        
        Returns:
            True si connecté, False sinon
        """
        try:
            self._ws = await websockets.connect(
                self.ws_url,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5
            )
            self._running = True
            self._reconnect_attempts = 0
            
            if self.on_connect:
                self.on_connect()
            
            return True
        except Exception as e:
            if self.on_error:
                self.on_error(e)
            return False
    
    async def disconnect(self) -> None:
        """Ferme la connexion WebSocket."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
        
        if self.on_disconnect:
            self.on_disconnect()
    
    async def subscribe(self, token_ids: list[str]) -> None:
        """
        S'abonne aux updates pour les tokens spécifiés.
        
        Args:
            token_ids: Liste des IDs de tokens à suivre
        """
        if not self.is_connected:
            raise RuntimeError("WebSocket non connecté")
        
        for token_id in token_ids:
            if token_id not in self._subscriptions:
                message = {
                    "type": "subscribe",
                    "channel": "price",
                    "token_id": token_id
                }
                await self._ws.send(json.dumps(message))
                self._subscriptions.add(token_id)
    
    async def unsubscribe(self, token_ids: list[str]) -> None:
        """Se désabonne des tokens spécifiés."""
        if not self.is_connected:
            return
        
        for token_id in token_ids:
            if token_id in self._subscriptions:
                message = {
                    "type": "unsubscribe",
                    "channel": "price",
                    "token_id": token_id
                }
                await self._ws.send(json.dumps(message))
                self._subscriptions.discard(token_id)
    
    async def listen(self) -> None:
        """
        Écoute les messages WebSocket en continu.
        
        Boucle infinie avec reconnexion automatique.
        """
        while self._running:
            try:
                if not self.is_connected:
                    connected = await self._reconnect()
                    if not connected:
                        await asyncio.sleep(5)
                        continue
                
                # Écoute des messages
                async for message in self._ws:
                    if not self._running:
                        break
                    
                    await self._handle_message(message)
            
            except websockets.exceptions.ConnectionClosed:
                if self.on_disconnect:
                    self.on_disconnect()
                
                if self._running:
                    await self._reconnect()
            
            except Exception as e:
                if self.on_error:
                    self.on_error(e)
                
                await asyncio.sleep(1)
    
    async def _reconnect(self) -> bool:
        """Tente de se reconnecter."""
        self._reconnect_attempts += 1
        
        if self._reconnect_attempts > self._max_reconnect_attempts:
            self._running = False
            return False
        
        # Backoff exponentiel
        wait_time = min(30, 2 ** self._reconnect_attempts)
        await asyncio.sleep(wait_time)
        
        connected = await self.connect()
        
        # Re-souscrire aux tokens
        if connected and self._subscriptions:
            for token_id in list(self._subscriptions):
                try:
                    message = {
                        "type": "subscribe",
                        "channel": "price",
                        "token_id": token_id
                    }
                    await self._ws.send(json.dumps(message))
                except Exception:
                    pass
        
        return connected
    
    async def _handle_message(self, raw_message: str) -> None:
        """Traite un message WebSocket."""
        try:
            data = json.loads(raw_message)
            msg_type = data.get("type", data.get("event", ""))
            
            if msg_type in ["price", "price_update"]:
                update = PriceUpdate(
                    token_id=data.get("asset_id", data.get("token_id", "")),
                    price=float(data.get("price", 0)),
                    timestamp=datetime.now()
                )
                if self.on_price_update:
                    self.on_price_update(update)
            
            elif msg_type in ["book", "book_update"]:
                update = BookUpdate(
                    token_id=data.get("asset_id", data.get("token_id", "")),
                    bids=[(float(b[0]), float(b[1])) for b in data.get("bids", [])],
                    asks=[(float(a[0]), float(a[1])) for a in data.get("asks", [])],
                    timestamp=datetime.now()
                )
                if self.on_book_update:
                    self.on_book_update(update)
            
            elif msg_type == "trade":
                update = TradeUpdate(
                    token_id=data.get("asset_id", data.get("token_id", "")),
                    price=float(data.get("price", 0)),
                    size=float(data.get("size", 0)),
                    side=data.get("side", ""),
                    timestamp=datetime.now()
                )
                if self.on_trade:
                    self.on_trade(update)
            
            elif msg_type == "heartbeat":
                pass  # Ignorer les heartbeats
            
            elif msg_type == "error":
                error = Exception(data.get("message", "WebSocket error"))
                if self.on_error:
                    self.on_error(error)
        
        except json.JSONDecodeError:
            pass
        except Exception as e:
            if self.on_error:
                self.on_error(e)
    
    async def send_heartbeat(self) -> None:
        """Envoie un heartbeat pour maintenir la connexion."""
        if self.is_connected:
            try:
                await self._ws.send(json.dumps({"type": "ping"}))
            except Exception:
                pass
