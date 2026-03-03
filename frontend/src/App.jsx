import { useState, useEffect, useMemo } from "react";

// ═══════════════════════════════════════════════════════════════
//  KAT — KATHERINA'S AUTONOMOUS TRADER v2.0
//  Signal Aggregator Dashboard
//  Design: Swiss Institutional Terminal (Bloomberg meets Zurich)
// ═══════════════════════════════════════════════════════════════

// ── Design Tokens ──
const C = {
  bg0: "#050a14", bg1: "#0a1020", bg2: "#0f1628", bg3: "#141d32",
  bg4: "#1a2540", bgHover: "#1c2844",
  border0: "#141d32", border1: "#1e2d4a", border2: "#2a3d5e",
  text0: "#e4eaf4", text1: "#b8c5d9", text2: "#7e91ab", text3: "#4a5e7a",
  green: "#00dc82", greenMute: "#0b3a28", greenGlow: "0 0 8px rgba(0,220,130,0.25)",
  red: "#ff4757", redMute: "#2d0a12", redGlow: "0 0 8px rgba(255,71,87,0.25)",
  cyan: "#00b4d8", cyanMute: "#082838", cyanGlow: "0 0 8px rgba(0,180,216,0.2)",
  amber: "#f59e0b", amberMute: "#2d2200",
  purple: "#a78bfa",
  accentGrad: "linear-gradient(135deg, #00dc82, #00b4d8)",
};

const mono = "'IBM Plex Mono', 'Fira Code', 'SF Mono', monospace";
const sans = "'Outfit', 'DM Sans', system-ui, sans-serif";

// ── Mock Data ──
const SOURCES = [
  { id: "c2", name: "Collective2", short: "C2", type: "api_poll", status: "connected", color: C.cyan, signalsDay: 4, winRate: 72.3, pnlMtd: 2340, allocation: 23, maxAlloc: 30, latencyMs: 340, uptime: 99.8, lastSignal: "2m ago" },
  { id: "tp", name: "TradersPost", short: "TP", type: "webhook", status: "connected", color: C.green, signalsDay: 2, winRate: 64.8, pnlMtd: 580, allocation: 12, maxAlloc: 20, latencyMs: 120, uptime: 99.9, lastSignal: "18m ago" },
  { id: "holly", name: "Holly AI", short: "HL", type: "webhook", status: "connected", color: C.amber, signalsDay: 6, winRate: 68.1, pnlMtd: 1190, allocation: 18, maxAlloc: 20, latencyMs: 450, uptime: 98.2, lastSignal: "8m ago" },
  { id: "ss", name: "SignalStack", short: "SS", type: "webhook", status: "standby", color: C.text3, signalsDay: 0, winRate: 0, pnlMtd: 0, allocation: 0, maxAlloc: 10, latencyMs: 0, uptime: 0, lastSignal: "—" },
  { id: "int", name: "Internal", short: "IN", type: "internal", status: "active", color: C.purple, signalsDay: 3, winRate: 71.4, pnlMtd: 920, allocation: 28, maxAlloc: 40, latencyMs: 5, uptime: 100, lastSignal: "32m ago" },
];

const SIGNALS = [
  { id: 1, time: "14:23:05", src: "c2", action: "BUY", type: "FUT", sym: "@ESH6", qty: "2 ct", price: 5421.50, approved: true, strat: "ES Momentum Pro", confidence: 0.82 },
  { id: 2, time: "14:21:30", src: "holly", action: "BUY", type: "STK", sym: "NVDA", qty: "15 sh", price: 892.30, approved: true, strat: "Holly Grail", confidence: 0.76 },
  { id: 3, time: "14:18:45", src: "int", action: "STO", type: "OPT", sym: "TSLA IC", qty: "1 ct", price: null, approved: true, strat: "Iron Condor", confidence: 0.85 },
  { id: 4, time: "14:15:12", src: "c2", action: "SELL", type: "STK", sym: "META", qty: "20 sh", price: 612.40, approved: false, reason: ">15% concentration", strat: "C2 Swing Alpha", confidence: 0.71 },
  { id: 5, time: "14:10:00", src: "tp", action: "BUY", type: "STK", sym: "AMD", qty: "25 sh", price: 178.50, approved: true, strat: "TV Momentum", confidence: 0.69 },
  { id: 6, time: "14:05:33", src: "holly", action: "BUY", type: "STK", sym: "AAPL", qty: "10 sh", price: 241.20, approved: true, strat: "Holly 2.0", confidence: 0.73 },
  { id: 7, time: "13:58:17", src: "int", action: "BUY", type: "STK", sym: "MSFT", qty: "8 sh", price: 432.10, approved: true, strat: "Momentum RSI", confidence: 0.80 },
  { id: 8, time: "13:52:44", src: "c2", action: "BTO", type: "OPT", sym: "SPY 550C", qty: "3 ct", price: 12.40, approved: false, reason: "Options cap >30%", strat: "C2 Options Flow", confidence: 0.65 },
  { id: 9, time: "13:45:20", src: "holly", action: "SELL", type: "STK", sym: "GOOGL", qty: "12 sh", price: 178.90, approved: true, strat: "Holly Neo", confidence: 0.74 },
  { id: 10, time: "13:40:08", src: "tp", action: "BUY", type: "FUT", sym: "@NQM6", qty: "1 ct", price: 19850.00, approved: true, strat: "NQ Scalper", confidence: 0.77 },
  { id: 11, time: "13:32:15", src: "int", action: "BUY", type: "STK", sym: "AMZN", qty: "5 sh", price: 218.40, approved: true, strat: "Dividend Cap", confidence: 0.88 },
  { id: 12, time: "13:25:42", src: "holly", action: "BUY", type: "STK", sym: "CRM", qty: "8 sh", price: 312.50, approved: true, strat: "Holly Grail", confidence: 0.70 },
];

const POSITIONS = [
  { sym: "NVDA", qty: 15, avg: 892.30, cur: 898.40, pnl: 91.50, pct: 0.68, src: "holly", type: "STK", sl: 875.00 },
  { sym: "@ESH6", qty: 2, avg: 5421.50, cur: 5434.25, pnl: 637.50, pct: 0.24, src: "c2", type: "FUT", sl: 5390.00 },
  { sym: "TSLA IC", qty: 1, avg: 8.40, cur: 7.20, pnl: 120.00, pct: 14.3, src: "int", type: "OPT", sl: null },
  { sym: "AMD", qty: 25, avg: 178.50, cur: 180.10, pnl: 40.00, pct: 0.90, src: "tp", type: "STK", sl: 174.00 },
  { sym: "AAPL", qty: 10, avg: 241.20, cur: 240.80, pnl: -4.00, pct: -0.17, src: "holly", type: "STK", sl: 235.00 },
  { sym: "MSFT", qty: 8, avg: 432.10, cur: 435.60, pnl: 28.00, pct: 0.81, src: "int", type: "STK", sl: 425.00 },
  { sym: "@NQM6", qty: 1, avg: 19850, cur: 19872.50, pnl: 450.00, pct: 0.11, src: "tp", type: "FUT", sl: 19780.00 },
  { sym: "AMZN", qty: 5, avg: 218.40, cur: 220.15, pnl: 8.75, pct: 0.80, src: "int", type: "STK", sl: 212.00 },
  { sym: "CRM", qty: 8, avg: 312.50, cur: 310.80, pnl: -13.60, pct: -0.54, src: "holly", type: "STK", sl: 302.00 },
];

const GUARDIAN_CHECKS = [
  { id: 1, name: "Capital Available", status: "pass", detail: "$48,230 buying power", metric: "48230" },
  { id: 2, name: "Position Size", status: "pass", detail: "Largest: 1.8% (max 2%)", metric: "1.8%" },
  { id: 3, name: "Portfolio Heat", status: "pass", detail: "7.2% at risk (max 10%)", metric: "7.2%" },
  { id: 4, name: "Correlation", status: "pass", detail: "Max pair: 0.42 (max 0.70)", metric: "0.42" },
  { id: 5, name: "Concentration", status: "warn", detail: "NVDA at 13.2% (max 15%)", metric: "13.2%" },
  { id: 6, name: "Daily P&L", status: "pass", detail: "+$1,358 / +1.41%", metric: "+1.41%" },
  { id: 7, name: "Cash Reserve", status: "pass", detail: "25.1% held (min 20%)", metric: "25.1%" },
  { id: 8, name: "Stop-Loss", status: "pass", detail: "9/9 positions covered", metric: "9/9" },
  { id: 9, name: "Source Alloc", status: "pass", detail: "All within limits", metric: "OK" },
  { id: 10, name: "Compliance", status: "pass", detail: "No restricted symbols", metric: "Clear" },
];

// ── Utility ──
const fmt = (n, d = 0) => n?.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }) ?? "—";
const fmtPnl = (n) => `${n >= 0 ? "+" : ""}$${fmt(Math.abs(n), 2)}`;
const srcOf = (id) => SOURCES.find(s => s.id === id);
const pnlColor = (n) => n >= 0 ? C.green : C.red;

// ═══════════════════════════════════════════════════════════════
//  MICRO-COMPONENTS
// ═══════════════════════════════════════════════════════════════

function StatusDot({ status, size = 6 }) {
  const colors = { connected: C.green, active: C.green, standby: C.text3, error: C.red, halted: C.red };
  const col = colors[status] || C.text3;
  const glow = status === "connected" || status === "active";
  return <span style={{ display: "inline-block", width: size, height: size, borderRadius: "50%", background: col, boxShadow: glow ? `0 0 ${size}px ${col}` : "none", flexShrink: 0 }} />;
}

function Badge({ children, color = C.text2, bg }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", padding: "1px 6px", borderRadius: 3,
      fontSize: 10, fontWeight: 600, letterSpacing: 0.5,
      color, background: bg || `${color}18`, fontFamily: mono,
    }}>{children}</span>
  );
}

function Stat({ label, value, sub, color, small }) {
  return (
    <div style={{ background: C.bg2, border: `1px solid ${C.border0}`, borderRadius: 6, padding: small ? "10px 12px" : "12px 16px", flex: "1 1 140px", minWidth: 130 }}>
      <div style={{ fontSize: 9, color: C.text3, textTransform: "uppercase", letterSpacing: 1.2, fontFamily: sans, marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: small ? 18 : 22, fontWeight: 700, color: color || C.text0, fontFamily: mono, lineHeight: 1.1 }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: C.text3, marginTop: 3, fontFamily: mono }}>{sub}</div>}
    </div>
  );
}

function Panel({ title, badge, children, headerRight, noPad }) {
  return (
    <div style={{ background: C.bg2, border: `1px solid ${C.border0}`, borderRadius: 6, overflow: "hidden" }}>
      <div style={{
        padding: "8px 14px", borderBottom: `1px solid ${C.border0}`,
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: C.text0, fontFamily: sans, letterSpacing: 0.3 }}>{title}</span>
          {badge}
        </div>
        {headerRight}
      </div>
      <div style={noPad ? {} : { padding: 14 }}>{children}</div>
    </div>
  );
}

function AllocBar({ source }) {
  const ratio = source.maxAlloc > 0 ? source.allocation / source.maxAlloc : 0;
  const barCol = ratio > 0.9 ? C.amber : ratio > 0.7 ? C.cyan : C.green;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, marginBottom: 5 }}>
      <span style={{ width: 85, color: C.text1, fontFamily: sans, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{source.name}</span>
      <div style={{ flex: 1, height: 5, background: C.bg1, borderRadius: 3 }}>
        <div style={{ width: `${Math.min(ratio * 100, 100)}%`, height: "100%", background: barCol, borderRadius: 3, transition: "width 0.6s ease" }} />
      </div>
      <span style={{ width: 70, textAlign: "right", color: C.text3, fontFamily: mono, fontSize: 10 }}>
        {source.allocation}% / {source.maxAlloc}%
      </span>
    </div>
  );
}

function SignalRow({ sig, idx }) {
  const src = srcOf(sig.src);
  const actionColor = { BUY: C.green, BTO: C.green, SELL: C.red, STC: C.red, STO: C.cyan }[sig.action] || C.text1;
  return (
    <div style={{
      display: "grid", gridTemplateColumns: "62px 38px 42px 34px 72px 48px 72px 1fr",
      alignItems: "center", gap: 4, padding: "5px 12px", fontSize: 11,
      background: sig.approved ? (idx % 2 === 0 ? "transparent" : C.bg1 + "40") : C.redMute + "60",
      borderBottom: `1px solid ${C.border0}`, fontFamily: mono, transition: "background 0.15s",
    }}>
      <span style={{ color: C.text3, fontSize: 10 }}>{sig.time}</span>
      <Badge color={src?.color}>{src?.short}</Badge>
      <span style={{ color: actionColor, fontWeight: 700, fontSize: 10 }}>{sig.action}</span>
      <span style={{ color: C.text3, fontSize: 9, background: C.bg3, padding: "0 3px", borderRadius: 2, textAlign: "center" }}>{sig.type}</span>
      <span style={{ color: C.text0, fontWeight: 500 }}>{sig.sym}</span>
      <span style={{ color: C.text2 }}>{sig.qty}</span>
      <span style={{ color: C.text1 }}>{sig.price ? `$${fmt(sig.price, 2)}` : "—"}</span>
      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
        {sig.approved ? (
          <span style={{ color: C.green, fontSize: 10, fontWeight: 600 }}>APPROVED</span>
        ) : (
          <span style={{ color: C.red, fontSize: 10 }}>{sig.reason}</span>
        )}
      </div>
    </div>
  );
}

function PosRow({ pos, idx }) {
  const src = srcOf(pos.src);
  return (
    <div style={{
      display: "grid", gridTemplateColumns: "78px 34px 50px 72px 72px 80px 52px 38px",
      alignItems: "center", gap: 4, padding: "5px 12px", fontSize: 11,
      background: idx % 2 === 0 ? "transparent" : C.bg1 + "40",
      borderBottom: `1px solid ${C.border0}`, fontFamily: mono,
    }}>
      <span style={{ color: C.text0, fontWeight: 600 }}>{pos.sym}</span>
      <span style={{ color: C.text3, fontSize: 9, background: C.bg3, padding: "0 3px", borderRadius: 2, textAlign: "center" }}>{pos.type}</span>
      <span style={{ color: C.text1 }}>{pos.qty}</span>
      <span style={{ color: C.text2 }}>${fmt(pos.avg, 2)}</span>
      <span style={{ color: C.text1 }}>${fmt(pos.cur, 2)}</span>
      <span style={{ color: pnlColor(pos.pnl), fontWeight: 600 }}>{fmtPnl(pos.pnl)}</span>
      <span style={{ color: pnlColor(pos.pct), fontSize: 10 }}>{pos.pct >= 0 ? "+" : ""}{pos.pct}%</span>
      <Badge color={src?.color}>{src?.short}</Badge>
    </div>
  );
}

function GuardianCheck({ check }) {
  const icons = { pass: "✓", warn: "!", fail: "✗" };
  const colors = { pass: C.green, warn: C.amber, fail: C.red };
  const bgColors = { pass: C.greenMute, warn: C.amberMute, fail: C.redMute };
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10, padding: "7px 10px", borderRadius: 4,
      background: bgColors[check.status] + "60", marginBottom: 3,
    }}>
      <span style={{
        width: 20, height: 20, borderRadius: 4, display: "flex", alignItems: "center", justifyContent: "center",
        background: `${colors[check.status]}20`, color: colors[check.status],
        fontSize: 11, fontWeight: 800, fontFamily: mono, flexShrink: 0,
      }}>{icons[check.status]}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 11, color: C.text0, fontFamily: sans, fontWeight: 500 }}>
          <span style={{ color: C.text3, marginRight: 6 }}>#{check.id}</span>{check.name}
        </div>
        <div style={{ fontSize: 10, color: C.text3, fontFamily: mono, marginTop: 1 }}>{check.detail}</div>
      </div>
      <span style={{ fontFamily: mono, fontSize: 11, color: colors[check.status], fontWeight: 600, flexShrink: 0 }}>
        {check.metric}
      </span>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
//  MAIN
// ═══════════════════════════════════════════════════════════════

export default function KATDashboard() {
  const [tab, setTab] = useState("signals");
  const [clock, setClock] = useState(new Date());
  const [isHalted, setIsHalted] = useState(false);
  const [filterSrc, setFilterSrc] = useState("all");

  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const totalPnl = useMemo(() => POSITIONS.reduce((s, p) => s + p.pnl, 0), []);
  const portfolioVal = 96420;
  const approvedCount = SIGNALS.filter(s => s.approved).length;
  const rejectedCount = SIGNALS.filter(s => !s.approved).length;
  const filteredSignals = filterSrc === "all" ? SIGNALS : SIGNALS.filter(s => s.src === filterSrc);
  const filteredPositions = filterSrc === "all" ? POSITIONS : POSITIONS.filter(p => p.src === filterSrc);

  const TABS = [
    { id: "signals", label: "SIGNAL HUB", icon: "⚡" },
    { id: "positions", label: "POSITIONS", icon: "📊" },
    { id: "guardian", label: "GUARDIAN", icon: "🛡" },
    { id: "sources", label: "SOURCES", icon: "🔗" },
  ];

  return (
    <div style={{ minHeight: "100vh", background: C.bg0, color: C.text1, fontFamily: sans }}>
      {/* ════ HEADER ════ */}
      <header style={{
        background: C.bg1, borderBottom: `1px solid ${C.border0}`,
        padding: "0 20px", height: 52, display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{
              width: 30, height: 30, borderRadius: 6, background: C.accentGrad,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 15, fontWeight: 900, color: "#fff", fontFamily: sans,
            }}>K</div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: C.text0, letterSpacing: 1.5, lineHeight: 1.1, fontFamily: sans }}>KATHERINA</div>
              <div style={{ fontSize: 8, color: C.cyan, letterSpacing: 2.5, lineHeight: 1, fontFamily: mono }}>AUTONOMOUS TRADER v2.0</div>
            </div>
          </div>
          <div style={{
            marginLeft: 8, padding: "3px 10px", borderRadius: 4, fontSize: 9, fontWeight: 700,
            fontFamily: mono, letterSpacing: 1,
            background: isHalted ? C.redMute : C.greenMute,
            color: isHalted ? C.red : C.green,
            border: `1px solid ${isHalted ? C.red : C.green}30`,
          }}>
            {isHalted ? "⏹ HALTED" : "● PAPER"}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 9, color: C.text3, fontFamily: sans, letterSpacing: 0.5 }}>PORTFOLIO</div>
            <div style={{ fontSize: 17, fontWeight: 700, color: C.text0, fontFamily: mono }}>${fmt(portfolioVal)}</div>
          </div>
          <div style={{ width: 1, height: 28, background: C.border1 }} />
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 9, color: C.text3, fontFamily: sans, letterSpacing: 0.5 }}>DAY P&L</div>
            <div style={{ fontSize: 17, fontWeight: 700, color: pnlColor(totalPnl), fontFamily: mono }}>{fmtPnl(totalPnl)}</div>
          </div>
          <div style={{ width: 1, height: 28, background: C.border1 }} />
          <div style={{ fontFamily: mono, fontSize: 12, color: C.text3, minWidth: 68, textAlign: "center" }}>
            {clock.toLocaleTimeString("en-US", { hour12: false })}
          </div>
          <button onClick={() => setIsHalted(!isHalted)} style={{
            background: isHalted ? C.green : C.red, color: "#fff", border: "none", borderRadius: 4,
            padding: "6px 14px", fontSize: 9, fontWeight: 700, cursor: "pointer",
            letterSpacing: 1.2, fontFamily: sans, boxShadow: isHalted ? C.greenGlow : C.redGlow,
          }}>{isHalted ? "▶ RESUME" : "⏹ KILL"}</button>
        </div>
      </header>

      {/* ════ TAB BAR ════ */}
      <nav style={{ display: "flex", background: C.bg1, borderBottom: `1px solid ${C.border0}`, padding: "0 20px" }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            background: "none", border: "none", color: tab === t.id ? C.cyan : C.text3,
            padding: "9px 16px", fontSize: 10, fontWeight: 600, cursor: "pointer",
            letterSpacing: 1.2, fontFamily: sans,
            borderBottom: `2px solid ${tab === t.id ? C.cyan : "transparent"}`,
            display: "flex", alignItems: "center", gap: 5,
          }}>
            <span style={{ fontSize: 11 }}>{t.icon}</span> {t.label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <div style={{ display: "flex", alignItems: "center", gap: 4, paddingRight: 4 }}>
          <span style={{ fontSize: 9, color: C.text3, marginRight: 4, fontFamily: sans }}>FILTER:</span>
          {[{ id: "all", label: "ALL", short: "ALL", color: C.text2 }, ...SOURCES.filter(s => s.status !== "standby")].map(s => (
            <button key={s.id} onClick={() => setFilterSrc(s.id)} style={{
              background: filterSrc === s.id ? (s.color || C.text2) + "25" : "transparent",
              border: `1px solid ${filterSrc === s.id ? (s.color || C.text2) + "50" : "transparent"}`,
              color: filterSrc === s.id ? (s.color || C.text2) : C.text3,
              padding: "2px 8px", borderRadius: 3, fontSize: 9, fontWeight: 600, cursor: "pointer", fontFamily: mono,
            }}>{s.short}</button>
          ))}
        </div>
      </nav>

      {/* ════ CONTENT ════ */}
      <main style={{ padding: 16 }}>
        <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
          <Stat label="Portfolio" value={`$${fmt(portfolioVal)}`} sub={`${POSITIONS.length} positions`} small />
          <Stat label="Day P&L" value={fmtPnl(totalPnl)} sub="+1.41%" color={pnlColor(totalPnl)} small />
          <Stat label="Signals" value={SIGNALS.length.toString()} sub={`${approvedCount}↑ ${rejectedCount}↓`} color={C.cyan} small />
          <Stat label="Cash" value="25.1%" sub="$24,220" small />
          <Stat label="Win Rate" value="69.1%" sub="30d: 142/206" color={C.green} small />
          <Stat label="Drawdown" value="-2.1%" sub="Max: -4.8%" color={C.amber} small />
        </div>

        {/* SIGNAL HUB */}
        {tab === "signals" && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 280px", gap: 14 }}>
            <Panel title="Signal Feed"
              badge={<><StatusDot status="active" /><span style={{ fontSize: 9, color: C.text3, fontFamily: mono }}>LIVE</span></>}
              headerRight={<span style={{ fontSize: 10, color: C.text3, fontFamily: mono }}>{approvedCount} approved · {rejectedCount} rejected</span>}
              noPad>
              <div style={{
                display: "grid", gridTemplateColumns: "62px 38px 42px 34px 72px 48px 72px 1fr",
                gap: 4, padding: "5px 12px", fontSize: 9, color: C.text3, fontFamily: mono,
                textTransform: "uppercase", letterSpacing: 0.8, borderBottom: `1px solid ${C.border0}`,
              }}>
                <span>TIME</span><span>SRC</span><span>ACT</span><span>TYPE</span>
                <span>SYMBOL</span><span>QTY</span><span>PRICE</span><span>STATUS</span>
              </div>
              <div style={{ maxHeight: 440, overflowY: "auto" }}>
                {filteredSignals.map((s, i) => <SignalRow key={s.id} sig={s} idx={i} />)}
              </div>
            </Panel>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <Panel title="Source Health">
                {SOURCES.map(s => (
                  <div key={s.id} style={{
                    display: "flex", alignItems: "center", gap: 8, padding: "6px 0",
                    borderBottom: s.id !== "int" ? `1px solid ${C.border0}30` : "none",
                  }}>
                    <StatusDot status={s.status} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 11, color: C.text0, fontFamily: sans, fontWeight: 500 }}>{s.name}</div>
                      <div style={{ fontSize: 9, color: C.text3, fontFamily: mono }}>{s.signalsDay} sig · {s.winRate}% win · {s.lastSignal}</div>
                    </div>
                    <span style={{ color: pnlColor(s.pnlMtd), fontFamily: mono, fontSize: 11, fontWeight: 600 }}>
                      {s.pnlMtd > 0 ? `+$${fmt(s.pnlMtd)}` : "—"}
                    </span>
                  </div>
                ))}
              </Panel>
              <Panel title="Source Allocation">
                {SOURCES.filter(s => s.allocation > 0).map(s => <AllocBar key={s.id} source={s} />)}
                <div style={{ marginTop: 8, paddingTop: 8, borderTop: `1px solid ${C.border0}` }}>
                  <AllocBar source={{ name: "Cash Reserve", allocation: 25, maxAlloc: 20, color: C.green }} />
                </div>
              </Panel>
            </div>
          </div>
        )}

        {/* POSITIONS */}
        {tab === "positions" && (
          <Panel title={`Open Positions (${filteredPositions.length})`}
            headerRight={<span style={{ color: pnlColor(totalPnl), fontFamily: mono, fontSize: 12, fontWeight: 700 }}>Unrealized: {fmtPnl(totalPnl)}</span>}
            noPad>
            <div style={{
              display: "grid", gridTemplateColumns: "78px 34px 50px 72px 72px 80px 52px 38px",
              gap: 4, padding: "5px 12px", fontSize: 9, color: C.text3, fontFamily: mono,
              textTransform: "uppercase", letterSpacing: 0.8, borderBottom: `1px solid ${C.border0}`,
            }}>
              <span>SYMBOL</span><span>TYPE</span><span>QTY</span><span>AVG</span>
              <span>LAST</span><span>P&L</span><span>%</span><span>SRC</span>
            </div>
            {filteredPositions.map((p, i) => <PosRow key={i} pos={p} idx={i} />)}
            <div style={{
              padding: "10px 12px", borderTop: `1px solid ${C.border1}`,
              display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12,
            }}>
              {[
                { label: "Stocks", val: `$${fmt(filteredPositions.filter(p=>p.type==="STK").reduce((s,p)=>s+p.cur*p.qty,0))}`, pct: "61%" },
                { label: "Futures", val: `$${fmt(filteredPositions.filter(p=>p.type==="FUT").reduce((s,p)=>s+p.cur*p.qty,0))}`, pct: "31%" },
                { label: "Options", val: `$${fmt(filteredPositions.filter(p=>p.type==="OPT").reduce((s,p)=>s+p.cur*p.qty*100,0))}`, pct: "8%" },
              ].map((a, i) => (
                <div key={i} style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 9, color: C.text3, fontFamily: sans }}>{a.label}</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: C.text0, fontFamily: mono }}>{a.val}</div>
                  <div style={{ fontSize: 10, color: C.text2, fontFamily: mono }}>{a.pct}</div>
                </div>
              ))}
            </div>
          </Panel>
        )}

        {/* GUARDIAN */}
        {tab === "guardian" && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            <Panel title="10 Risk Checks" badge={<Badge color={C.green} bg={C.greenMute}>ALL PASSING</Badge>}>
              {GUARDIAN_CHECKS.map(c => <GuardianCheck key={c.id} check={c} />)}
            </Panel>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <Panel title="Circuit Breakers">
                {[
                  { label: "Daily Loss >3%", val: "Current: +1.41%" },
                  { label: "Weekly Loss >5%", val: "Current: +2.83%" },
                  { label: "Source Loss >2%/day", val: "Max: C2 +1.1%" },
                  { label: "Signal Flood >20/src", val: "Max: Holly 6" },
                  { label: "IBKR Connection", val: "Paper:7496 ✓" },
                  { label: "Data Feed TTL", val: "5s refresh" },
                ].map((cb, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 0", borderBottom: i < 5 ? `1px solid ${C.border0}30` : "none" }}>
                    <StatusDot status="active" size={5} />
                    <span style={{ flex: 1, fontSize: 11, color: C.text1, fontFamily: sans }}>{cb.label}</span>
                    <span style={{ fontSize: 10, color: C.text3, fontFamily: mono }}>{cb.val}</span>
                  </div>
                ))}
              </Panel>
              <Panel title="Risk Limits">
                {[
                  ["Max per trade", "2.0%"], ["Portfolio heat", "10.0%"], ["Daily loss halt", "3.0%"],
                  ["Weekly loss halt", "5.0%"], ["Concentration", "15.0%"], ["Options cap", "30.0%"],
                  ["Futures margin", "25.0%"], ["Cash reserve min", "20.0%"], ["Max positions", "15"],
                  ["Signals/src/day", "20"],
                ].map(([k, v], i) => (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontSize: 11 }}>
                    <span style={{ color: C.text2, fontFamily: sans }}>{k}</span>
                    <span style={{ color: C.text0, fontFamily: mono, fontWeight: 500 }}>{v}</span>
                  </div>
                ))}
              </Panel>
            </div>
          </div>
        )}

        {/* SOURCES */}
        {tab === "sources" && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 14 }}>
            {SOURCES.map(s => (
              <div key={s.id} style={{
                background: C.bg2, border: `1px solid ${C.border0}`, borderRadius: 6,
                borderTop: `3px solid ${s.color}`, padding: 16,
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <StatusDot status={s.status} size={7} />
                    <span style={{ fontSize: 14, fontWeight: 700, color: C.text0, fontFamily: sans }}>{s.name}</span>
                  </div>
                  <Badge color={s.status === "standby" ? C.text3 : C.green}>{s.status.toUpperCase()}</Badge>
                </div>
                <div style={{ fontSize: 10, color: C.text3, fontFamily: mono, marginBottom: 12 }}>
                  {s.type} · latency {s.latencyMs}ms · {s.uptime}% uptime
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  {[
                    { label: "Win Rate", val: `${s.winRate}%`, color: s.winRate > 60 ? C.green : C.text1 },
                    { label: "MTD P&L", val: s.pnlMtd > 0 ? `+$${fmt(s.pnlMtd)}` : "—", color: pnlColor(s.pnlMtd) },
                    { label: "Signals/Day", val: s.signalsDay.toString(), color: C.text0 },
                    { label: "Allocation", val: `${s.allocation}%`, color: C.cyan },
                  ].map((m, i) => (
                    <div key={i}>
                      <div style={{ fontSize: 9, color: C.text3, fontFamily: sans, letterSpacing: 0.5 }}>{m.label}</div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: m.color, fontFamily: mono }}>{m.val}</div>
                    </div>
                  ))}
                </div>
                <div style={{ marginTop: 12, paddingTop: 10, borderTop: `1px solid ${C.border0}` }}>
                  <AllocBar source={s} />
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Outfit:wght@300;400;500;600;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: ${C.bg0}; }
        ::-webkit-scrollbar { width: 3px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: ${C.border1}; border-radius: 3px; }
        button { transition: all 0.15s ease; }
        button:hover { filter: brightness(1.15); }
      `}</style>
    </div>
  );
}
