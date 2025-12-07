"""
Web Server - API FastAPI pour le bot HFT

Endpoints:
- GET /: Dashboard principal
- GET /api/status: Statut du bot
- GET /api/opportunities: Liste des opportunités
- GET /api/stats: Statistiques
- POST /api/config: Mettre à jour la config
- POST /api/start: Démarrer le scanner
- POST /api/stop: Arrêter le scanner
- WebSocket /ws: Updates temps réel
"""

import asyncio
import json
from datetime import datetime
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_settings, get_trading_params, update_trading_params, TradingParams
from core import MarketScanner, OpportunityAnalyzer, OrderManager
from core.scanner import ScannerState


app = FastAPI(title="HFT Scalper Bot", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# État global
scanner: Optional[MarketScanner] = None
analyzer: Optional[OpportunityAnalyzer] = None
order_manager: Optional[OrderManager] = None
is_running = False
start_time = datetime.now()
connected_websockets: list[WebSocket] = []


class ConfigUpdate(BaseModel):
    min_spread: float
    capital_per_trade: float
    max_open_positions: int


# ═══════════════════════════════════════════════════════════════
# PAGES HTML
# ═══════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Page principale du dashboard."""
    html_path = Path(__file__).parent / "templates" / "index.html"
    return html_path.read_text()


# ═══════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.get("/api/status")
async def get_status():
    """Retourne le statut du bot."""
    global scanner, is_running, start_time
    
    elapsed = (datetime.now() - start_time).total_seconds()
    hours, remainder = divmod(int(elapsed), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    return {
        "is_running": is_running,
        "scanner_state": scanner.state.value if scanner else "stopped",
        "markets_count": scanner.market_count if scanner else 0,
        "uptime": f"{hours:02d}:{minutes:02d}:{seconds:02d}",
        "wallet_connected": False,
    }


@app.get("/api/opportunities")
async def get_opportunities():
    """Retourne les opportunités détectées."""
    global scanner, analyzer
    
    if not scanner or not analyzer:
        return {"opportunities": []}
    
    markets = scanner.markets
    opportunities = analyzer.analyze_all_markets(markets)
    
    return {
        "opportunities": [
            {
                "id": opp.id,
                "market": opp.question,
                "spread": round(opp.effective_spread, 4),
                "volume": opp.volume,
                "price_yes": round(opp.best_ask_yes, 2),
                "price_no": round(opp.best_ask_no, 2),
                "score": opp.score,
                "action": opp.action.value,
            }
            for opp in opportunities[:20]
        ]
    }


@app.get("/api/stats")
async def get_stats():
    """Retourne les statistiques."""
    global order_manager
    
    params = get_trading_params()
    
    if order_manager:
        stats = order_manager.stats
        return {
            "trades_today": stats["total_trades"],
            "win_rate": round(stats["win_rate"], 1),
            "pnl_today": round(order_manager.get_daily_pnl(), 2),
            "open_positions": stats["open_positions"],
            "max_positions": params.max_open_positions,
        }
    
    return {
        "trades_today": 0,
        "win_rate": 0,
        "pnl_today": 0,
        "open_positions": 0,
        "max_positions": params.max_open_positions,
    }


@app.get("/api/config")
async def get_config():
    """Retourne la configuration actuelle."""
    params = get_trading_params()
    return {
        "min_spread": params.min_spread,
        "capital_per_trade": params.capital_per_trade,
        "max_open_positions": params.max_open_positions,
        "max_total_exposure": params.max_total_exposure,
    }


@app.post("/api/config")
async def update_config(config: ConfigUpdate):
    """Met à jour la configuration."""
    global analyzer
    
    params = get_trading_params()
    params.min_spread = max(0.01, min(0.20, config.min_spread))
    params.capital_per_trade = max(1, min(1000, config.capital_per_trade))
    params.max_open_positions = max(1, min(20, config.max_open_positions))
    
    update_trading_params(params)
    
    if analyzer:
        analyzer.update_params(params)
    
    await broadcast({"type": "config_updated", "config": config.dict()})
    
    return {"success": True, "message": "Configuration mise à jour"}


@app.post("/api/start")
async def start_scanner():
    """Démarre le scanner."""
    global scanner, analyzer, order_manager, is_running
    
    if is_running:
        return {"success": False, "message": "Déjà en cours d'exécution"}
    
    try:
        order_manager = OrderManager()
        analyzer = OpportunityAnalyzer()
        scanner = MarketScanner()
        
        await scanner.start()
        is_running = True
        
        # Démarrer la tâche de broadcast
        asyncio.create_task(broadcast_loop())
        
        await broadcast({"type": "started", "markets": scanner.market_count})
        
        return {
            "success": True,
            "message": f"Scanner démarré - {scanner.market_count} marchés"
        }
        
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.post("/api/stop")
async def stop_scanner():
    """Arrête le scanner."""
    global scanner, is_running
    
    if scanner:
        await scanner.stop()
    
    is_running = False
    await broadcast({"type": "stopped"})
    
    return {"success": True, "message": "Scanner arrêté"}


# ═══════════════════════════════════════════════════════════════
# WEBSOCKET
# ═══════════════════════════════════════════════════════════════

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket pour les updates temps réel."""
    await websocket.accept()
    connected_websockets.append(websocket)
    
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_websockets.remove(websocket)


async def broadcast(message: dict):
    """Envoie un message à tous les WebSockets connectés."""
    for ws in connected_websockets.copy():
        try:
            await ws.send_json(message)
        except Exception:
            connected_websockets.remove(ws)


async def broadcast_loop():
    """Boucle de broadcast des données."""
    global scanner, analyzer, is_running
    
    while is_running:
        try:
            if scanner and analyzer:
                markets = scanner.markets
                opportunities = analyzer.analyze_all_markets(markets)
                
                await broadcast({
                    "type": "update",
                    "data": {
                        "markets_count": len(markets),
                        "opportunities": [
                            {
                                "id": opp.id,
                                "market": opp.question[:50],
                                "spread": round(opp.effective_spread, 4),
                                "volume": opp.volume,
                                "price_yes": round(opp.best_ask_yes, 2),
                                "price_no": round(opp.best_ask_no, 2),
                                "score": opp.score,
                                "action": opp.action.value,
                            }
                            for opp in opportunities[:15]
                        ],
                        "timestamp": datetime.now().isoformat(),
                    }
                })
            
            await asyncio.sleep(2)
            
        except Exception as e:
            print(f"Broadcast error: {e}")
            await asyncio.sleep(5)


# ═══════════════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    """Au démarrage du serveur."""
    print("🚀 HFT Scalper Bot - Serveur Web démarré")
    print("📊 Dashboard: http://localhost:8000")
