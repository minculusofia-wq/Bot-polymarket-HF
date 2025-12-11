"""
Trading Params - Paramètres de trading modifiables

Ces paramètres peuvent être modifiés en temps réel via l'interface.
Ils sont sauvegardés automatiquement dans trading_params.json.
"""

import os
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List


@dataclass
class TradingParams:
    """
    Paramètres de trading ajustables en temps réel.

    Ces valeurs contrôlent le comportement du bot:
    - Quand entrer en position (spread minimum)
    - Combien trader (capital par trade)
    - Limites de risque (positions max, exposition totale)
    """

    # ═══════════════════════════════════════════════════════════════
    # PARAMÈTRES DE SPREAD (Optimisés HFT)
    # ═══════════════════════════════════════════════════════════════
    min_spread: float = 0.06      # Spread optimal pour HFT (6 cents)
    max_spread: float = 0.25      # Spread max (évite illiquides)

    # ═══════════════════════════════════════════════════════════════
    # PARAMÈTRES DE VOLUME (Optimisés HFT)
    # ═══════════════════════════════════════════════════════════════
    min_volume_usd: float = 20000.0    # Volume minimum 20k$ (marchés liquides)
    min_depth_usd: float = 50.0        # Profondeur carnet min 50$ (évite fake liquidity)
    max_duration_hours: int = 24       # Durée max du marché (short-term focus)

    # ═══════════════════════════════════════════════════════════════
    # PARAMÈTRES DE CAPITAL
    # ═══════════════════════════════════════════════════════════════
    capital_per_trade: float = 50.0     # $ par trade (à configurer)
    max_open_positions: int = 5         # Nombre max de positions simultanées
    max_total_exposure: float = 500.0   # Exposition totale max en $

    # ═══════════════════════════════════════════════════════════════
    # PARAMÈTRES D'EXÉCUTION
    # ═══════════════════════════════════════════════════════════════
    order_offset: float = 0.01          # Décalage du prix (1¢ off-best)
    position_timeout_seconds: int = 0   # 0 = pas de fermeture auto (manuel)
    min_time_between_trades: int = 5    # Secondes entre trades

    # ═══════════════════════════════════════════════════════════════
    # ASSETS CIBLES (configurables)
    # ═══════════════════════════════════════════════════════════════
    target_assets: Optional[List[str]] = field(default=None)  # None = utilise settings

    # ═══════════════════════════════════════════════════════════════
    # CONTRÔLES
    # ═══════════════════════════════════════════════════════════════
    auto_trading_enabled: bool = False  # Trading automatique désactivé (manuel)
    require_confirmation: bool = True   # Confirmation avant trade
    
    def to_dict(self) -> dict:
        """Convertit en dictionnaire pour sauvegarde."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "TradingParams":
        """Crée une instance depuis un dictionnaire."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
    
    def save(self, filepath: str = "config/trading_params.json") -> None:
        """Sauvegarde les paramètres dans un fichier JSON."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, filepath: str = "config/trading_params.json") -> "TradingParams":
        """Charge les paramètres depuis un fichier JSON."""
        path = Path(filepath)
        if path.exists():
            with open(path, "r") as f:
                data = json.load(f)
                return cls.from_dict(data)
        return cls()  # Valeurs par défaut
    
    def validate(self) -> list[str]:
        """Valide les paramètres et retourne les erreurs."""
        errors = []
        
        if self.min_spread < 0.01:
            errors.append("Spread minimum doit être >= 0.01$")
        if self.min_spread > self.max_spread:
            errors.append("Spread minimum doit être <= spread maximum")
        if self.capital_per_trade < 1:
            errors.append("Capital par trade doit être >= 1$")
        if self.max_open_positions < 1:
            errors.append("Positions max doit être >= 1")
        if self.capital_per_trade * self.max_open_positions > self.max_total_exposure:
            errors.append("Exposition totale risque d'être dépassée")
            
        return errors


# Instance globale avec chargement depuis fichier
_trading_params: Optional[TradingParams] = None


def get_trading_params() -> TradingParams:
    """Retourne l'instance des paramètres de trading."""
    global _trading_params
    if _trading_params is None:
        _trading_params = TradingParams.load()
    return _trading_params


def update_trading_params(params: TradingParams) -> None:
    """Met à jour et sauvegarde les paramètres."""
    global _trading_params
    _trading_params = params
    params.save()
