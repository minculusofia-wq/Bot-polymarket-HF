# 🚀 Bot HFT Polymarket

Bot de trading haute fréquence automatisé pour les marchés crypto Up/Down sur Polymarket.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux-lightgrey.svg)

## ✨ Fonctionnalités

- 🔍 **Scanner temps réel** - Détecte les marchés BTC, SOL, ETH, XRP Up/Down
- 📊 **Analyse de spreads** - Score les opportunités (1-5 étoiles)
- ⚡ **Trading automatique** - Place les ordres bilatéraux (YES + NO)
- 🖥️ **Interface premium** - Dashboard Textual interactif
- 🔐 **Wallet sécurisé** - Chiffrement AES-256 de la clé privée
- ⚙️ **Paramètres configurables** - Spread, capital, positions max

## 📸 Aperçu

```
╔═══════════════════════════════════════════════════════════════════╗
║           🚀 POLYMARKET HFT SCALPER                               ║
╠═══════════════════════════════════════════════════════════════════╣
║  Scanner: 🟢 Actif     │  Wallet: 💳 Connecté    │  Uptime: 01:23 ║
╠═══════════════════════════════════════════════════════════════════╣
║  📊 OPPORTUNITÉS                                                   ║
║  ⭐⭐⭐⭐⭐ SOL Up 5%    Spread: $0.08   Volume: $45k   🚀 TRADE    ║
║  ⭐⭐⭐⭐   BTC Down 3%  Spread: $0.06   Volume: $128k  🚀 TRADE    ║
║  ⭐⭐⭐     ETH Up 2%    Spread: $0.05   Volume: $32k   👀 WATCH    ║
╚═══════════════════════════════════════════════════════════════════╝
```

## 🚀 Installation

```bash
# Cloner le repo
git clone https://github.com/minculusofia-wq/Bot-polymarket-HF.git
cd Bot-polymarket-HF

# Installer les dépendances
pip install -r requirements.txt

# Configurer
cp .env.example .env
```

## 🎮 Utilisation

### Lancement rapide (macOS)
```bash
# Double-cliquez sur le fichier dans le Finder
./🚀 Lancer Bot.command
```

### Ligne de commande
```bash
# Interface graphique
python main.py

# Mode CLI
python main.py --cli

# Mode debug
python main.py --debug
```

## ⚙️ Configuration

| Paramètre | Défaut | Description |
|-----------|--------|-------------|
| `min_spread` | $0.04 | Spread minimum pour trader |
| `capital_per_trade` | $50 | Capital par trade |
| `max_open_positions` | 5 | Positions simultanées max |
| `max_total_exposure` | $500 | Exposition totale max |

## 🔐 Sécurité

- ✅ Clé privée **chiffrée AES-256**
- ✅ Jamais stockée en clair
- ✅ Prompt sécurisé (pas d'historique)
- ✅ Déchiffrement en mémoire uniquement

## 📁 Structure

```
Bot-polymarket-HF/
├── config/          # Configuration
├── core/            # Scanner, Analyzer, Executor
├── api/             # Clients Polymarket
│   ├── public/      # APIs publiques
│   └── private/     # APIs privées (ordres)
├── wallet/          # Gestion sécurisée du wallet
├── ui/              # Interface Textual
├── utils/           # Utilitaires
└── main.py          # Point d'entrée
```

## 🎯 Stratégie

Le bot utilise une stratégie de **market making bilatéral** :

1. Scanne les marchés crypto Up/Down
2. Détecte les spreads > 4¢
3. Place des ordres YES et NO légèrement off-best
4. Capture le spread quand le marché oscille

## ⚠️ Avertissement

> Ce bot exécute des trades réels. Utilisez avec prudence et commencez avec de petits montants.

## 📄 License

MIT License - Voir [LICENSE](LICENSE)
