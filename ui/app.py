"""
HFT Scalper App - Interface Premium Textual

Interface haute qualité avec:
- Design moderne dark mode
- Animations fluides
- Widgets interactifs
- Couleurs harmonieuses
"""

import asyncio
from datetime import datetime
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, Grid
from textual.widgets import (
    Header, Footer, Static, Button, DataTable,
    Input, Label, Log, Rule, Sparkline
)
from textual.binding import Binding
from textual.reactive import reactive
from textual import work

from config import get_settings, get_trading_params, TradingParams, update_trading_params
from core import MarketScanner, OpportunityAnalyzer, Opportunity, OrderExecutor, OrderManager
from core.scanner import ScannerState, MarketData
from core.analyzer import OpportunityAction
from api.private import PolymarketCredentials, CredentialsManager


class GradientHeader(Static):
    """Header avec gradient."""
    
    def compose(self) -> ComposeResult:
        yield Static(
            "🚀 POLYMARKET HFT SCALPER",
            id="header-title"
        )


class StatusBar(Static):
    """Barre de statut moderne."""
    
    scanner_status = reactive("⏹️ Arrêté")
    api_status = reactive("⚪ Déconnecté")
    wallet_status = reactive("🔒 Non connecté")
    uptime = reactive("00:00:00")
    markets_count = reactive(0)
    
    def compose(self) -> ComposeResult:
        with Horizontal(id="status-bar"):
            yield Static("", id="status-scanner")
            yield Static("│", classes="separator")
            yield Static("", id="status-api")
            yield Static("│", classes="separator")
            yield Static("", id="status-wallet")
            yield Static("│", classes="separator")
            yield Static("", id="status-uptime")
            yield Static("│", classes="separator")
            yield Static("", id="status-markets")
    
    def watch_scanner_status(self, value: str) -> None:
        self.query_one("#status-scanner", Static).update(f"Scanner: {value}")
    
    def watch_api_status(self, value: str) -> None:
        self.query_one("#status-api", Static).update(f"API: {value}")
    
    def watch_wallet_status(self, value: str) -> None:
        self.query_one("#status-wallet", Static).update(f"Wallet: {value}")
    
    def watch_uptime(self, value: str) -> None:
        self.query_one("#status-uptime", Static).update(f"⏱️ {value}")
    
    def watch_markets_count(self, value: int) -> None:
        self.query_one("#status-markets", Static).update(f"📊 {value} marchés")


class StatsCard(Static):
    """Carte de statistique individuelle."""
    
    def __init__(self, title: str, value: str, icon: str, card_id: str, **kwargs):
        super().__init__(**kwargs)
        self._title = title
        self._value = value
        self._icon = icon
        self._card_id = card_id
    
    def compose(self) -> ComposeResult:
        with Vertical(classes="stat-card"):
            yield Static(f"{self._icon} {self._title}", classes="stat-title")
            yield Static(self._value, id=self._card_id, classes="stat-value")


class StatsPanel(Static):
    """Panneau de statistiques."""
    
    def compose(self) -> ComposeResult:
        yield Static("📊 STATISTIQUES", classes="panel-title")
        with Grid(id="stats-grid"):
            yield StatsCard("Trades", "0", "📈", "stat-trades")
            yield StatsCard("Win Rate", "0%", "🎯", "stat-winrate")
            yield StatsCard("PnL Jour", "$0.00", "💰", "stat-pnl")
            yield StatsCard("Positions", "0/5", "📊", "stat-positions")
    
    def update_stats(self, trades: int, winrate: float, pnl: float, positions: int, max_pos: int):
        self.query_one("#stat-trades", Static).update(str(trades))
        self.query_one("#stat-winrate", Static).update(f"{winrate:.1f}%")
        
        pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
        pnl_widget = self.query_one("#stat-pnl", Static)
        pnl_widget.update(pnl_str)
        pnl_widget.set_class(pnl >= 0, "positive")
        pnl_widget.set_class(pnl < 0, "negative")
        
        self.query_one("#stat-positions", Static).update(f"{positions}/{max_pos}")


class TradingConfig(Static):
    """Panneau de configuration trading."""
    
    def compose(self) -> ComposeResult:
        params = get_trading_params()
        
        yield Static("⚙️ CONFIGURATION", classes="panel-title")
        
        with Horizontal(classes="config-row"):
            with Vertical(classes="config-item"):
                yield Label("💹 Spread Minimum ($)")
                yield Input(
                    value=str(params.min_spread),
                    id="input-spread",
                    placeholder="0.04"
                )
            
            with Vertical(classes="config-item"):
                yield Label("💰 Capital / Trade ($)")
                yield Input(
                    value=str(params.capital_per_trade),
                    id="input-capital",
                    placeholder="50"
                )
            
            with Vertical(classes="config-item"):
                yield Label("📊 Positions Max")
                yield Input(
                    value=str(params.max_open_positions),
                    id="input-maxpos",
                    placeholder="5"
                )
        
        with Horizontal(classes="config-buttons"):
            yield Button("💾 Sauvegarder", id="btn-save", variant="primary")
            yield Button("🔄 Reset", id="btn-reset", variant="default")


class OpportunitiesPanel(Static):
    """Panneau des opportunités."""
    
    def compose(self) -> ComposeResult:
        yield Static("🎯 OPPORTUNITÉS EN TEMPS RÉEL", classes="panel-title")
        yield DataTable(id="opp-table", zebra_stripes=True)
    
    def on_mount(self) -> None:
        table = self.query_one("#opp-table", DataTable)
        table.add_columns("Score", "Marché", "Spread", "Volume", "YES", "NO", "Action")
        table.cursor_type = "row"
    
    def update_opportunities(self, opportunities: list[Opportunity]) -> None:
        table = self.query_one("#opp-table", DataTable)
        table.clear()
        
        for opp in opportunities[:12]:
            # Score avec couleur
            if opp.score >= 4:
                stars = f"[green]{'⭐' * opp.score}[/green]"
            elif opp.score >= 3:
                stars = f"[yellow]{'⭐' * opp.score}[/yellow]"
            else:
                stars = f"[dim]{'⭐' * opp.score}[/dim]"
            
            # Marché tronqué
            market = opp.question[:35] + "..." if len(opp.question) > 35 else opp.question
            
            # Spread
            spread = f"[bold cyan]${opp.effective_spread:.3f}[/bold cyan]"
            
            # Volume
            if opp.volume >= 1000000:
                vol = f"${opp.volume/1000000:.1f}M"
            elif opp.volume >= 1000:
                vol = f"${opp.volume/1000:.1f}k"
            else:
                vol = f"${opp.volume:.0f}"
            
            # Prix
            yes_price = f"${opp.best_ask_yes:.2f}"
            no_price = f"${opp.best_ask_no:.2f}"
            
            # Action
            if opp.action == OpportunityAction.TRADE:
                action = "[bold green]🚀 TRADE[/bold green]"
            elif opp.action == OpportunityAction.WATCH:
                action = "[yellow]👀 WATCH[/yellow]"
            else:
                action = "[dim]⏭️ SKIP[/dim]"
            
            table.add_row(stars, market, spread, vol, yes_price, no_price, action)


class ActivityPanel(Static):
    """Panneau d'activité."""
    
    def compose(self) -> ComposeResult:
        yield Static("📋 ACTIVITÉ", classes="panel-title")
        yield Log(id="activity-log", max_lines=50, highlight=True)
    
    def log(self, message: str, level: str = "info") -> None:
        log_widget = self.query_one("#activity-log", Log)
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        icons = {
            "info": "[cyan]ℹ️[/cyan]",
            "success": "[green]✅[/green]",
            "warning": "[yellow]⚠️[/yellow]",
            "error": "[red]❌[/red]",
            "trade": "[bold green]🚀[/bold green]",
            "opportunity": "[magenta]🎯[/magenta]",
        }
        icon = icons.get(level, "•")
        
        log_widget.write_line(f"[dim]{timestamp}[/dim] {icon} {message}")


class ControlPanel(Static):
    """Panneau de contrôle."""
    
    def compose(self) -> ComposeResult:
        with Horizontal(id="control-buttons"):
            yield Button("▶️ Démarrer", id="btn-start", variant="success")
            yield Button("⏸️ Pause", id="btn-pause", variant="warning")
            yield Button("💳 Wallet", id="btn-wallet", variant="primary")
            yield Button("🔄 Refresh", id="btn-refresh", variant="default")


class HFTScalperApp(App):
    """Application principale HFT Scalper."""
    
    CSS = """
    Screen {
        background: #0d1117;
    }
    
    /* Header */
    #header-title {
        text-align: center;
        text-style: bold;
        color: #58a6ff;
        background: linear-gradient(90deg, #0d1117, #161b22, #0d1117);
        padding: 1;
        border: heavy #30363d;
    }
    
    /* Status Bar */
    #status-bar {
        background: #161b22;
        padding: 0 2;
        height: 3;
        border: solid #30363d;
    }
    
    #status-bar Static {
        padding: 1 2;
        color: #8b949e;
    }
    
    .separator {
        color: #30363d;
        width: 1;
        padding: 1 0;
    }
    
    /* Main Layout */
    #main-container {
        padding: 1;
    }
    
    #left-panel {
        width: 35%;
        padding-right: 1;
    }
    
    #right-panel {
        width: 65%;
        padding-left: 1;
    }
    
    /* Panels */
    .panel {
        background: #161b22;
        border: solid #30363d;
        padding: 1 2;
        margin-bottom: 1;
    }
    
    .panel-title {
        text-style: bold;
        color: #58a6ff;
        margin-bottom: 1;
        text-align: center;
    }
    
    /* Stats Grid */
    #stats-grid {
        grid-size: 2 2;
        grid-gutter: 1;
        height: auto;
    }
    
    .stat-card {
        background: #0d1117;
        border: solid #30363d;
        padding: 1;
        text-align: center;
    }
    
    .stat-title {
        color: #8b949e;
        text-style: italic;
    }
    
    .stat-value {
        text-style: bold;
        color: #58a6ff;
    }
    
    .stat-value.positive {
        color: #3fb950;
    }
    
    .stat-value.negative {
        color: #f85149;
    }
    
    /* Config */
    .config-row {
        height: auto;
        margin-bottom: 1;
    }
    
    .config-item {
        width: 1fr;
        padding: 0 1;
    }
    
    .config-item Label {
        color: #8b949e;
        margin-bottom: 0;
    }
    
    .config-item Input {
        background: #0d1117;
        border: solid #30363d;
        color: #c9d1d9;
    }
    
    .config-item Input:focus {
        border: solid #58a6ff;
    }
    
    .config-buttons {
        margin-top: 1;
    }
    
    .config-buttons Button {
        margin-right: 1;
    }
    
    /* Opportunities Table */
    #opp-table {
        height: 100%;
        background: #0d1117;
    }
    
    DataTable > .datatable--header {
        background: #21262d;
        color: #58a6ff;
        text-style: bold;
    }
    
    DataTable > .datatable--cursor {
        background: #1f6feb;
    }
    
    /* Activity Log */
    #activity-log {
        background: #0d1117;
        border: solid #30363d;
        height: 100%;
        min-height: 8;
    }
    
    /* Control Panel */
    #control-buttons {
        padding: 1;
        background: #161b22;
        border: solid #30363d;
    }
    
    #control-buttons Button {
        margin: 0 1;
    }
    
    /* Buttons */
    Button {
        min-width: 16;
    }
    
    Button.-primary {
        background: #238636;
    }
    
    Button.-success {
        background: #238636;
    }
    
    Button.-warning {
        background: #9e6a03;
    }
    
    Button:hover {
        background: $accent-lighten-1;
    }
    
    /* Footer */
    Footer {
        background: #161b22;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quitter"),
        Binding("r", "refresh", "Refresh"),
        Binding("p", "pause", "Pause"),
        Binding("w", "wallet", "Wallet"),
        Binding("s", "start", "Start"),
    ]
    
    def __init__(self):
        super().__init__()
        self._scanner: Optional[MarketScanner] = None
        self._analyzer: Optional[OpportunityAnalyzer] = None
        self._executor: Optional[OrderExecutor] = None
        self._order_manager: Optional[OrderManager] = None
        self._credentials_manager = CredentialsManager()
        
        self._opportunities: list[Opportunity] = []
        self._is_paused = False
        self._is_running = False
        self._wallet_connected = False
        self._start_time = datetime.now()
    
    def compose(self) -> ComposeResult:
        yield GradientHeader()
        yield StatusBar(id="status-bar-widget")
        
        with Horizontal(id="main-container"):
            with Vertical(id="left-panel"):
                with Container(classes="panel"):
                    yield StatsPanel(id="stats-panel")
                
                with Container(classes="panel"):
                    yield TradingConfig(id="config-panel")
                
                with Container(classes="panel"):
                    yield ActivityPanel(id="activity-panel")
            
            with Vertical(id="right-panel"):
                with Container(classes="panel", id="opp-container"):
                    yield OpportunitiesPanel(id="opp-panel")
        
        yield ControlPanel(id="control-panel")
        yield Footer()
    
    def on_mount(self) -> None:
        self._log("🚀 Bot HFT Polymarket démarré")
        self._log("Cliquez 'Démarrer' pour lancer le scanner")
        self.set_interval(1, self._update_uptime)
    
    def _log(self, message: str, level: str = "info") -> None:
        try:
            panel = self.query_one("#activity-panel", ActivityPanel)
            panel.log(message, level)
        except Exception:
            pass
    
    def _update_uptime(self) -> None:
        elapsed = datetime.now() - self._start_time
        hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        status = self.query_one("#status-bar-widget", StatusBar)
        status.uptime = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        
        if btn_id == "btn-start":
            await self._start_scanner()
        elif btn_id == "btn-pause":
            self._toggle_pause()
        elif btn_id == "btn-wallet":
            await self._connect_wallet()
        elif btn_id == "btn-refresh":
            await self._refresh()
        elif btn_id == "btn-save":
            self._save_config()
        elif btn_id == "btn-reset":
            self._reset_config()
    
    @work(exclusive=True)
    async def _start_scanner(self) -> None:
        if self._is_running:
            return
        
        self._log("⏳ Démarrage du scanner...", "info")
        status = self.query_one("#status-bar-widget", StatusBar)
        status.scanner_status = "🔄 Démarrage..."
        
        try:
            self._order_manager = OrderManager()
            self._analyzer = OpportunityAnalyzer()
            self._scanner = MarketScanner()
            
            await self._scanner.start()
            self._is_running = True
            
            status.scanner_status = "🟢 Actif"
            status.api_status = "🟢 Connecté"
            status.markets_count = self._scanner.market_count
            
            self._log(f"✅ Scanner démarré - {self._scanner.market_count} marchés", "success")
            
            # Démarrer la boucle d'analyse
            self.set_interval(2, self._analyze_loop)
            
        except Exception as e:
            status.scanner_status = "🔴 Erreur"
            self._log(f"❌ Erreur: {e}", "error")
    
    async def _analyze_loop(self) -> None:
        if not self._scanner or not self._analyzer or self._is_paused:
            return
        
        try:
            markets = self._scanner.markets
            opportunities = self._analyzer.analyze_all_markets(markets)
            self._opportunities = opportunities
            
            # Mettre à jour l'interface
            opp_panel = self.query_one("#opp-panel", OpportunitiesPanel)
            opp_panel.update_opportunities(opportunities)
            
            status = self.query_one("#status-bar-widget", StatusBar)
            status.markets_count = len(markets)
            
            # Stats
            if self._order_manager:
                stats = self._order_manager.stats
                params = get_trading_params()
                stats_panel = self.query_one("#stats-panel", StatsPanel)
                stats_panel.update_stats(
                    trades=stats["total_trades"],
                    winrate=stats["win_rate"],
                    pnl=self._order_manager.get_daily_pnl(),
                    positions=stats["open_positions"],
                    max_pos=params.max_open_positions
                )
            
            # Trader automatiquement
            if self._wallet_connected and self._executor:
                tradeable = [o for o in opportunities if self._analyzer.should_trade(o)]
                for opp in tradeable[:1]:
                    self._log(f"🎯 Trade: {opp.question[:30]}...", "trade")
                    
        except Exception as e:
            self._log(f"Erreur analyse: {e}", "error")
    
    def _toggle_pause(self) -> None:
        self._is_paused = not self._is_paused
        status = self.query_one("#status-bar-widget", StatusBar)
        
        if self._is_paused:
            status.scanner_status = "⏸️ Pause"
            self._log("⏸️ Scanner en pause", "warning")
        else:
            status.scanner_status = "🟢 Actif"
            self._log("▶️ Scanner repris", "success")
    
    async def _connect_wallet(self) -> None:
        self._log("💳 Connexion wallet...", "info")
        self._log("Voir le terminal pour entrer vos credentials", "warning")
        
        try:
            credentials = await self._credentials_manager.get_credentials(require_wallet=True)
            
            if credentials.is_complete():
                poly_creds = PolymarketCredentials(
                    api_key=credentials.polymarket_api_key or "",
                    api_secret=credentials.polymarket_api_secret or ""
                )
                
                self._executor = OrderExecutor(poly_creds, self._order_manager)
                success = await self._executor.start()
                
                if success:
                    self._wallet_connected = True
                    status = self.query_one("#status-bar-widget", StatusBar)
                    addr = credentials.wallet_address or ""
                    status.wallet_status = f"💳 {addr[:6]}...{addr[-4:]}"
                    self._log("✅ Wallet connecté!", "success")
                else:
                    self._log("❌ Échec connexion", "error")
                    
        except Exception as e:
            self._log(f"❌ Erreur: {e}", "error")
    
    async def _refresh(self) -> None:
        if self._scanner:
            self._log("🔄 Rafraîchissement...", "info")
            await self._scanner.force_refresh()
            self._log("✅ Rafraîchi", "success")
    
    def _save_config(self) -> None:
        try:
            spread = float(self.query_one("#input-spread", Input).value)
            capital = float(self.query_one("#input-capital", Input).value)
            maxpos = int(self.query_one("#input-maxpos", Input).value)
            
            params = get_trading_params()
            params.min_spread = max(0.01, min(0.20, spread))
            params.capital_per_trade = max(1, min(1000, capital))
            params.max_open_positions = max(1, min(20, maxpos))
            
            update_trading_params(params)
            
            if self._analyzer:
                self._analyzer.update_params(params)
            
            self._log("💾 Configuration sauvegardée", "success")
            
        except Exception as e:
            self._log(f"❌ Erreur: {e}", "error")
    
    def _reset_config(self) -> None:
        params = TradingParams()
        self.query_one("#input-spread", Input).value = str(params.min_spread)
        self.query_one("#input-capital", Input).value = str(params.capital_per_trade)
        self.query_one("#input-maxpos", Input).value = str(params.max_open_positions)
        self._log("🔄 Configuration réinitialisée", "info")
    
    def action_quit(self) -> None:
        self.exit()
    
    def action_refresh(self) -> None:
        asyncio.create_task(self._refresh())
    
    def action_pause(self) -> None:
        self._toggle_pause()
    
    def action_wallet(self) -> None:
        asyncio.create_task(self._connect_wallet())
    
    def action_start(self) -> None:
        asyncio.create_task(self._start_scanner())
