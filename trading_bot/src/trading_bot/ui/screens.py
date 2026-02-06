from __future__ import annotations

import yaml
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static, TextArea

from trading_bot.core.config import AppConfig
from trading_bot.engine.state import EngineSnapshot
from trading_bot.ui.widgets import fmt_bps, fmt_float, fmt_pct, fmt_uptime


class DashboardScreen(Screen):
    BINDINGS = []

    def compose(self):
        yield Header(show_clock=True)
        with Vertical():
            yield Static("", id="status")
            with Horizontal():
                yield DataTable(id="rank_table")
                yield DataTable(id="pos_table")
            yield Static("", id="events")
        yield Footer()

    def on_mount(self) -> None:
        rank = self.query_one("#rank_table", DataTable)
        rank.add_columns("Symbol", "Score", "Strategy", "Signal", "Vol", "Trend", "Mom", "Cost", "Reasons")
        rank.cursor_type = "row"

        pos = self.query_one("#pos_table", DataTable)
        pos.add_columns("Symbol", "Side", "Vol", "Open", "SL", "TP", "PnL")
        pos.cursor_type = "row"

    def refresh_data(self, snap: EngineSnapshot) -> None:
        status = self.query_one("#status", Static)
        connected = "CONNECTED" if snap.connected else "DISCONNECTED"
        paused = "PAUSED" if snap.paused else "RUNNING"
        enabled = "TRADING_ENABLED" if snap.trading_enabled else "READ_ONLY"
        status.update(
            f"Status: {connected} | {paused} | {enabled} | "
            f"Last cycle: {snap.last_cycle_id or 'N/A'} | "
            f"Candle close: {snap.last_candle_close_time_utc or 'N/A'} | "
            f"Latency: {fmt_float(snap.last_cycle_latency_ms, ndp=0)} ms | "
            f"Today PnL: {fmt_float(snap.today_pnl, ndp=2)} | W/L: {snap.wins}/{snap.losses}"
        )

        rank = self.query_one("#rank_table", DataTable)
        rank.clear()
        app = self.app  # type: ignore[attr-defined]
        for r in snap.top_ranked:
            strat = ""
            sig = ""
            try:
                row = app.db.query_one(
                    "SELECT strategy, signal_json FROM decisions WHERE symbol=? ORDER BY id DESC LIMIT 1",
                    (r.symbol,),
                )
                if row:
                    strat = str(row["strategy"] or "")
                    import json

                    sj = json.loads(row["signal_json"] or "{}")
                    sig_side = str(sj.get("side") or "")
                    sig_reason = str(sj.get("reason") or "")
                    sig = f"{sig_side} {sig_reason[:24]}".strip()
            except Exception:
                pass
            rank.add_row(
                r.symbol,
                f"{r.score:.3f}",
                strat,
                sig,
                f"{r.components.get('volatility', 0.0):.2f}",
                f"{r.components.get('trend', 0.0):.2f}",
                f"{r.components.get('momentum', 0.0):.2f}",
                f"{r.components.get('cost', 0.0):.2f}",
                "; ".join(r.reasons)[:80],
            )

        pos = self.query_one("#pos_table", DataTable)
        pos.clear()
        for p in snap.open_positions:
            pos.add_row(
                p.symbol,
                p.side,
                f"{p.volume:g}",
                f"{p.price_open:g}",
                f"{p.sl:g}" if p.sl is not None else "",
                f"{p.tp:g}" if p.tp is not None else "",
                f"{p.profit:g}" if p.profit is not None else "",
            )

        events = self.query_one("#events", Static)
        lines = []
        for e in snap.last_events[:10]:
            lines.append(f"- {e}")
        for e in snap.last_errors[:10]:
            lines.append(f"! {e}")
        events.update("Recent:\n" + "\n".join(lines))


class TradesScreen(Screen):
    def compose(self):
        yield Header(show_clock=True)
        yield DataTable(id="trades_table")
        yield Footer()

    def on_mount(self) -> None:
        t = self.query_one("#trades_table", DataTable)
        t.add_columns("Time", "Symbol", "Side", "Entry", "Vol", "Price", "Profit", "Comment")
        t.cursor_type = "row"

    def refresh_data(self, snap: EngineSnapshot) -> None:
        app = self.app  # type: ignore[attr-defined]
        rows = app.db.trade_repo().list_recent(200)
        t = self.query_one("#trades_table", DataTable)
        t.clear()
        for r in rows[:200]:
            t.add_row(
                str(r.get("time_utc", ""))[:19],
                str(r.get("symbol", "")),
                str(r.get("side", "")),
                str(r.get("entry", "")),
                str(r.get("volume", "")),
                str(r.get("price", "")),
                str(r.get("profit", "")) if r.get("profit") is not None else "",
                str(r.get("comment", ""))[:30],
            )


class DecisionsScreen(Screen):
    def compose(self):
        yield Header(show_clock=True)
        yield DataTable(id="decisions_table")
        yield Footer()

    def on_mount(self) -> None:
        t = self.query_one("#decisions_table", DataTable)
        t.add_columns("Time", "Cycle", "Symbol", "Strategy", "Status", "Side", "Reason", "Score")
        t.cursor_type = "row"

    def refresh_data(self, snap: EngineSnapshot) -> None:
        app = self.app  # type: ignore[attr-defined]
        rows = app.db.decision_repo().list_recent(200)
        t = self.query_one("#decisions_table", DataTable)
        t.clear()
        for r in rows[:200]:
            signal = r.get("signal_json") or ""
            side = ""
            reason = ""
            try:
                import json

                sj = json.loads(signal) if signal else {}
                side = str(sj.get("side") or "")
                reason = str(sj.get("reason") or "")
            except Exception:
                pass
            t.add_row(
                str(r.get("created_at", ""))[:19],
                str(r.get("cycle_id", "")),
                str(r.get("symbol", "")),
                str(r.get("strategy") or ""),
                str(r.get("status", "")),
                side,
                reason[:40],
                f"{float(r.get('rank_score') or 0.0):.3f}" if r.get("rank_score") is not None else "",
            )


class SettingsScreen(Screen):
    def compose(self):
        yield Header(show_clock=True)
        with Container():
            yield Static("Edit config YAML and press S to save.", id="settings_help")
            yield Static("", id="settings_status")
            yield TextArea("", id="settings_editor")
        yield Footer()

    def on_mount(self) -> None:
        app = self.app  # type: ignore[attr-defined]
        editor = self.query_one("#settings_editor", TextArea)
        cfg_dict = app.config.model_dump()
        editor.text = yaml.safe_dump(cfg_dict, sort_keys=False)
        editor.language = "yaml"

    def save_settings(self) -> tuple[bool, str]:
        app = self.app  # type: ignore[attr-defined]
        editor = self.query_one("#settings_editor", TextArea)
        status = self.query_one("#settings_status", Static)
        try:
            cfg_raw = yaml.safe_load(editor.text) or {}
            cfg = AppConfig.model_validate(cfg_raw)
        except Exception as exc:
            status.update(f"Validation error: {exc}")
            return False, str(exc)
        status.update("Saved. Applying...")
        app.engine.enqueue(app.engine_command("apply_config", {"config": cfg_raw}))
        app.config = cfg
        return True, "ok"

    def refresh_data(self, snap: EngineSnapshot) -> None:
        # No auto-refresh needed; keep editor stable.
        pass


class ResourcesScreen(Screen):
    def compose(self):
        yield Header(show_clock=True)
        yield Static("", id="res_text")
        yield Footer()

    def refresh_data(self, snap: EngineSnapshot) -> None:
        r = snap.resources or {}
        text = (
            f"CPU: {fmt_pct(r.get('cpu_pct'))}  "
            f"RAM: {fmt_pct(r.get('ram_pct'))}  "
            f"Disk: {fmt_pct(r.get('disk_pct'))}\n"
            f"Uptime: {fmt_uptime(r.get('uptime_seconds'))}  "
            f"Net RX: {fmt_bps(r.get('net_rx_bps'))}  "
            f"Net TX: {fmt_bps(r.get('net_tx_bps'))}\n"
            f"Temp: {fmt_float(r.get('temp_c'), ndp=1)} C"
        )
        self.query_one("#res_text", Static).update(text)
