#!/bin/bash
# =============================================================================
# 🚀 HFT SCALPER BOT - LANCEMENT RAPIDE
# =============================================================================
# Double-cliquez sur ce fichier pour lancer le bot !
# =============================================================================

# Répertoire du script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Couleurs
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

clear
echo -e "${CYAN}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════════════╗
║                                                                       ║
║   ██╗  ██╗███████╗████████╗    ███████╗ ██████╗ █████╗ ██╗     ██████╗║
║   ██║  ██║██╔════╝╚══██╔══╝    ██╔════╝██╔════╝██╔══██╗██║     ██╔══██║
║   ███████║█████╗     ██║       ███████╗██║     ███████║██║     ██████╔╝
║   ██╔══██║██╔══╝     ██║       ╚════██║██║     ██╔══██║██║     ██╔═══╝ ║
║   ██║  ██║██║        ██║       ███████║╚██████╗██║  ██║███████╗██║     ║
║   ╚═╝  ╚═╝╚═╝        ╚═╝       ╚══════╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝     ║
║                                                                       ║
║                    🚀 POLYMARKET TRADING BOT 🚀                       ║
║                                                                       ║
╚═══════════════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Vérifier Python
echo -e "${YELLOW}⏳ Vérification de l'environnement...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 non trouvé !${NC}"
    echo "Installez Python3 depuis https://python.org"
    read -p "Appuyez sur Entrée pour fermer..."
    exit 1
fi
echo -e "${GREEN}✓ Python3 trouvé${NC}"

# Vérifier/installer les dépendances
python3 -c "import textual" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}⏳ Installation des dépendances (première fois)...${NC}"
    pip3 install -r requirements.txt --quiet
    echo -e "${GREEN}✓ Dépendances installées${NC}"
else
    echo -e "${GREEN}✓ Dépendances OK${NC}"
fi

# Créer .env si nécessaire
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⏳ Création du fichier de configuration...${NC}"
    cp .env.example .env
    echo -e "${GREEN}✓ Configuration créée${NC}"
fi

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}🚀 LANCEMENT DU BOT...${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════════${NC}"
echo ""

# Lancer le bot
python3 main.py

# Si le bot se ferme, attendre avant de fermer le terminal
echo ""
echo -e "${YELLOW}Bot arrêté. Appuyez sur Entrée pour fermer...${NC}"
read
