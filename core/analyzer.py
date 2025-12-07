"""
Opportunity Analyzer - Analyse et scoring des opportunités de trading

Fonctionnalités:
1. Analyse les spreads des marchés
2. Score les opportunités selon plusieurs critères
3. Filtre selon les paramètres utilisateur
4. Recommande les trades à exécuter
"""

from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from core.scanner import MarketData
from config import get_trading_params, TradingParams


class OpportunityScore(Enum):
    """Niveaux de score d'opportunité."""
    EXCELLENT = 5  # ⭐⭐⭐⭐⭐
    VERY_GOOD = 4  # ⭐⭐⭐⭐
    GOOD = 3       # ⭐⭐⭐
    AVERAGE = 2    # ⭐⭐
    POOR = 1       # ⭐


class OpportunityAction(Enum):
    """Actions recommandées."""
    TRADE = "trade"      # Trader immédiatement
    WATCH = "watch"      # Surveiller
    SKIP = "skip"        # Ignorer


@dataclass
class Opportunity:
    """
    Représente une opportunité de trading détectée.
    
    Contient toutes les informations nécessaires pour décider
    si on doit trader et à quel prix.
    """
    
    # Identification
    id: str
    market_id: str
    question: str
    
    # Tokens
    token_yes_id: str
    token_no_id: str
    
    # Prix et spreads
    best_bid_yes: float
    best_ask_yes: float
    best_bid_no: float
    best_ask_no: float
    spread_yes: float
    spread_no: float
    
    # Prix recommandés pour placement d'ordres
    recommended_price_yes: float
    recommended_price_no: float
    
    # Métriques
    volume: float
    liquidity: float
    
    # Scoring
    score: int  # 1-5
    score_breakdown: dict = field(default_factory=dict)
    
    # Action
    action: OpportunityAction = OpportunityAction.SKIP
    
    # Timing
    detected_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    
    @property
    def effective_spread(self) -> float:
        """Spread moyen."""
        return (self.spread_yes + self.spread_no) / 2
    
    @property
    def potential_profit_per_share(self) -> float:
        """Profit potentiel par share (estimation)."""
        return self.effective_spread * 0.5  # Estimation conservatrice
    
    @property
    def score_stars(self) -> str:
        """Représentation en étoiles du score."""
        return "⭐" * self.score
    
    def to_dict(self) -> dict:
        """Convertit en dictionnaire."""
        return {
            "id": self.id,
            "market_id": self.market_id,
            "question": self.question,
            "spread_yes": self.spread_yes,
            "spread_no": self.spread_no,
            "effective_spread": self.effective_spread,
            "volume": self.volume,
            "score": self.score,
            "action": self.action.value,
            "detected_at": self.detected_at.isoformat(),
        }


class OpportunityAnalyzer:
    """
    Analyse les marchés et détecte les opportunités de trading.
    
    Usage:
        analyzer = OpportunityAnalyzer()
        opportunities = analyzer.analyze_markets(market_data_list)
    """
    
    def __init__(self, params: Optional[TradingParams] = None):
        self._params = params or get_trading_params()
        self._opportunity_counter = 0
    
    @property
    def params(self) -> TradingParams:
        """Paramètres de trading actuels."""
        return self._params
    
    def update_params(self, params: TradingParams) -> None:
        """Met à jour les paramètres."""
        self._params = params
    
    def analyze_market(self, market_data: MarketData) -> Optional[Opportunity]:
        """
        Analyse un marché et retourne une opportunité si valide.
        
        Args:
            market_data: Données du marché
            
        Returns:
            Opportunity si les critères sont remplis, None sinon
        """
        # Vérifier que les données sont valides
        if not market_data.is_valid:
            return None
        
        market = market_data.market
        
        # Vérifier le spread minimum
        spread_yes = market_data.spread_yes or 0
        spread_no = market_data.spread_no or 0
        effective_spread = (spread_yes + spread_no) / 2
        
        if effective_spread < self._params.min_spread:
            return None
        
        if effective_spread > self._params.max_spread:
            return None
        
        # Vérifier le volume minimum
        if market.volume < self._params.min_volume_usd:
            return None
        
        # Calculer les prix recommandés (off-best)
        recommended_yes = (market_data.best_bid_yes or 0) + self._params.order_offset
        recommended_no = (market_data.best_bid_no or 0) + self._params.order_offset
        
        # S'assurer que les prix sont valides (entre 0.01 et 0.99)
        recommended_yes = max(0.01, min(0.99, recommended_yes))
        recommended_no = max(0.01, min(0.99, recommended_no))
        
        # Calculer le score
        score, breakdown = self._calculate_score(market_data, effective_spread)
        
        # Déterminer l'action
        if score >= 4:
            action = OpportunityAction.TRADE
        elif score >= 3:
            action = OpportunityAction.WATCH
        else:
            action = OpportunityAction.SKIP
        
        # Créer l'opportunité
        self._opportunity_counter += 1
        
        return Opportunity(
            id=f"opp_{self._opportunity_counter}_{int(datetime.now().timestamp())}",
            market_id=market.id,
            question=market.question,
            token_yes_id=market.token_yes_id,
            token_no_id=market.token_no_id,
            best_bid_yes=market_data.best_bid_yes or 0,
            best_ask_yes=market_data.best_ask_yes or 0,
            best_bid_no=market_data.best_bid_no or 0,
            best_ask_no=market_data.best_ask_no or 0,
            spread_yes=spread_yes,
            spread_no=spread_no,
            recommended_price_yes=recommended_yes,
            recommended_price_no=recommended_no,
            volume=market.volume,
            liquidity=market.liquidity,
            score=score,
            score_breakdown=breakdown,
            action=action,
            detected_at=datetime.now(),
            expires_at=market.end_date,
        )
    
    def _calculate_score(
        self,
        market_data: MarketData,
        effective_spread: float
    ) -> tuple[int, dict]:
        """
        Calcule le score d'une opportunité.
        
        Critères:
        1. Spread (plus élevé = mieux)
        2. Volume (plus élevé = mieux)
        3. Liquidité (plus élevé = mieux)
        4. Équilibre des prix (proche de 50/50 = mieux)
        
        Returns:
            Tuple (score 1-5, breakdown)
        """
        breakdown = {}
        total_points = 0
        max_points = 0
        
        # 1. Score spread (0-25 points)
        max_points += 25
        if effective_spread >= 0.10:
            spread_points = 25
        elif effective_spread >= 0.08:
            spread_points = 20
        elif effective_spread >= 0.06:
            spread_points = 15
        elif effective_spread >= 0.04:
            spread_points = 10
        else:
            spread_points = 5
        total_points += spread_points
        breakdown["spread"] = spread_points
        
        # 2. Score volume (0-25 points)
        max_points += 25
        volume = market_data.market.volume
        if volume >= 100000:
            volume_points = 25
        elif volume >= 50000:
            volume_points = 20
        elif volume >= 20000:
            volume_points = 15
        elif volume >= 5000:
            volume_points = 10
        else:
            volume_points = 5
        total_points += volume_points
        breakdown["volume"] = volume_points
        
        # 3. Score liquidité (0-25 points)
        max_points += 25
        liquidity = market_data.market.liquidity
        if liquidity >= 50000:
            liquidity_points = 25
        elif liquidity >= 20000:
            liquidity_points = 20
        elif liquidity >= 10000:
            liquidity_points = 15
        elif liquidity >= 5000:
            liquidity_points = 10
        else:
            liquidity_points = 5
        total_points += liquidity_points
        breakdown["liquidity"] = liquidity_points
        
        # 4. Score équilibre (0-25 points)
        # Prix proche de 0.50 = marché incertain = plus de volatilité
        max_points += 25
        price_yes = market_data.market.price_yes
        distance_from_50 = abs(price_yes - 0.50)
        if distance_from_50 <= 0.10:
            balance_points = 25
        elif distance_from_50 <= 0.20:
            balance_points = 20
        elif distance_from_50 <= 0.30:
            balance_points = 15
        elif distance_from_50 <= 0.40:
            balance_points = 10
        else:
            balance_points = 5
        total_points += balance_points
        breakdown["balance"] = balance_points
        
        # Calculer le score final (1-5)
        percentage = (total_points / max_points) * 100
        if percentage >= 80:
            final_score = 5
        elif percentage >= 60:
            final_score = 4
        elif percentage >= 40:
            final_score = 3
        elif percentage >= 20:
            final_score = 2
        else:
            final_score = 1
        
        breakdown["total_points"] = total_points
        breakdown["max_points"] = max_points
        breakdown["percentage"] = percentage
        
        return final_score, breakdown
    
    def analyze_all_markets(
        self,
        markets: dict[str, MarketData]
    ) -> list[Opportunity]:
        """
        Analyse tous les marchés et retourne les opportunités.
        
        Args:
            markets: Dictionnaire de MarketData
            
        Returns:
            Liste d'opportunités triées par score (desc)
        """
        opportunities = []
        
        for market_data in markets.values():
            opportunity = self.analyze_market(market_data)
            if opportunity:
                opportunities.append(opportunity)
        
        # Trier par score décroissant
        opportunities.sort(key=lambda x: (x.score, x.effective_spread), reverse=True)
        
        return opportunities
    
    def get_tradeable_opportunities(
        self,
        markets: dict[str, MarketData]
    ) -> list[Opportunity]:
        """
        Retourne uniquement les opportunités à trader.
        
        Args:
            markets: Dictionnaire de MarketData
            
        Returns:
            Liste d'opportunités avec action=TRADE
        """
        all_opportunities = self.analyze_all_markets(markets)
        return [op for op in all_opportunities if op.action == OpportunityAction.TRADE]
    
    def should_trade(self, opportunity: Opportunity) -> bool:
        """
        Détermine si on doit trader cette opportunité.
        
        Vérifie les paramètres de trading et les sécurités.
        """
        if not self._params.auto_trading_enabled:
            return False
        
        if opportunity.action != OpportunityAction.TRADE:
            return False
        
        if opportunity.score < 4:
            return False
        
        return True
