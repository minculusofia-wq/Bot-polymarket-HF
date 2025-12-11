"""
Polymarket Private API Client (Order Placement)

Utilise py-clob-client officiel de Polymarket.
Documentation: https://github.com/Polymarket/py-clob-client

Modes supportés:
1. Direct EOA (MetaMask, hardware wallet) - signature_type=0
2. Email/Magic wallet proxy - signature_type=1
3. Browser wallet proxy - signature_type=2
"""

from typing import Optional, Dict, Any, List
from enum import Enum
import asyncio

# Import py-clob-client
try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, OrderType, MarketOrderArgs
    from py_clob_client.order_builder.constants import BUY, SELL
    _HAS_CLOB_CLIENT = True
except ImportError:
    _HAS_CLOB_CLIENT = False
    print("⚠️ py-clob-client non installé. pip install py-clob-client")


class SignatureType(Enum):
    """Types de signature supportés par Polymarket."""
    EOA = 0           # Direct wallet (MetaMask, Ledger)
    MAGIC = 1         # Email/Magic wallet
    BROWSER_PROXY = 2 # Browser wallet proxy


class OrderSide(Enum):
    """Côté de l'ordre."""
    BUY = "BUY"
    SELL = "SELL"


class PolymarketPrivate:
    """
    Client privé Polymarket pour l'exécution d'ordres.

    Usage:
        client = PolymarketPrivate(
            private_key="0x...",
            api_key="...",
            api_secret="...",
            passphrase="..."
        )
        await client.create_limit_order(token_id, "BUY", 0.55, 100)
    """

    # Polymarket CLOB endpoints
    HOST = "https://clob.polymarket.com"
    CHAIN_ID = 137  # Polygon Mainnet

    def __init__(
        self,
        private_key: str,
        api_key: str = "",
        api_secret: str = "",
        passphrase: str = "",
        signature_type: SignatureType = SignatureType.EOA,
        funder_address: Optional[str] = None
    ):
        """
        Initialise le client privé.

        Args:
            private_key: Clé privée du wallet (0x...)
            api_key: API Key Polymarket (pour API credentials)
            api_secret: API Secret
            passphrase: Passphrase API
            signature_type: Type de signature (EOA, MAGIC, BROWSER_PROXY)
            funder_address: Adresse du funder (pour proxy wallets)
        """
        self.private_key = private_key
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.signature_type = signature_type
        self.funder_address = funder_address

        self._client: Optional[ClobClient] = None
        self._initialized = False
        self._mock_mode = not _HAS_CLOB_CLIENT or not private_key

        if self._mock_mode:
            print("🔐 Private Client: Mode SIMULATION (pas de clé privée ou SDK manquant)")
        else:
            self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialise le ClobClient officiel."""
        if not _HAS_CLOB_CLIENT:
            return

        try:
            # Configuration selon le type de signature
            kwargs = {
                "host": self.HOST,
                "key": self.private_key,
                "chain_id": self.CHAIN_ID,
            }

            # Ajouter credentials API si disponibles
            if self.api_key and self.api_secret and self.passphrase:
                kwargs["creds"] = {
                    "api_key": self.api_key,
                    "api_secret": self.api_secret,
                    "api_passphrase": self.passphrase
                }

            # Configuration pour proxy wallets
            if self.signature_type != SignatureType.EOA:
                kwargs["signature_type"] = self.signature_type.value
                if self.funder_address:
                    kwargs["funder"] = self.funder_address

            self._client = ClobClient(**kwargs)
            self._initialized = True
            print("🔐 Private Client: Connecté à Polymarket CLOB")

        except Exception as e:
            print(f"❌ Erreur initialisation ClobClient: {e}")
            self._mock_mode = True

    @property
    def is_ready(self) -> bool:
        """Vérifie si le client est prêt pour trader."""
        return self._initialized and self._client is not None

    async def get_balance(self) -> Dict[str, float]:
        """Récupère les balances du wallet."""
        if self._mock_mode:
            return {"USDC": 1000.0, "mock": True}

        try:
            # py-clob-client est synchrone, on l'exécute dans un thread
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._client.get_balance_allowance)
            return result
        except Exception as e:
            print(f"❌ Erreur get_balance: {e}")
            return {}

    async def create_limit_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
        time_in_force: str = "GTC"
    ) -> Dict[str, Any]:
        """
        Crée un ordre limite.

        Args:
            token_id: ID du token (YES ou NO)
            side: "BUY" ou "SELL"
            price: Prix de l'ordre (0.01 - 0.99)
            size: Quantité en shares
            time_in_force: GTC (Good Till Cancel) ou FOK (Fill or Kill)

        Returns:
            Détails de l'ordre créé
        """
        if self._mock_mode:
            print(f"📝 [SIMULATION] {side} {size} shares @ ${price} (token: {token_id[:16]}...)")
            return {
                "orderID": f"mock-{token_id[:8]}-{int(price*100)}",
                "status": "SIMULATED",
                "side": side,
                "price": price,
                "size": size
            }

        try:
            # Construire les arguments de l'ordre
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=BUY if side.upper() == "BUY" else SELL,
            )

            # Créer et signer l'ordre
            loop = asyncio.get_event_loop()
            signed_order = await loop.run_in_executor(
                None,
                self._client.create_order,
                order_args
            )

            # Soumettre l'ordre
            result = await loop.run_in_executor(
                None,
                self._client.post_order,
                signed_order,
                OrderType.GTC if time_in_force == "GTC" else OrderType.FOK
            )

            print(f"✅ Ordre placé: {side} {size} @ ${price}")
            return result

        except Exception as e:
            print(f"❌ Erreur create_limit_order: {e}")
            return {"error": str(e), "status": "FAILED"}

    async def create_market_order(
        self,
        token_id: str,
        side: str,
        amount: float
    ) -> Dict[str, Any]:
        """
        Crée un ordre au marché.

        Args:
            token_id: ID du token
            side: "BUY" ou "SELL"
            amount: Montant en USDC (pour BUY) ou en shares (pour SELL)

        Returns:
            Détails de l'ordre
        """
        if self._mock_mode:
            print(f"📝 [SIMULATION] MARKET {side} ${amount} (token: {token_id[:16]}...)")
            return {
                "orderID": f"mock-market-{token_id[:8]}",
                "status": "SIMULATED",
                "side": side,
                "amount": amount
            }

        try:
            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=amount,
                side=BUY if side.upper() == "BUY" else SELL,
            )

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._client.create_and_post_market_order,
                order_args
            )

            print(f"✅ Ordre marché exécuté: {side} ${amount}")
            return result

        except Exception as e:
            print(f"❌ Erreur create_market_order: {e}")
            return {"error": str(e), "status": "FAILED"}

    async def cancel_order(self, order_id: str) -> bool:
        """
        Annule un ordre.

        Args:
            order_id: ID de l'ordre à annuler

        Returns:
            True si annulé avec succès
        """
        if self._mock_mode:
            print(f"📝 [SIMULATION] Cancel order {order_id}")
            return True

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._client.cancel,
                order_id
            )
            print(f"✅ Ordre annulé: {order_id}")
            return True

        except Exception as e:
            print(f"❌ Erreur cancel_order: {e}")
            return False

    async def cancel_all_orders(self) -> bool:
        """Annule tous les ordres ouverts."""
        if self._mock_mode:
            print("📝 [SIMULATION] Cancel all orders")
            return True

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._client.cancel_all
            )
            print("✅ Tous les ordres annulés")
            return True

        except Exception as e:
            print(f"❌ Erreur cancel_all_orders: {e}")
            return False

    async def get_open_orders(self) -> List[Dict[str, Any]]:
        """Récupère les ordres ouverts."""
        if self._mock_mode:
            return []

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._client.get_orders
            )
            return result

        except Exception as e:
            print(f"❌ Erreur get_open_orders: {e}")
            return []

    async def get_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Récupère l'historique des trades."""
        if self._mock_mode:
            return []

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._client.get_trades(limit=limit)
            )
            return result

        except Exception as e:
            print(f"❌ Erreur get_trades: {e}")
            return []

    # Alias pour compatibilité avec l'ancien code
    async def create_order(
        self,
        market_id: str,
        side: str,
        price: float,
        size: float
    ) -> Dict[str, Any]:
        """Alias pour create_limit_order (compatibilité)."""
        return await self.create_limit_order(
            token_id=market_id,
            side=side.upper(),
            price=price,
            size=size
        )
