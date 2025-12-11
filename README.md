# Bot HFT PolyScalper - Crypto Edition

Bot de trading haute fréquence (HFT) pour scalper les marchés crypto court terme sur Polymarket.
Optimisé pour la volatilité, la vitesse et l'exécution.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Binance](https://img.shields.io/badge/Data-Binance%20Live-yellow.svg)

## Fonctionnalités

### Scanner HFT
- **WebSocket Temps Réel** - Latence 50ms (vs 1000ms polling REST)
- **Scanner Ultra-Rapide** - Détection instantanée des opportunités sur BTC, ETH, SOL...
- **Scoring Volatilité** - Intégration data Binance pour valider la volatilité réelle
- **Market Finding** - Filtre automatique des marchés < 24h et > $20k volume

### Stratégie Gabagool (Arbitrage Binaire)
- **Principe** : Accumuler YES + NO pour que `avg_YES + avg_NO < $1.00`
- **Profit Garanti** : Au settlement, une des deux options vaut $1
- **Détection Auto** : Analyse en temps réel des opportunités d'arbitrage
- **Gestion Positions** : Suivi des positions actives et profits verrouillés

### Market Maker
- **Quotes Automatiques** - Placement d'ordres bid/ask
- **Gestion du Spread** - Target spread configurable
- **Position Management** - Limites et équilibrage automatique

### Dashboard Web
- Interface réactive sur `http://localhost:8000`
- Ticker Volatilité Binance (Top Movers)
- Panel "Trades Actifs" pour gérer vos positions
- Scanner d'opportunités avec score 1-5 étoiles
- Configuration dynamique (Spread, Volume, Capital)

## Optimisations HFT v2.0

| Optimisation | Impact | Description |
|-------------|--------|-------------|
| WebSocket | 1000ms → 50ms | Données prix temps réel |
| Cache TTL | 2s → 0.5s | Données 4x plus fraîches |
| HTTP Timeout | 10s → 3s | Fail-fast pour HFT |
| Cache Propriétés | 5-10x | Calculs pré-cachés |
| Sets Filtrage | O(n) → O(1) | Filtrage positions instantané |
| Seuil Prix | -70% calculs | Skip si prix stables |
| Priorité Positions | +20% réactivité | Positions actives en premier |

## Installation

```bash
# 1. Cloner le repo
git clone https://github.com/votre-repo/PolyScalper-HFT.git
cd PolyScalper-HFT

# 2. Créer l'environnement virtuel
python3 -m venv venv
source venv/bin/activate

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer
cp .env.example .env
# Editez .env avec vos clés API Polymarket
```

## Démarrage Rapide

1. **Lancer le serveur :**
   ```bash
   # macOS
   ./🚀\ Lancer\ Bot.command

   # Ou via terminal
   source venv/bin/activate
   python3 web/server.py
   ```

2. **Ouvrir le Dashboard :**
   `http://localhost:8000`

3. **Utilisation :**
   - Cliquez sur **Start** pour lancer le scanner
   - **Gabagool** : Active la stratégie d'arbitrage binaire
   - **Market Maker** : Active le market making automatique
   - Surveillez le P&L et les profits verrouillés

## Configuration

| Paramètre | Défaut | Description |
|-----------|--------|-------------|
| `min_spread` | $0.06 | Spread minimum (rentabilité scalping) |
| `min_volume` | $20k | Liquidité minimale requise |
| `max_duration` | 24h | Focus sur marchés court terme |
| `capital` | $50 | Mise par trade |
| `max_pair_cost` | $0.98 | Pair cost max pour Gabagool |
| `order_size_usd` | $25 | Taille des ordres Gabagool |

## Architecture

```
PolyScalper-HFT/
├── web/                 # Serveur FastAPI & Dashboard
│   ├── server.py        # API endpoints + WebSocket
│   └── templates/       # HTML Dashboard
├── core/                # Moteur HFT
│   ├── scanner.py       # Scanner temps réel + WebSocket
│   ├── analyzer.py      # Scoring opportunités
│   ├── gabagool.py      # Stratégie arbitrage binaire
│   ├── market_maker.py  # Market making automatique
│   ├── trade_manager.py # Gestion trades + SL/TP
│   └── performance.py   # Optimisations (uvloop, orjson, cache)
├── api/
│   ├── public/          # Clients publics (Polymarket, Binance, Gamma)
│   │   ├── polymarket_public.py
│   │   ├── websocket_feed.py  # WebSocket temps réel
│   │   └── binance_client.py
│   └── private/         # Client privé (ordres, positions)
│       └── polymarket_private.py
├── config/              # Configuration
└── requirements.txt
```

## Sécurité

- Les clés privées sont stockées localement dans `.env` (non commité)
- Le bot tourne 100% en local
- Aucune donnée envoyée à des serveurs tiers (sauf API Polymarket/Binance)

## Avertissement

Ce logiciel est un outil d'aide au trading. Le trading de crypto-monnaies et de prédictions comporte des risques financiers importants. Utilisez uniquement le capital que vous pouvez vous permettre de perdre.

## License

MIT License
