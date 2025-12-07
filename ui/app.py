"""
HFT Scalper App - Application Textual principale

Interface premium avec:
- Dashboard temps réel
- Paramètres modifiables (spread, capital)
- Table des opportunités
- Log d'activité
- Connexion wallet
"""

import asyncio
from datetime import datetime
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header, Footer, Static, Button, DataTable,
    Input, Label, ProgressBar, Log
)
from textual.binding import Binding
from textual.timer import Timer
from textual import work

from config import get_settings, get_trading_params, TradingParams, update_trading_params
from core import MarketScanner, OpportunityAnalyzer, Opportunity, OrderExecutor, OrderManager
from core.scanner import ScannerState, MarketData
from core.executor import ExecutorState
from api.private import PolymarketCredentials, CredentialsManager


class StatusPanel(Static):
    """Panneau de statut."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._scanner_status = "⏹️ Arrêté"
        self._api_status = "⏸️ Déconnecté"
        self._wallet_status = "🔒 Non connecté"
        self._uptime = "00:00:00"
        self._start_time = datetime.now()
    
    def compose(self) -> ComposeResult:
        yield Static(id="status-content")
    
    def update_scanner(self, state: ScannerState) -> None:
        """Met à jour le statut du scanner."""
        states = {
            ScannerState.STOPPED: "⏹️ Arrêté",
            ScannerState.STARTING: "🔄 Démarrage...",
            ScannerState.RUNNING: "🟢 Actif",
            ScannerState.PAUSED: "⏸️ Pause",
            ScannerState.ERROR: "🔴 Erreur",
        }
        self._scanner_status = states.get(state, "❓ Inconnu")
        self._refresh()
    
    def update_api(self, connected: bool) -> None:
        """Met à jour le statut API."""
        self._api_status = "🟢 Connecté" if connected else "🔴 Déconnecté"
        self._refresh()
    
    def update_wallet(self, address: Optional[str]) -> None:
        """Met à jour le statut wallet."""
        if address:
            short = f"{address[:6]}...{address[-4:]}"
            self._wallet_status = f"💳 {short}"
        else:
            self._wallet_status = "🔒 Non connecté"
        self._refresh()
    
    def update_uptime(self) -> None:
        """Met à jour l'uptime."""
        elapsed = datetime.now() - self._start_time
        hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        self._uptime = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        self._refresh()
    
    def _refresh(self) -> None:
        """Rafraîchit l'affichage."""
        content = self.query_one("#status-content", Static)
        content.update(
            f"Scanner: {self._scanner_status}  │  "
            f"API: {self._api_status}  │  "
            f"Wallet: {self._wallet_status}  │  "
            f"Uptime: {self._uptime}"
        )


class TradingParamsPanel(Static):
    """Panneau des paramètres de trading."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._params = get_trading_params()
    
    def compose(self) -> ComposeResult:
        with Horizontal(classes="params-row"):
            with Vertical(classes="param-group"):
                yield Label("💹 Spread Minimum", classes="param-label")
                yield Input(
                    value=str(self._params.min_spread),
                    placeholder="0.04",
                    id="input-spread",
                    classes="param-input"
                )
                yield Label(f"Range: 0.01$ - 0.20$", classes="param-hint")
            
            with Vertical(classes="param-group"):
                yield Label("💰 Capital / Trade", classes="param-label")
                yield Input(
                    value=str(self._params.capital_per_trade),
                    placeholder="50",
                    id="input-capital",
                    classes="param-input"
                )
                yield Label(f"Max: ${self._params.max_total_exposure}", classes="param-hint")
            
            with Vertical(classes="param-group"):
                yield Label("📊 Positions Max", classes="param-label")
                yield Input(
                    value=str(self._params.max_open_positions),
                    placeholder="5",
                    id="input-positions",
                    classes="param-input"
                )
                yield Label("Simultanées", classes="param-hint")
        
        yield Button("💾 Sauvegarder", id="btn-save-params", variant="primary")
    
    def get_params(self) -> TradingParams:
        """Récupère les paramètres depuis les inputs."""
        try:
            spread = float(self.query_one("#input-spread", Input).value)
            capital = float(self.query_one("#input-capital", Input).value)
            positions = int(self.query_one("#input-positions", Input).value)
            
            params = get_trading_params()
            params.min_spread = max(0.01, min(0.20, spread))
            params.capital_per_trade = max(1, min(1000, capital))
            params.max_open_positions = max(1, min(20, positions))
            
            return params
        except (ValueError, TypeError):
            return get_trading_params()


class OpportunitiesTable(Static):
    """Table des opportunités."""
    
    def compose(self) -> ComposeResult:
        yield DataTable(id="opportunities-table")
    
    def on_mount(self) -> None:
        """Configure la table au montage."""
        table = self.query_one("#opportunities-table", DataTable)
        table.add_columns(
            "Score", "Marché", "Spread", "Volume", "Prix YES", "Prix NO", "Action"
        )
        table.cursor_type = "row"
    
    def update_opportunities(self, opportunities: list[Opportunity]) -> None:
        """Met à jour la table avec les nouvelles opportunités."""
        table = self.query_one("#opportunities-table", DataTable)
        table.clear()
        
        for opp in opportunities[:15]:  # Max 15 lignes
            # Score en étoiles
            stars = "⭐" * opp.score
            
            # Marché (tronqué)
            market = opp.question[:40] + "..." if len(opp.question) > 40 else opp.question
            
            # Spread formaté
            spread = f"${opp.effective_spread:.3f}"
            
            # Volume formaté
            if opp.volume >= 1000000:
                volume = f"${opp.volume/1000000:.1f}M"
            elif opp.volume >= 1000:
                volume = f"${opp.volume/1000:.1f}k"
            else:
                volume = f"${opp.volume:.0f}"
            
            # Prix
            price_yes = f"${opp.best_ask_yes:.2f}"
            price_no = f"${opp.best_ask_no:.2f}"
            
            # Action
            if opp.action.value == "trade":
                action = "🚀 TRADE"
            elif opp.action.value == "watch":
                action = "👀 WATCH"
            else:
                action = "⏭️ SKIP"
            
            table.add_row(stars, market, spread, volume, price_yes, price_no, action)


class StatsPanel(Static):
    """Panneau de statistiques."""
    
    def compose(self) -> ComposeResult:
        with Horizontal(classes="stats-row"):
            with Vertical(classes="stat-box"):
                yield Label("📈 Trades Aujourd'hui", classes="stat-label")
                yield Static("0", id="stat-trades", classes="stat-value")
            
            with Vertical(classes="stat-box"):
                yield Label("✅ Win Rate", classes="stat-label")
                yield Static("0%", id="stat-winrate", classes="stat-value")
            
            with Vertical(classes="stat-box"):
                yield Label("💵 PnL Jour", classes="stat-label")
                yield Static("$0.00", id="stat-pnl", classes="stat-value")
            
            with Vertical(classes="stat-box"):
                yield Label("📊 Positions", classes="stat-label")
                yield Static("0", id="stat-positions", classes="stat-value")
    
    def update_stats(
        self,
        trades: int = 0,
        win_rate: float = 0,
        pnl: float = 0,
        positions: int = 0
    ) -> None:
        """Met à jour les statistiques."""
        self.query_one("#stat-trades", Static).update(str(trades))
        self.query_one("#stat-winrate", Static).update(f"{win_rate:.1f}%")
        
        pnl_str = f"${pnl:+.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
        pnl_widget = self.query_one("#stat-pnl", Static)
        pnl_widget.update(pnl_str)
        pnl_widget.set_class(pnl >= 0, "positive")
        pnl_widget.set_class(pnl < 0, "negative")
        
        self.query_one("#stat-positions", Static).update(str(positions))


class ActivityLog(Static):
    """Log d'activité."""
    
    def compose(self) -> ComposeResult:
        yield Log(id="activity-log", max_lines=100)
    
    def log(self, message: str, level: str = "info") -> None:
        """Ajoute une entrée au log."""
        log_widget = self.query_one("#activity-log", Log)
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        icons = {
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
            "trade": "🚀",
            "opportunity": "🎯",
        }
        icon = icons.get(level, "•")
        
        log_widget.write_line(f"[{timestamp}] {icon} {message}")


class HFTScalperApp(App):
    """Application principale HFT Scalper."""
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    #main-container {
        height: 100%;
        padding: 1;
    }
    
    .panel {
        border: solid $primary;
        padding: 1;
        margin-bottom: 1;
    }
    
    .panel-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    
    StatusPanel {
        height: 3;
        background: $surface-darken-1;
        padding: 0 1;
    }
    
    TradingParamsPanel {
        height: auto;
    }
    
    .params-row {
        height: auto;
        margin-bottom: 1;
    }
    
    .param-group {
        width: 1fr;
        padding: 0 1;
    }
    
    .param-label {
        text-style: bold;
        margin-bottom: 0;
    }
    
    .param-input {
        width: 100%;
    }
    
    .param-hint {
        color: $text-muted;
        text-style: italic;
    }
    
    #btn-save-params {
        margin-top: 1;
        width: 100%;
    }
    
    OpportunitiesTable {
        height: 1fr;
        min-height: 10;
    }
    
    #opportunities-table {
        height: 100%;
    }
    
    StatsPanel {
        height: auto;
    }
    
    .stats-row {
        height: auto;
    }
    
    .stat-box {
        width: 1fr;
        padding: 1;
        background: $surface-darken-1;
        margin: 0 1;
        text-align: center;
    }
    
    .stat-label {
        color: $text-muted;
    }
    
    .stat-value {
        text-style: bold;
        color: $primary;
    }
    
    .stat-value.positive {
        color: $success;
    }
    
    .stat-value.negative {
        color: $error;
    }
    
    ActivityLog {
        height: 8;
    }
    
    #activity-log {
        height: 100%;
        background: $surface-darken-2;
    }
    
    .buttons-row {
        height: auto;
        padding: 1;
    }
    
    .buttons-row Button {
        margin: 0 1;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quitter"),
        Binding("r", "refresh", "Rafraîchir"),
        Binding("p", "toggle_pause", "Pause/Resume"),
        Binding("w", "connect_wallet", "Wallet"),
        Binding("s", "focus_spread", "Spread"),
        Binding("c", "focus_capital", "Capital"),
    ]
    
    def __init__(self):
        super().__init__()
        self.title = "🚀 Polymarket HFT Scalper"
        self.sub_title = "v1.0.0"
        
        # Composants
        self._scanner: Optional[MarketScanner] = None
        self._analyzer: Optional[OpportunityAnalyzer] = None
        self._executor: Optional[OrderExecutor] = None
        self._order_manager: Optional[OrderManager] = None
        self._credentials_manager = CredentialsManager()
        
        # État
        self._opportunities: list[Opportunity] = []
        self._is_paused = False
        self._wallet_connected = False
    
    def compose(self) -> ComposeResult:
        yield Header()
        
        with Container(id="main-container"):
            # Status
            yield StatusPanel(id="status-panel")
            
            # Paramètres
            with Container(classes="panel"):
                yield Label("⚙️ Paramètres de Trading", classes="panel-title")
                yield TradingParamsPanel(id="params-panel")
            
            # Opportunités
            with Container(classes="panel"):
                yield Label("🎯 Opportunités Détectées", classes="panel-title")
                yield OpportunitiesTable(id="opportunities-panel")
            
            # Stats
            with Container(classes="panel"):
                yield Label("📊 Statistiques", classes="panel-title")
                yield StatsPanel(id="stats-panel")
            
            # Log
            with Container(classes="panel"):
                yield Label("📋 Activité", classes="panel-title")
                yield ActivityLog(id="log-panel")
            
            # Boutons
            with Horizontal(classes="buttons-row"):
                yield Button("▶️ Démarrer", id="btn-start", variant="success")
                yield Button("⏸️ Pause", id="btn-pause", variant="warning")
                yield Button("💳 Wallet", id="btn-wallet", variant="primary")
                yield Button("🔄 Refresh", id="btn-refresh", variant="default")
        
        yield Footer()
    
    async def on_mount(self) -> None:
        """Au montage de l'application."""
        self._log("Application démarrée")
        self._log("Appuyez sur 'Démarrer' pour lancer le scanner")
        
        # Timer pour l'uptime
        self.set_interval(1, self._update_uptime)
    
    def _log(self, message: str, level: str = "info") -> None:
        """Ajoute un message au log."""
        log_panel = self.query_one("#log-panel", ActivityLog)
        log_panel.log(message, level)
    
    def _update_uptime(self) -> None:
        """Met à jour l'uptime."""
        status = self.query_one("#status-panel", StatusPanel)
        status.update_uptime()
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Gère les clics sur les boutons."""
        button_id = event.button.id
        
        if button_id == "btn-start":
            await self._start_scanner()
        elif button_id == "btn-pause":
            self._toggle_pause()
        elif button_id == "btn-wallet":
            await self._connect_wallet()
        elif button_id == "btn-refresh":
            await self._refresh_markets()
        elif button_id == "btn-save-params":
            self._save_params()
    
    @work(exclusive=True)
    async def _start_scanner(self) -> None:
        """Démarre le scanner."""
        self._log("Démarrage du scanner...")
        
        try:
            # Initialiser les composants
            self._order_manager = OrderManager()
            self._analyzer = OpportunityAnalyzer()
            self._scanner = MarketScanner()
            
            # Configurer les callbacks
            self._scanner.on_state_change = self._on_scanner_state_change
            self._scanner.on_market_update = self._on_market_update
            self._scanner.on_error = self._on_scanner_error
            
            # Démarrer
            await self._scanner.start()
            
            self._log("Scanner démarré", "success")
            self._log(f"{self._scanner.market_count} marchés détectés", "info")
            
            # Mettre à jour le status
            status = self.query_one("#status-panel", StatusPanel)
            status.update_api(True)
            
            # Boucle d'analyse
            self._start_analysis_loop()
            
        except Exception as e:
            self._log(f"Erreur: {e}", "error")
    
    def _on_scanner_state_change(self, state: ScannerState) -> None:
        """Callback changement d'état du scanner."""
        status = self.query_one("#status-panel", StatusPanel)
        status.update_scanner(state)
    
    def _on_market_update(self, market_data: MarketData) -> None:
        """Callback mise à jour d'un marché."""
        pass  # Traité dans la boucle d'analyse
    
    def _on_scanner_error(self, error: Exception) -> None:
        """Callback erreur du scanner."""
        self._log(f"Erreur scanner: {error}", "error")
    
    def _start_analysis_loop(self) -> None:
        """Démarre la boucle d'analyse."""
        self.set_interval(2, self._analyze_markets)
    
    async def _analyze_markets(self) -> None:
        """Analyse les marchés et met à jour l'interface."""
        if not self._scanner or not self._analyzer:
            return
        
        if self._is_paused:
            return
        
        try:
            # Analyser les marchés
            markets = self._scanner.markets
            opportunities = self._analyzer.analyze_all_markets(markets)
            
            self._opportunities = opportunities
            
            # Mettre à jour la table
            table = self.query_one("#opportunities-panel", OpportunitiesTable)
            table.update_opportunities(opportunities)
            
            # Mettre à jour les stats
            stats = self.query_one("#stats-panel", StatsPanel)
            if self._order_manager:
                om_stats = self._order_manager.stats
                stats.update_stats(
                    trades=om_stats["total_trades"],
                    win_rate=om_stats["win_rate"],
                    pnl=self._order_manager.get_daily_pnl(),
                    positions=om_stats["open_positions"]
                )
            
            # Exécuter les trades si wallet connecté
            if self._wallet_connected and self._executor:
                tradeable = [o for o in opportunities if self._analyzer.should_trade(o)]
                for opp in tradeable[:1]:  # Un trade à la fois
                    self._log(f"Trade: {opp.question[:30]}...", "trade")
                    result = await self._executor.execute_opportunity(opp)
                    if result.success:
                        self._log(f"Trade réussi!", "success")
                    else:
                        self._log(f"Échec: {result.error_message}", "error")
            
        except Exception as e:
            self._log(f"Erreur analyse: {e}", "error")
    
    def _toggle_pause(self) -> None:
        """Bascule pause/resume."""
        self._is_paused = not self._is_paused
        
        if self._is_paused:
            self._log("Scanner en pause", "warning")
            if self._scanner:
                self._scanner.pause()
        else:
            self._log("Scanner repris", "success")
            if self._scanner:
                self._scanner.resume()
    
    async def _connect_wallet(self) -> None:
        """Connecte le wallet."""
        self._log("Connexion wallet... (voir terminal)", "info")
        
        try:
            credentials = await self._credentials_manager.get_credentials(require_wallet=True)
            
            if credentials.is_complete():
                # Initialiser l'executor
                poly_creds = PolymarketCredentials(
                    api_key=credentials.polymarket_api_key or "",
                    api_secret=credentials.polymarket_api_secret or ""
                )
                
                self._executor = OrderExecutor(poly_creds, self._order_manager)
                success = await self._executor.start()
                
                if success:
                    self._wallet_connected = True
                    status = self.query_one("#status-panel", StatusPanel)
                    status.update_wallet(credentials.wallet_address)
                    self._log("Wallet connecté!", "success")
                else:
                    self._log("Échec connexion wallet", "error")
            else:
                self._log("Credentials incomplètes", "error")
                
        except Exception as e:
            self._log(f"Erreur wallet: {e}", "error")
    
    async def _refresh_markets(self) -> None:
        """Force un rafraîchissement."""
        if self._scanner:
            self._log("Rafraîchissement...")
            await self._scanner.force_refresh()
            self._log("Rafraîchissement terminé", "success")
    
    def _save_params(self) -> None:
        """Sauvegarde les paramètres."""
        params_panel = self.query_one("#params-panel", TradingParamsPanel)
        params = params_panel.get_params()
        
        errors = params.validate()
        if errors:
            for error in errors:
                self._log(f"Erreur: {error}", "error")
            return
        
        update_trading_params(params)
        
        if self._analyzer:
            self._analyzer.update_params(params)
        if self._executor:
            self._executor.update_params(params)
        
        self._log("Paramètres sauvegardés", "success")
    
    def action_quit(self) -> None:
        """Quitte l'application."""
        self.exit()
    
    def action_refresh(self) -> None:
        """Raccourci rafraîchissement."""
        asyncio.create_task(self._refresh_markets())
    
    def action_toggle_pause(self) -> None:
        """Raccourci pause."""
        self._toggle_pause()
    
    def action_connect_wallet(self) -> None:
        """Raccourci wallet."""
        asyncio.create_task(self._connect_wallet())
    
    def action_focus_spread(self) -> None:
        """Focus sur l'input spread."""
        self.query_one("#input-spread", Input).focus()
    
    def action_focus_capital(self) -> None:
        """Focus sur l'input capital."""
        self.query_one("#input-capital", Input).focus()
