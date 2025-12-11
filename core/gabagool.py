"""
Gabagool Strategy - Arbitrage Binaire sur Polymarket

Stratégie:
1. Acheter YES quand YES devient cheap
2. Acheter NO quand NO devient cheap
3. Objectif: avg_YES + avg_NO < $1.00 = Profit garanti

Formules:
- avg_YES = cost_yes / qty_yes
- avg_NO = cost_no / qty_no
- pair_cost = avg_YES + avg_NO
- profit = min(qty_yes, qty_no) - (cost_yes + cost_no)
"""

from typing import Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio

from api.private import PolymarketPrivate


class GabagoolStatus(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


@dataclass
class PairPosition:
    """
    Position sur un marché binaire (YES + NO).

    Optimisations HFT:
    - Cache des propriétés calculées pour éviter recalculs
    - Mise à jour du cache uniquement lors des trades
    """

    market_id: str
    token_yes_id: str = ""
    token_no_id: str = ""
    question: str = ""

    # Quantités
    qty_yes: float = 0.0
    qty_no: float = 0.0

    # Coûts totaux
    cost_yes: float = 0.0
    cost_no: float = 0.0

    # Historique des trades
    trades_yes: int = 0
    trades_no: int = 0

    # Timing
    created_at: datetime = field(default_factory=datetime.now)
    last_trade_at: Optional[datetime] = None

    # Cache des propriétés calculées (HFT optimisation)
    _cached_avg_yes: float = field(default=0.0, init=False, repr=False)
    _cached_avg_no: float = field(default=0.0, init=False, repr=False)
    _cached_pair_cost: float = field(default=1.0, init=False, repr=False)
    _cached_is_locked: bool = field(default=False, init=False, repr=False)

    def __post_init__(self):
        """Initialise le cache après création."""
        self._update_cache()

    def _update_cache(self) -> None:
        """Met à jour toutes les valeurs cachées."""
        # avg_yes
        self._cached_avg_yes = self.cost_yes / self.qty_yes if self.qty_yes > 0 else 0.0
        # avg_no
        self._cached_avg_no = self.cost_no / self.qty_no if self.qty_no > 0 else 0.0
        # pair_cost
        if self.qty_yes > 0 and self.qty_no > 0:
            self._cached_pair_cost = self._cached_avg_yes + self._cached_avg_no
        else:
            self._cached_pair_cost = 1.0
        # is_locked
        locked_profit = min(self.qty_yes, self.qty_no) - (self.cost_yes + self.cost_no)
        self._cached_is_locked = locked_profit > 0

    @property
    def avg_yes(self) -> float:
        """Prix moyen payé pour YES (cached)."""
        return self._cached_avg_yes

    @property
    def avg_no(self) -> float:
        """Prix moyen payé pour NO (cached)."""
        return self._cached_avg_no

    @property
    def pair_cost(self) -> float:
        """Coût de la paire (cached)."""
        return self._cached_pair_cost

    @property
    def total_cost(self) -> float:
        """Coût total investi."""
        return self.cost_yes + self.cost_no

    @property
    def min_qty(self) -> float:
        """Quantité minimum (détermine le paiement garanti)."""
        return min(self.qty_yes, self.qty_no)

    @property
    def guaranteed_payout(self) -> float:
        """Paiement garanti au settlement."""
        return self.min_qty

    @property
    def locked_profit(self) -> float:
        """Profit verrouillé (si > 0, on a gagné)."""
        return self.guaranteed_payout - self.total_cost

    @property
    def is_locked(self) -> bool:
        """True si le profit est verrouillé (cached)."""
        return self._cached_is_locked

    @property
    def is_balanced(self) -> bool:
        """True si les quantités sont équilibrées."""
        if self.qty_yes == 0 or self.qty_no == 0:
            return False
        ratio = self.qty_yes / self.qty_no
        return 0.8 <= ratio <= 1.2

    def simulate_buy_yes_fast(self, price: float, qty: float) -> float:
        """Simule un achat YES (version inline optimisée)."""
        new_avg_yes = (self.cost_yes + price * qty) / (self.qty_yes + qty)
        if self.qty_no == 0:
            return 1.0
        return new_avg_yes + self._cached_avg_no

    def simulate_buy_no_fast(self, price: float, qty: float) -> float:
        """Simule un achat NO (version inline optimisée)."""
        new_avg_no = (self.cost_no + price * qty) / (self.qty_no + qty)
        if self.qty_yes == 0:
            return 1.0
        return self._cached_avg_yes + new_avg_no

    def add_yes(self, price: float, qty: float) -> None:
        """Ajoute des shares YES et met à jour le cache."""
        self.qty_yes += qty
        self.cost_yes += price * qty
        self.trades_yes += 1
        self.last_trade_at = datetime.now()
        self._update_cache()

    def add_no(self, price: float, qty: float) -> None:
        """Ajoute des shares NO et met à jour le cache."""
        self.qty_no += qty
        self.cost_no += price * qty
        self.trades_no += 1
        self.last_trade_at = datetime.now()
        self._update_cache()

    def to_dict(self) -> dict:
        """Convertit en dictionnaire."""
        return {
            "market_id": self.market_id,
            "question": self.question[:50] if self.question else "",
            "qty_yes": round(self.qty_yes, 2),
            "qty_no": round(self.qty_no, 2),
            "cost_yes": round(self.cost_yes, 2),
            "cost_no": round(self.cost_no, 2),
            "avg_yes": round(self.avg_yes, 4),
            "avg_no": round(self.avg_no, 4),
            "pair_cost": round(self.pair_cost, 4),
            "total_cost": round(self.total_cost, 2),
            "locked_profit": round(self.locked_profit, 2),
            "is_locked": self.is_locked,
            "is_balanced": self.is_balanced,
            "trades": self.trades_yes + self.trades_no,
        }


@dataclass
class GabagoolConfig:
    """Configuration de la stratégie."""

    max_pair_cost: float = 0.98       # Pair cost max acceptable
    min_improvement: float = 0.005    # Amélioration min du pair_cost pour acheter
    order_size_usd: float = 25.0      # Taille des ordres en $
    max_position_usd: float = 500.0   # Position max par marché
    balance_threshold: float = 0.2    # Seuil de déséquilibre (20%)
    refresh_interval: float = 1.0     # Intervalle de scan (secondes)


class GabagoolEngine:
    """
    Moteur de la stratégie Gabagool.

    Accumule des positions YES et NO de manière opportuniste
    pour atteindre pair_cost < 1.0 et verrouiller un profit.

    Optimisations HFT:
    - Sets pour filtrage O(1) des positions actives/verrouillées
    - Cache des prix pour éviter re-analyse
    """

    def __init__(
        self,
        private_client: Optional[PolymarketPrivate] = None,
        config: Optional[GabagoolConfig] = None
    ):
        self.private_client = private_client
        self.config = config or GabagoolConfig()
        self._status = GabagoolStatus.STOPPED
        self._positions: Dict[str, PairPosition] = {}
        self._task: Optional[asyncio.Task] = None

        # Sets pour filtrage rapide O(1) au lieu de O(n)
        self._active_ids: set = set()
        self._locked_ids: set = set()

        # Cache des derniers prix (pour seuil de changement)
        self._last_prices: Dict[str, tuple] = {}  # market_id -> (price_yes, price_no)

        # Stats globales
        self._total_trades = 0
        self._total_invested = 0.0
        self._start_time: Optional[datetime] = None

    @property
    def status(self) -> GabagoolStatus:
        return self._status

    @property
    def is_running(self) -> bool:
        return self._status == GabagoolStatus.RUNNING

    # ═══════════════════════════════════════════════════════════════
    # GESTION DES POSITIONS
    # ═══════════════════════════════════════════════════════════════

    def get_or_create_position(
        self,
        market_id: str,
        token_yes_id: str = "",
        token_no_id: str = "",
        question: str = ""
    ) -> PairPosition:
        """Récupère ou crée une position pour un marché."""
        if market_id not in self._positions:
            position = PairPosition(
                market_id=market_id,
                token_yes_id=token_yes_id,
                token_no_id=token_no_id,
                question=question[:50] if question else ""  # Truncate early
            )
            self._positions[market_id] = position
            self._active_ids.add(market_id)  # Nouvelle position = active
        return self._positions[market_id]

    def _update_position_sets(self, market_id: str) -> None:
        """Met à jour les sets active/locked pour une position."""
        position = self._positions.get(market_id)
        if not position:
            return

        if position.is_locked:
            self._locked_ids.add(market_id)
            self._active_ids.discard(market_id)
        else:
            self._active_ids.add(market_id)
            self._locked_ids.discard(market_id)

    def get_position(self, market_id: str) -> Optional[PairPosition]:
        """Récupère une position existante."""
        return self._positions.get(market_id)

    def get_all_positions(self) -> List[PairPosition]:
        """Retourne toutes les positions."""
        return list(self._positions.values())

    def get_active_positions(self) -> List[PairPosition]:
        """Retourne les positions non-verrouillées (O(k) via set)."""
        return [self._positions[mid] for mid in self._active_ids if mid in self._positions]

    def get_locked_positions(self) -> List[PairPosition]:
        """Retourne les positions avec profit verrouillé (O(k) via set)."""
        return [self._positions[mid] for mid in self._locked_ids if mid in self._positions]

    def get_active_position_ids(self) -> set:
        """Retourne les IDs des positions actives (pour priorité scanner)."""
        return self._active_ids.copy()

    # ═══════════════════════════════════════════════════════════════
    # LOGIQUE DE DÉCISION
    # ═══════════════════════════════════════════════════════════════

    def should_buy_yes(
        self,
        market_id: str,
        price: float,
        qty: float,
        token_yes_id: str = "",
        token_no_id: str = "",
        question: str = ""
    ) -> bool:
        """
        Détermine si on doit acheter YES (version optimisée HFT).

        Utilise les valeurs cached et calculs inline.
        """
        # Fast path: vérifier si dans locked_ids (O(1))
        if market_id in self._locked_ids:
            return False

        position = self.get_or_create_position(market_id, token_yes_id, token_no_id, question)

        # Cache config values localement (micro-optimisation)
        max_pos = self.config.max_position_usd
        max_cost = self.config.max_pair_cost
        min_improve = self.config.min_improvement

        # Vérifier la limite de position
        if position.total_cost + (price * qty) > max_pos:
            return False

        # Premier achat YES - toujours OK si prix raisonnable
        if position.qty_yes == 0:
            return price < 0.60

        # Calcul inline du nouveau pair_cost (évite appel fonction)
        new_avg_yes = (position.cost_yes + price * qty) / (position.qty_yes + qty)
        if position.qty_no == 0:
            new_pair_cost = 1.0
        else:
            new_pair_cost = new_avg_yes + position._cached_avg_no

        # Vérifier conditions
        if new_pair_cost >= max_cost:
            return False

        # L'achat doit améliorer le pair_cost
        if position.qty_no > 0:
            improvement = position._cached_pair_cost - new_pair_cost
            if improvement < min_improve:
                return False

        return True

    def should_buy_no(
        self,
        market_id: str,
        price: float,
        qty: float,
        token_yes_id: str = "",
        token_no_id: str = "",
        question: str = ""
    ) -> bool:
        """
        Détermine si on doit acheter NO (version optimisée HFT).

        Utilise les valeurs cached et calculs inline.
        """
        # Fast path: vérifier si dans locked_ids (O(1))
        if market_id in self._locked_ids:
            return False

        position = self.get_or_create_position(market_id, token_yes_id, token_no_id, question)

        # Cache config values localement
        max_pos = self.config.max_position_usd
        max_cost = self.config.max_pair_cost
        min_improve = self.config.min_improvement

        # Vérifier la limite de position
        if position.total_cost + (price * qty) > max_pos:
            return False

        # Premier achat NO - toujours OK si prix raisonnable
        if position.qty_no == 0:
            return price < 0.60

        # Calcul inline du nouveau pair_cost
        new_avg_no = (position.cost_no + price * qty) / (position.qty_no + qty)
        if position.qty_yes == 0:
            new_pair_cost = 1.0
        else:
            new_pair_cost = position._cached_avg_yes + new_avg_no

        # Vérifier conditions
        if new_pair_cost >= max_cost:
            return False

        # L'achat doit améliorer le pair_cost
        if position.qty_yes > 0:
            improvement = position._cached_pair_cost - new_pair_cost
            if improvement < min_improve:
                return False

        return True

    # ═══════════════════════════════════════════════════════════════
    # EXÉCUTION DES ORDRES
    # ═══════════════════════════════════════════════════════════════

    async def buy_yes(
        self,
        market_id: str,
        token_yes_id: str,
        price: float,
        qty: float,
        question: str = ""
    ) -> bool:
        """Achète des shares YES."""
        position = self.get_or_create_position(
            market_id, token_yes_id, "", question
        )

        # Vérifier si on doit acheter
        if not self.should_buy_yes(market_id, price, qty):
            return False

        # Exécuter l'ordre
        if self.private_client:
            try:
                result = await self.private_client.create_limit_order(
                    token_id=token_yes_id,
                    side="BUY",
                    price=price,
                    size=qty
                )
                if result.get("error"):
                    print(f"Erreur achat YES: {result}")
                    return False
            except Exception as e:
                print(f"Erreur exécution YES: {e}")
                return False

        # Mettre à jour la position
        position.add_yes(price, qty)
        self._total_trades += 1
        self._total_invested += price * qty

        # Mettre à jour les sets active/locked
        self._update_position_sets(market_id)

        print(f"🟢 BUY YES: {qty:.0f} @ ${price:.3f} | Pair Cost: {position.pair_cost:.4f}")

        # Vérifier si on a verrouillé le profit
        if position.is_locked:
            print(f"🎉 PROFIT VERROUILLÉ: ${position.locked_profit:.2f} sur {market_id[:16]}...")

        return True

    async def buy_no(
        self,
        market_id: str,
        token_no_id: str,
        price: float,
        qty: float,
        question: str = ""
    ) -> bool:
        """Achète des shares NO."""
        position = self.get_or_create_position(
            market_id, "", token_no_id, question
        )

        # Vérifier si on doit acheter
        if not self.should_buy_no(market_id, price, qty):
            return False

        # Exécuter l'ordre
        if self.private_client:
            try:
                result = await self.private_client.create_limit_order(
                    token_id=token_no_id,
                    side="BUY",
                    price=price,
                    size=qty
                )
                if result.get("error"):
                    print(f"Erreur achat NO: {result}")
                    return False
            except Exception as e:
                print(f"Erreur exécution NO: {e}")
                return False

        # Mettre à jour la position
        position.add_no(price, qty)
        self._total_trades += 1
        self._total_invested += price * qty

        # Mettre à jour les sets active/locked
        self._update_position_sets(market_id)

        print(f"🔴 BUY NO: {qty:.0f} @ ${price:.3f} | Pair Cost: {position.pair_cost:.4f}")

        # Vérifier si on a verrouillé le profit
        if position.is_locked:
            print(f"🎉 PROFIT VERROUILLÉ: ${position.locked_profit:.2f} sur {market_id[:16]}...")

        return True

    # ═══════════════════════════════════════════════════════════════
    # ANALYSE DES OPPORTUNITÉS
    # ═══════════════════════════════════════════════════════════════

    async def analyze_opportunity(
        self,
        market_id: str,
        token_yes_id: str,
        token_no_id: str,
        price_yes: float,
        price_no: float,
        question: str = ""
    ) -> Optional[str]:
        """
        Analyse un marché et retourne l'action à prendre.

        Optimisations HFT:
        - Seuil de changement de prix (skip si prix stable)
        - Évaluation parallèle YES/NO pour choisir le meilleur

        Returns:
            "buy_yes", "buy_no", ou None
        """
        # Fast path: marché déjà verrouillé
        if market_id in self._locked_ids:
            return None

        # Seuil de changement de prix (0.5%) - skip si pas de mouvement
        PRICE_THRESHOLD = 0.005
        if market_id in self._last_prices:
            old_yes, old_no = self._last_prices[market_id]
            yes_change = abs(price_yes - old_yes) / old_yes if old_yes > 0 else 1.0
            no_change = abs(price_no - old_no) / old_no if old_no > 0 else 1.0
            if yes_change < PRICE_THRESHOLD and no_change < PRICE_THRESHOLD:
                return None  # Prix stables, skip

        # Mettre à jour le cache des prix
        self._last_prices[market_id] = (price_yes, price_no)

        # Calculer les quantités
        order_size = self.config.order_size_usd
        qty_yes = order_size / price_yes if price_yes > 0 else 0
        qty_no = order_size / price_no if price_no > 0 else 0

        # Évaluation parallèle: vérifier les deux côtés
        can_buy_yes = self.should_buy_yes(market_id, price_yes, qty_yes, token_yes_id, token_no_id, question)
        can_buy_no = self.should_buy_no(market_id, price_no, qty_no, token_yes_id, token_no_id, question)

        # Choisir la meilleure opportunité
        if can_buy_yes and can_buy_no:
            # Les deux sont possibles: choisir le moins cher
            return "buy_yes" if price_yes <= price_no else "buy_no"
        elif can_buy_yes:
            return "buy_yes"
        elif can_buy_no:
            return "buy_no"

        return None

    # ═══════════════════════════════════════════════════════════════
    # CONTRÔLE
    # ═══════════════════════════════════════════════════════════════

    async def start(self) -> None:
        """Démarre la stratégie."""
        if self._status == GabagoolStatus.RUNNING:
            return

        self._status = GabagoolStatus.RUNNING
        self._start_time = datetime.now()
        print("🦀 Gabagool Engine démarré")

    async def stop(self) -> None:
        """Arrête la stratégie."""
        self._status = GabagoolStatus.STOPPED

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        print("🦀 Gabagool Engine arrêté")

    async def pause(self) -> None:
        """Met en pause."""
        self._status = GabagoolStatus.PAUSED
        print("🦀 Gabagool Engine en pause")

    async def resume(self) -> None:
        """Reprend après pause."""
        if self._status == GabagoolStatus.PAUSED:
            self._status = GabagoolStatus.RUNNING
            print("🦀 Gabagool Engine repris")

    # ═══════════════════════════════════════════════════════════════
    # STATS
    # ═══════════════════════════════════════════════════════════════

    def get_stats(self) -> dict:
        """Retourne les statistiques globales."""
        positions = self.get_all_positions()
        locked = self.get_locked_positions()

        total_locked_profit = sum(p.locked_profit for p in locked)
        total_potential_profit = sum(
            p.locked_profit for p in positions if p.locked_profit > 0
        )

        uptime = 0
        if self._start_time:
            uptime = (datetime.now() - self._start_time).total_seconds()

        return {
            "status": self._status.value,
            "uptime_seconds": int(uptime),
            "total_trades": self._total_trades,
            "total_invested": round(self._total_invested, 2),
            "positions_count": len(positions),
            "locked_count": len(locked),
            "active_count": len(positions) - len(locked),
            "total_locked_profit": round(total_locked_profit, 2),
            "total_potential_profit": round(total_potential_profit, 2),
            "config": {
                "max_pair_cost": self.config.max_pair_cost,
                "order_size_usd": self.config.order_size_usd,
                "max_position_usd": self.config.max_position_usd,
            }
        }
