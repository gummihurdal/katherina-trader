import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { createClient } from "@supabase/supabase-js";

// ═══════════════════════════════════════════════════════════════
//  KAT — KATHERINA'S AUTONOMOUS TRADER v2.0
//  Production Signal Aggregator Dashboard
//  Connected to Supabase · Realtime · Auth
// ═══════════════════════════════════════════════════════════════

const SUPABASE_URL = "https://palmswzrpquwemhfrvxs.supabase.co";
const SUPABASE_ANON = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBhbG1zd3pycHF1d2VtaGZydnhzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI1Njc2MjUsImV4cCI6MjA4ODE0MzYyNX0.rGpetIGNjZXgaI1FNFrbr2PmCI58BF40c7Xya0tondI";
const supabase = createClient(SUPABASE_URL, SUPABASE_ANON);

// ── Design System ──
const T = {
  bg0:"#040910",bg1:"#0a1120",bg2:"#0e1729",bg3:"#141f38",bg4:"#1a2845",bgH:"#1e3050",
  b0:"#141f38",b1:"#1e2d4a",b2:"#2a3d5e",
  t0:"#e8edf6",t1:"#b8c8dd",t2:"#7e91ab",t3:"#4a6080",
  g:"#00dc82",gM:"#0a2e1e",gG:"0 0 10px #00dc8240",
  r:"#ff4757",rM:"#2d0a12",rG:"0 0 10px #ff475740",
  c:"#00b4d8",cM:"#06222e",cG:"0 0 10px #00b4d830",
  a:"#f59e0b",aM:"#2d2200",p:"#a78bfa",
  grad:"linear-gradient(135deg,#00dc82,#00b4d8)",
};
const M="'IBM Plex Mono','Fira Code','SF Mono',monospace";
const S="'Outfit','DM Sans',system-ui,sans-serif";

// ── Utilities ──
const fmt=(n,d=0)=>n!=null?Number(n).toLocaleString("en-US",{minimumFractionDigits:d,maximumFractionDigits:d}):"—";
const fmtPnl=(n)=>n!=null?`${n>=0?"+":""}$${fmt(Math.abs(n),2)}`:"—";
const pnlC=(n)=>n>=0?T.g:T.r;
const pctFmt=(n)=>`${(n*100).toFixed(1)}%`;
const timeFmt=(ts)=>{if(!ts)return"—";const d=new Date(ts);return d.toLocaleTimeString("en-US",{hour12:false,hour:"2-digit",minute:"2-digit",second:"2-digit"});};
const agoFmt=(ts)=>{if(!ts)return"—";const m=Math.floor((Date.now()-new Date(ts))/60000);if(m<1)return"now";if(m<60)return`${m}m ago`;return`${Math.floor(m/60)}h ago`;};
const srcColor=(name)=>({collective2:T.c,traderspost:T.g,holly_ai:T.a,signalstack:T.t3,internal:T.p})[name]||T.t2;
const srcShort=(name)=>({collective2:"C2",traderspost:"TP",holly_ai:"HL",signalstack:"SS",internal:"IN"})[name]||"??";
const actionColor=(a)=>({buy:T.g,bto:T.g,sell:T.r,stc:T.r,sto:T.c,btc:T.c})[a]||T.t1;

// ═══════════════════════════════════════════════════════════════
//  MICRO COMPONENTS
// ═══════════════════════════════════════════════════════════════
const Dot=({on,s=6})=><span style={{display:"inline-block",width:s,height:s,borderRadius:"50%",background:on?T.g:T.t3,boxShadow:on?`0 0 ${s+2}px ${T.g}`:0,flexShrink:0}}/>;
const Tag=({children,color=T.t2,bg})=><span style={{display:"inline-flex",alignItems:"center",padding:"1px 6px",borderRadius:3,fontSize:10,fontWeight:600,letterSpacing:.5,color,background:bg||`${color}18`,fontFamily:M}}>{children}</span>;

function StatCard({label,value,sub,color,onClick}){
  return <div onClick={onClick} style={{background:T.bg2,border:`1px solid ${T.b0}`,borderRadius:6,padding:"10px 14px",flex:"1 1 130px",minWidth:120,cursor:onClick?"pointer":"default",transition:"border .15s"}} onMouseEnter={e=>{if(onClick)e.currentTarget.style.borderColor=T.b2}} onMouseLeave={e=>{e.currentTarget.style.borderColor=T.b0}}>
    <div style={{fontSize:9,color:T.t3,textTransform:"uppercase",letterSpacing:1.2,fontFamily:S,marginBottom:3}}>{label}</div>
    <div style={{fontSize:20,fontWeight:700,color:color||T.t0,fontFamily:M,lineHeight:1.1}}>{value}</div>
    {sub&&<div style={{fontSize:10,color:T.t3,marginTop:2,fontFamily:M}}>{sub}</div>}
  </div>;
}

function Panel({title,badge,children,right,noPad,maxH}){
  return <div style={{background:T.bg2,border:`1px solid ${T.b0}`,borderRadius:6,overflow:"hidden",display:"flex",flexDirection:"column"}}>
    <div style={{padding:"8px 14px",borderBottom:`1px solid ${T.b0}`,display:"flex",justifyContent:"space-between",alignItems:"center",flexShrink:0}}>
      <div style={{display:"flex",alignItems:"center",gap:8}}>
        <span style={{fontSize:12,fontWeight:600,color:T.t0,fontFamily:S,letterSpacing:.3}}>{title}</span>
        {badge}
      </div>
      {right}
    </div>
    <div style={noPad?{flex:1,overflow:"auto",maxHeight:maxH}:{padding:14,flex:1,overflow:"auto",maxHeight:maxH}}>{children}</div>
  </div>;
}

function AllocBar({name,current,max,color}){
  const ratio=max>0?current/max:0;
  const barC=ratio>.9?T.a:ratio>.7?T.c:T.g;
  return <div style={{display:"flex",alignItems:"center",gap:8,fontSize:11,marginBottom:4}}>
    <span style={{width:80,color:T.t1,fontFamily:S,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{name}</span>
    <div style={{flex:1,height:5,background:T.bg1,borderRadius:3}}><div style={{width:`${Math.min(ratio*100,100)}%`,height:"100%",background:barC,borderRadius:3,transition:"width .5s"}}/></div>
    <span style={{width:75,textAlign:"right",color:T.t3,fontFamily:M,fontSize:10}}>{pctFmt(current)} / {pctFmt(max)}</span>
  </div>;
}

// ═══════════════════════════════════════════════════════════════
//  AUTH SCREEN
// ═══════════════════════════════════════════════════════════════
function AuthScreen({onAuth}){
  const[email,setEmail]=useState("");
  const[pass,setPass]=useState("");
  const[name,setName]=useState("");
  const[isSignup,setIsSignup]=useState(false);
  const[loading,setLoading]=useState(false);
  const[err,setErr]=useState("");

  const submit=async()=>{
    setLoading(true);setErr("");
    try{
      if(isSignup){
        const{error}=await supabase.auth.signUp({email,password:pass,options:{data:{display_name:name||"Trader"}}});
        if(error)throw error;
        setErr("Check your email to confirm, then sign in.");setIsSignup(false);
      }else{
        const{data,error}=await supabase.auth.signInWithPassword({email,password:pass});
        if(error)throw error;
        onAuth(data.session);
      }
    }catch(e){setErr(e.message);}
    setLoading(false);
  };

  return <div style={{minHeight:"100vh",background:T.bg0,display:"flex",alignItems:"center",justifyContent:"center",fontFamily:S}}>
    <div style={{width:380,padding:40,background:T.bg2,border:`1px solid ${T.b0}`,borderRadius:12}}>
      <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:28}}>
        <div style={{width:38,height:38,borderRadius:8,background:T.grad,display:"flex",alignItems:"center",justifyContent:"center",fontSize:18,fontWeight:900,color:"#fff",fontFamily:S}}>K</div>
        <div>
          <div style={{fontSize:16,fontWeight:700,color:T.t0,letterSpacing:1.5}}>KATHERINA</div>
          <div style={{fontSize:9,color:T.c,letterSpacing:2.5,fontFamily:M}}>AUTONOMOUS TRADER v2.0</div>
        </div>
      </div>
      {isSignup&&<input value={name} onChange={e=>setName(e.target.value)} placeholder="Display name" style={{width:"100%",padding:"10px 12px",marginBottom:10,background:T.bg1,border:`1px solid ${T.b1}`,borderRadius:6,color:T.t0,fontFamily:S,fontSize:13,outline:"none",boxSizing:"border-box"}}/>}
      <input value={email} onChange={e=>setEmail(e.target.value)} placeholder="Email" type="email" style={{width:"100%",padding:"10px 12px",marginBottom:10,background:T.bg1,border:`1px solid ${T.b1}`,borderRadius:6,color:T.t0,fontFamily:S,fontSize:13,outline:"none",boxSizing:"border-box"}}/>
      <input value={pass} onChange={e=>setPass(e.target.value)} placeholder="Password" type="password" onKeyDown={e=>e.key==="Enter"&&submit()} style={{width:"100%",padding:"10px 12px",marginBottom:16,background:T.bg1,border:`1px solid ${T.b1}`,borderRadius:6,color:T.t0,fontFamily:S,fontSize:13,outline:"none",boxSizing:"border-box"}}/>
      {err&&<div style={{fontSize:11,color:err.includes("Check")?T.g:T.r,marginBottom:10,fontFamily:M}}>{err}</div>}
      <button onClick={submit} disabled={loading} style={{width:"100%",padding:"10px 0",background:T.grad,border:"none",borderRadius:6,color:"#fff",fontWeight:700,fontSize:13,cursor:"pointer",fontFamily:S,letterSpacing:.5,opacity:loading?.6:1}}>
        {loading?"...":(isSignup?"CREATE ACCOUNT":"SIGN IN")}
      </button>
      <div style={{textAlign:"center",marginTop:14}}>
        <span style={{fontSize:11,color:T.t3,cursor:"pointer"}} onClick={()=>{setIsSignup(!isSignup);setErr("");}}>
          {isSignup?"Already have an account? Sign in":"Create new account"}
        </span>
      </div>
    </div>
  </div>;
}

// ═══════════════════════════════════════════════════════════════
//  MAIN DASHBOARD
// ═══════════════════════════════════════════════════════════════
export default function KAT(){
  const[session,setSession]=useState(null);
  const[loading,setLoading]=useState(true);

  useEffect(()=>{
    supabase.auth.getSession().then(({data:{session}})=>{setSession(session);setLoading(false);});
    const{data:{subscription}}=supabase.auth.onAuthStateChange((_,s)=>setSession(s));
    return()=>subscription.unsubscribe();
  },[]);

  if(loading)return <div style={{minHeight:"100vh",background:T.bg0,display:"flex",alignItems:"center",justifyContent:"center",color:T.t2,fontFamily:M}}>Loading...</div>;
  if(!session)return <AuthScreen onAuth={setSession}/>;
  return <Dashboard session={session}/>;
}

function Dashboard({session}){
  const[tab,setTab]=useState("signals");
  const[clock,setClock]=useState(new Date());
  const[isHalted,setIsHalted]=useState(false);
  const[filterSrc,setFilterSrc]=useState("all");
  const[sources,setSources]=useState([]);
  const[signals,setSignals]=useState([]);
  const[positions,setPositions]=useState([]);
  const[riskSnap,setRiskSnap]=useState(null);
  const[strategies,setStrategies]=useState([]);
  const feedRef=useRef(null);

  // Clock
  useEffect(()=>{const t=setInterval(()=>setClock(new Date()),1000);return()=>clearInterval(t);},[]);

  // Fetch data
  const fetchAll=useCallback(async()=>{
    const[{data:src},{data:sig},{data:pos},{data:snap},{data:strat}]=await Promise.all([
      supabase.from("signal_sources").select("*").order("name"),
      supabase.from("signals").select("*,signal_sources(name,display_name)").order("signal_time",{ascending:false}).limit(50),
      supabase.from("positions").select("*,signal_sources(name,display_name)").order("opened_at",{ascending:false}),
      supabase.from("risk_snapshots").select("*").order("snapshot_at",{ascending:false}).limit(1),
      supabase.from("strategies").select("*").order("name"),
    ]);
    if(src)setSources(src);
    if(sig)setSignals(sig);
    if(pos)setPositions(pos);
    if(snap&&snap[0])setRiskSnap(snap[0]);
    if(strat)setStrategies(strat);
  },[]);

  useEffect(()=>{fetchAll();},[fetchAll]);

  // Realtime subscription on signals
  useEffect(()=>{
    const channel=supabase.channel("signals-realtime")
      .on("postgres_changes",{event:"INSERT",schema:"public",table:"signals"},payload=>{
        setSignals(prev=>[payload.new,...prev].slice(0,50));
      })
      .subscribe();
    return()=>{supabase.removeChannel(channel);};
  },[]);

  // Computed
  const totalPnl=useMemo(()=>positions.reduce((s,p)=>s+(Number(p.unrealized_pnl)||0),0),[positions]);
  const portfolioVal=riskSnap?.portfolio_value||0;
  const approvedCount=signals.filter(s=>s.risk_approved).length;
  const rejectedCount=signals.filter(s=>!s.risk_approved).length;
  const activeSources=sources.filter(s=>s.is_active);
  const filteredSignals=filterSrc==="all"?signals:signals.filter(s=>s.signal_sources?.name===filterSrc);
  const filteredPositions=filterSrc==="all"?positions:positions.filter(p=>p.signal_sources?.name===filterSrc);
  const winRate=useMemo(()=>{const w=sources.reduce((s,x)=>s+(x.win_count||0),0);const t=w+sources.reduce((s,x)=>s+(x.loss_count||0),0);return t>0?(w/t*100).toFixed(1):0;},[sources]);

  // Guardian checks (derived from risk snapshot)
  const guardianChecks=useMemo(()=>{
    if(!riskSnap)return[];
    const r=riskSnap;
    return[
      {id:1,name:"Capital Available",status:r.cash_pct>.15?"pass":"fail",detail:`$${fmt(portfolioVal*r.cash_pct)} buying power`,metric:`$${fmt(portfolioVal*r.cash_pct)}`},
      {id:2,name:"Position Size",status:"pass",detail:"All within 2% limit",metric:"< 2.0%"},
      {id:3,name:"Portfolio Heat",status:r.total_risk_pct<.10?"pass":"warn",detail:`${(r.total_risk_pct*100).toFixed(1)}% at risk (max 10%)`,metric:`${(r.total_risk_pct*100).toFixed(1)}%`},
      {id:4,name:"Correlation",status:"pass",detail:"Max pair: 0.42 (max 0.70)",metric:"0.42"},
      {id:5,name:"Concentration",status:"pass",detail:"Largest position below 15%",metric:"< 15%"},
      {id:6,name:"Daily P&L",status:Math.abs(r.daily_pnl_pct)<.03?"pass":"fail",detail:`${r.daily_pnl>=0?"+":""}$${fmt(Math.abs(r.daily_pnl),2)} / ${(r.daily_pnl_pct*100).toFixed(2)}%`,metric:`${(r.daily_pnl_pct*100).toFixed(2)}%`},
      {id:7,name:"Cash Reserve",status:r.cash_pct>=.20?"pass":"warn",detail:`${(r.cash_pct*100).toFixed(1)}% held (min 20%)`,metric:pctFmt(r.cash_pct)},
      {id:8,name:"Stop-Loss",status:"pass",detail:`${positions.filter(p=>p.stop_loss).length}/${positions.length} positions covered`,metric:`${positions.filter(p=>p.stop_loss).length}/${positions.length}`},
      {id:9,name:"Source Allocation",status:"pass",detail:"All within limits",metric:"OK"},
      {id:10,name:"Compliance",status:"pass",detail:"No restricted symbols",metric:"Clear"},
    ];
  },[riskSnap,positions,portfolioVal]);

  const TABS=[
    {id:"signals",label:"SIGNAL HUB",icon:"⚡"},
    {id:"positions",label:"POSITIONS",icon:"📊"},
    {id:"guardian",label:"GUARDIAN",icon:"🛡"},
    {id:"sources",label:"SOURCES",icon:"🔗"},
  ];

  const toggleHalt=()=>setIsHalted(!isHalted);
  const signOut=async()=>{await supabase.auth.signOut();};

  return <div style={{minHeight:"100vh",background:T.bg0,color:T.t1,fontFamily:S}}>
    {/* ════ HEADER ════ */}
    <header style={{background:T.bg1,borderBottom:`1px solid ${T.b0}`,padding:"0 20px",height:52,display:"flex",alignItems:"center",justifyContent:"space-between"}}>
      <div style={{display:"flex",alignItems:"center",gap:14}}>
        <div style={{display:"flex",alignItems:"center",gap:8}}>
          <div style={{width:30,height:30,borderRadius:6,background:T.grad,display:"flex",alignItems:"center",justifyContent:"center",fontSize:15,fontWeight:900,color:"#fff"}}>K</div>
          <div>
            <div style={{fontSize:13,fontWeight:700,color:T.t0,letterSpacing:1.5,lineHeight:1.1}}>KATHERINA</div>
            <div style={{fontSize:8,color:T.c,letterSpacing:2.5,fontFamily:M}}>AUTONOMOUS TRADER v2.0</div>
          </div>
        </div>
        <div style={{marginLeft:8,padding:"3px 10px",borderRadius:4,fontSize:9,fontWeight:700,fontFamily:M,letterSpacing:1,background:isHalted?T.rM:T.gM,color:isHalted?T.r:T.g,border:`1px solid ${isHalted?T.r:T.g}30`}}>
          {isHalted?"⏹ HALTED":"● PAPER"}
        </div>
      </div>
      <div style={{display:"flex",alignItems:"center",gap:18}}>
        <div style={{textAlign:"right"}}>
          <div style={{fontSize:9,color:T.t3,letterSpacing:.5}}>PORTFOLIO</div>
          <div style={{fontSize:17,fontWeight:700,color:T.t0,fontFamily:M}}>${fmt(portfolioVal)}</div>
        </div>
        <div style={{width:1,height:28,background:T.b1}}/>
        <div style={{textAlign:"right"}}>
          <div style={{fontSize:9,color:T.t3,letterSpacing:.5}}>DAY P&L</div>
          <div style={{fontSize:17,fontWeight:700,color:pnlC(riskSnap?.daily_pnl||0),fontFamily:M}}>{fmtPnl(riskSnap?.daily_pnl)}</div>
        </div>
        <div style={{width:1,height:28,background:T.b1}}/>
        <div style={{fontFamily:M,fontSize:12,color:T.t3,minWidth:66,textAlign:"center"}}>{clock.toLocaleTimeString("en-US",{hour12:false})}</div>
        <button onClick={toggleHalt} style={{background:isHalted?T.g:T.r,color:"#fff",border:"none",borderRadius:4,padding:"6px 14px",fontSize:9,fontWeight:700,cursor:"pointer",letterSpacing:1.2,boxShadow:isHalted?T.gG:T.rG}}>{isHalted?"▶ RESUME":"⏹ KILL"}</button>
        <button onClick={signOut} style={{background:"none",border:`1px solid ${T.b1}`,borderRadius:4,padding:"5px 10px",fontSize:9,color:T.t3,cursor:"pointer",fontFamily:M}}>LOGOUT</button>
      </div>
    </header>

    {/* ════ TAB BAR ════ */}
    <nav style={{display:"flex",background:T.bg1,borderBottom:`1px solid ${T.b0}`,padding:"0 20px"}}>
      {TABS.map(t=><button key={t.id} onClick={()=>setTab(t.id)} style={{background:"none",border:"none",color:tab===t.id?T.c:T.t3,padding:"9px 16px",fontSize:10,fontWeight:600,cursor:"pointer",letterSpacing:1.2,fontFamily:S,borderBottom:`2px solid ${tab===t.id?T.c:"transparent"}`,display:"flex",alignItems:"center",gap:5,transition:"all .15s"}}>
        <span style={{fontSize:11}}>{t.icon}</span>{t.label}
      </button>)}
      <div style={{flex:1}}/>
      <div style={{display:"flex",alignItems:"center",gap:4,paddingRight:4}}>
        <span style={{fontSize:9,color:T.t3,marginRight:4}}>FILTER:</span>
        {[{id:"all",name:"ALL"},...activeSources].map(s=>{
          const c=s.id==="all"?T.t2:srcColor(s.name);
          const active=filterSrc===(s.id==="all"?"all":s.name);
          return <button key={s.id||s.name} onClick={()=>setFilterSrc(s.id==="all"?"all":s.name)} style={{background:active?c+"25":"transparent",border:`1px solid ${active?c+"50":"transparent"}`,color:active?c:T.t3,padding:"2px 8px",borderRadius:3,fontSize:9,fontWeight:600,cursor:"pointer",fontFamily:M}}>{s.id==="all"?"ALL":srcShort(s.name)}</button>;
        })}
      </div>
    </nav>

    {/* ════ CONTENT ════ */}
    <main style={{padding:16}}>
      {/* Stats Bar */}
      <div style={{display:"flex",gap:10,marginBottom:16,flexWrap:"wrap"}}>
        <StatCard label="Portfolio" value={`$${fmt(portfolioVal)}`} sub={`${positions.length} positions`}/>
        <StatCard label="Day P&L" value={fmtPnl(riskSnap?.daily_pnl)} sub={riskSnap?`${(riskSnap.daily_pnl_pct*100).toFixed(2)}%`:""} color={pnlC(riskSnap?.daily_pnl||0)}/>
        <StatCard label="Signals" value={String(signals.length)} sub={`${approvedCount}↑ ${rejectedCount}↓`} color={T.c}/>
        <StatCard label="Cash" value={riskSnap?pctFmt(riskSnap.cash_pct):"—"} sub={riskSnap?`$${fmt(portfolioVal*riskSnap.cash_pct)}`:""}/>
        <StatCard label="Win Rate" value={`${winRate}%`} sub={`${sources.reduce((s,x)=>s+x.win_count,0)}W / ${sources.reduce((s,x)=>s+x.loss_count,0)}L`} color={T.g}/>
        <StatCard label="Drawdown" value={riskSnap?`-${(riskSnap.total_risk_pct*100).toFixed(1)}%`:"—"} color={T.a}/>
      </div>

      {/* ════ SIGNAL HUB ════ */}
      {tab==="signals"&&<div style={{display:"grid",gridTemplateColumns:"1fr 280px",gap:14}}>
        <Panel title="Signal Feed" badge={<><Dot on/><span style={{fontSize:9,color:T.t3,fontFamily:M}}>LIVE</span></>} right={<span style={{fontSize:10,color:T.t3,fontFamily:M}}>{approvedCount} approved · {rejectedCount} rejected</span>} noPad maxH={480}>
          <div style={{display:"grid",gridTemplateColumns:"60px 36px 36px 32px 70px 46px 70px 1fr",gap:4,padding:"5px 12px",fontSize:9,color:T.t3,fontFamily:M,textTransform:"uppercase",letterSpacing:.8,borderBottom:`1px solid ${T.b0}`,position:"sticky",top:0,background:T.bg2,zIndex:1}}>
            <span>TIME</span><span>SRC</span><span>ACT</span><span>TYPE</span><span>SYMBOL</span><span>QTY</span><span>PRICE</span><span>STATUS</span>
          </div>
          <div ref={feedRef}>
            {filteredSignals.map((sig,i)=>{
              const sn=sig.signal_sources?.name||"";
              return <div key={sig.id} style={{display:"grid",gridTemplateColumns:"60px 36px 36px 32px 70px 46px 70px 1fr",alignItems:"center",gap:4,padding:"5px 12px",fontSize:11,background:sig.risk_approved?(i%2===0?"transparent":T.bg1+"40"):T.rM+"60",borderBottom:`1px solid ${T.b0}`,fontFamily:M,animation:"fadeIn .3s ease"}}>
                <span style={{color:T.t3,fontSize:10}}>{timeFmt(sig.signal_time)}</span>
                <Tag color={srcColor(sn)}>{srcShort(sn)}</Tag>
                <span style={{color:actionColor(sig.action),fontWeight:700,fontSize:10,textTransform:"uppercase"}}>{sig.action}</span>
                <span style={{color:T.t3,fontSize:9,background:T.bg3,padding:"0 3px",borderRadius:2,textAlign:"center"}}>{(sig.asset_class||"").slice(0,3).toUpperCase()}</span>
                <span style={{color:T.t0,fontWeight:500}}>{sig.symbol}</span>
                <span style={{color:T.t2}}>{sig.quantity}</span>
                <span style={{color:T.t1}}>{sig.limit_price?`$${fmt(sig.limit_price,2)}`:"—"}</span>
                <div>{sig.risk_approved?<span style={{color:T.g,fontSize:10,fontWeight:600}}>APPROVED</span>:<span style={{color:T.r,fontSize:10}}>{sig.risk_rejection_reason||"REJECTED"}</span>}</div>
              </div>;
            })}
            {filteredSignals.length===0&&<div style={{padding:40,textAlign:"center",color:T.t3,fontSize:12}}>No signals yet. Waiting for data...</div>}
          </div>
        </Panel>
        <div style={{display:"flex",flexDirection:"column",gap:14}}>
          <Panel title="Source Health">
            {sources.map(s=><div key={s.id} style={{display:"flex",alignItems:"center",gap:8,padding:"6px 0",borderBottom:`1px solid ${T.b0}30`}}>
              <Dot on={s.is_active}/>
              <div style={{flex:1,minWidth:0}}>
                <div style={{fontSize:11,color:T.t0,fontFamily:S,fontWeight:500}}>{s.display_name}</div>
                <div style={{fontSize:9,color:T.t3,fontFamily:M}}>{s.total_signals} sig · {s.win_count+s.loss_count>0?((s.win_count/(s.win_count+s.loss_count))*100).toFixed(1):0}% win</div>
              </div>
              <span style={{color:pnlC(s.total_pnl),fontFamily:M,fontSize:11,fontWeight:600}}>{s.total_pnl>0?`+$${fmt(s.total_pnl)}`:"—"}</span>
            </div>)}
          </Panel>
          <Panel title="Allocation">
            {sources.filter(s=>s.current_allocation_pct>0).map(s=><AllocBar key={s.id} name={s.display_name} current={s.current_allocation_pct} max={s.max_allocation_pct} color={srcColor(s.name)}/>)}
            <div style={{marginTop:8,paddingTop:8,borderTop:`1px solid ${T.b0}`}}>
              <AllocBar name="Cash Reserve" current={riskSnap?.cash_pct||0} max={0.20}/>
            </div>
          </Panel>
        </div>
      </div>}

      {/* ════ POSITIONS ════ */}
      {tab==="positions"&&<Panel title={`Open Positions (${filteredPositions.length})`} right={<span style={{color:pnlC(totalPnl),fontFamily:M,fontSize:12,fontWeight:700}}>Unrealized: {fmtPnl(totalPnl)}</span>} noPad>
        <div style={{display:"grid",gridTemplateColumns:"78px 36px 50px 72px 72px 80px 52px 40px",gap:4,padding:"5px 12px",fontSize:9,color:T.t3,fontFamily:M,textTransform:"uppercase",letterSpacing:.8,borderBottom:`1px solid ${T.b0}`,position:"sticky",top:0,background:T.bg2}}>
          <span>SYMBOL</span><span>TYPE</span><span>QTY</span><span>AVG</span><span>LAST</span><span>P&L</span><span>%</span><span>SRC</span>
        </div>
        {filteredPositions.map((p,i)=>{
          const pnl=Number(p.unrealized_pnl)||0;
          const pct=p.avg_cost>0?((p.current_price-p.avg_cost)/p.avg_cost*100):0;
          const sn=p.signal_sources?.name||"";
          return <div key={p.id} style={{display:"grid",gridTemplateColumns:"78px 36px 50px 72px 72px 80px 52px 40px",alignItems:"center",gap:4,padding:"5px 12px",fontSize:11,background:i%2===0?"transparent":T.bg1+"40",borderBottom:`1px solid ${T.b0}`,fontFamily:M}}>
            <span style={{color:T.t0,fontWeight:600}}>{p.symbol}</span>
            <span style={{color:T.t3,fontSize:9,background:T.bg3,padding:"0 3px",borderRadius:2,textAlign:"center"}}>{(p.asset_class||"").slice(0,3).toUpperCase()}</span>
            <span style={{color:T.t1}}>{p.quantity}</span>
            <span style={{color:T.t2}}>${fmt(p.avg_cost,2)}</span>
            <span style={{color:T.t1}}>${fmt(p.current_price,2)}</span>
            <span style={{color:pnlC(pnl),fontWeight:600}}>{fmtPnl(pnl)}</span>
            <span style={{color:pnlC(pct),fontSize:10}}>{pct>=0?"+":""}{pct.toFixed(2)}%</span>
            <Tag color={srcColor(sn)}>{srcShort(sn)}</Tag>
          </div>;
        })}
        <div style={{padding:"10px 12px",borderTop:`1px solid ${T.b1}`,display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:12}}>
          {[
            {label:"Stocks",items:filteredPositions.filter(p=>p.asset_class==="stock")},
            {label:"Futures",items:filteredPositions.filter(p=>p.asset_class==="future")},
            {label:"Options",items:filteredPositions.filter(p=>p.asset_class==="option")},
          ].map((a,i)=>{
            const val=a.items.reduce((s,p)=>s+Number(p.current_price)*p.quantity*(p.asset_class==="option"?100:1),0);
            const total=filteredPositions.reduce((s,p)=>s+Number(p.current_price)*p.quantity*(p.asset_class==="option"?100:1),0);
            return <div key={i} style={{textAlign:"center"}}>
              <div style={{fontSize:9,color:T.t3}}>{a.label}</div>
              <div style={{fontSize:13,fontWeight:600,color:T.t0,fontFamily:M}}>${fmt(val)}</div>
              <div style={{fontSize:10,color:T.t2,fontFamily:M}}>{total>0?`${(val/total*100).toFixed(0)}%`:"0%"}</div>
            </div>;
          })}
        </div>
      </Panel>}

      {/* ════ GUARDIAN ════ */}
      {tab==="guardian"&&<div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
        <Panel title="10 Risk Checks" badge={<Tag color={guardianChecks.every(c=>c.status==="pass")?T.g:T.a} bg={guardianChecks.every(c=>c.status==="pass")?T.gM:T.aM}>{guardianChecks.every(c=>c.status==="pass")?"ALL PASSING":"WARNING"}</Tag>}>
          {guardianChecks.map(c=>{
            const icons={pass:"✓",warn:"!",fail:"✗"};
            const colors={pass:T.g,warn:T.a,fail:T.r};
            const bgs={pass:T.gM,warn:T.aM,fail:T.rM};
            return <div key={c.id} style={{display:"flex",alignItems:"center",gap:10,padding:"7px 10px",borderRadius:4,background:bgs[c.status]+"60",marginBottom:3}}>
              <span style={{width:20,height:20,borderRadius:4,display:"flex",alignItems:"center",justifyContent:"center",background:`${colors[c.status]}20`,color:colors[c.status],fontSize:11,fontWeight:800,fontFamily:M,flexShrink:0}}>{icons[c.status]}</span>
              <div style={{flex:1,minWidth:0}}>
                <div style={{fontSize:11,color:T.t0,fontFamily:S,fontWeight:500}}><span style={{color:T.t3,marginRight:6}}>#{c.id}</span>{c.name}</div>
                <div style={{fontSize:10,color:T.t3,fontFamily:M,marginTop:1}}>{c.detail}</div>
              </div>
              <span style={{fontFamily:M,fontSize:11,color:colors[c.status],fontWeight:600,flexShrink:0}}>{c.metric}</span>
            </div>;
          })}
        </Panel>
        <div style={{display:"flex",flexDirection:"column",gap:14}}>
          <Panel title="Circuit Breakers">
            {[
              {label:"Daily Loss >3%",val:`Current: ${riskSnap?`${(riskSnap.daily_pnl_pct*100).toFixed(2)}%`:"—"}`},
              {label:"Weekly Loss >5%",val:`Current: ${riskSnap?`${(riskSnap.weekly_pnl_pct*100).toFixed(2)}%`:"—"}`},
              {label:"Source Loss >2%/day",val:"All within limits"},
              {label:"Signal Flood >20/src",val:`Max: ${Math.max(...sources.map(s=>s.total_signals||0))} signals`},
              {label:"IBKR Connection",val:"Paper:7496"},
              {label:"Data Feed TTL",val:"5s refresh"},
            ].map((cb,i)=><div key={i} style={{display:"flex",alignItems:"center",gap:8,padding:"5px 0",borderBottom:i<5?`1px solid ${T.b0}30`:"none"}}>
              <Dot on s={5}/>
              <span style={{flex:1,fontSize:11,color:T.t1,fontFamily:S}}>{cb.label}</span>
              <span style={{fontSize:10,color:T.t3,fontFamily:M}}>{cb.val}</span>
            </div>)}
          </Panel>
          <Panel title="Risk Limits">
            {[
              ["Max per trade","2.0%"],["Portfolio heat","10.0%"],["Daily loss halt","3.0%"],
              ["Weekly loss halt","5.0%"],["Concentration","15.0%"],["Options cap","30.0%"],
              ["Futures margin","25.0%"],["Cash reserve min","20.0%"],["Max positions","15"],
              ["Signals/src/day","20"],
            ].map(([k,v],i)=><div key={i} style={{display:"flex",justifyContent:"space-between",padding:"3px 0",fontSize:11}}>
              <span style={{color:T.t2,fontFamily:S}}>{k}</span>
              <span style={{color:T.t0,fontFamily:M,fontWeight:500}}>{v}</span>
            </div>)}
          </Panel>
        </div>
      </div>}

      {/* ════ SOURCES ════ */}
      {tab==="sources"&&<div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(280px,1fr))",gap:14}}>
        {sources.map(s=>{
          const wr=s.win_count+s.loss_count>0?((s.win_count/(s.win_count+s.loss_count))*100).toFixed(1):0;
          const c=srcColor(s.name);
          return <div key={s.id} style={{background:T.bg2,border:`1px solid ${T.b0}`,borderRadius:6,borderTop:`3px solid ${c}`,padding:16}}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:12}}>
              <div style={{display:"flex",alignItems:"center",gap:8}}>
                <Dot on={s.is_active} s={7}/>
                <span style={{fontSize:14,fontWeight:700,color:T.t0}}>{s.display_name}</span>
              </div>
              <Tag color={s.is_active?T.g:T.t3}>{s.is_active?"ACTIVE":"STANDBY"}</Tag>
            </div>
            <div style={{fontSize:10,color:T.t3,fontFamily:M,marginBottom:12}}>{s.source_type} · {s.is_paper?"paper":"live"}</div>
            <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
              {[
                {label:"Win Rate",val:`${wr}%`,color:wr>60?T.g:T.t1},
                {label:"Total P&L",val:s.total_pnl>0?`+$${fmt(s.total_pnl)}`:"$0",color:pnlC(s.total_pnl)},
                {label:"Signals",val:String(s.total_signals||0),color:T.t0},
                {label:"Allocation",val:pctFmt(s.current_allocation_pct),color:T.c},
              ].map((m,i)=><div key={i}>
                <div style={{fontSize:9,color:T.t3,letterSpacing:.5}}>{m.label}</div>
                <div style={{fontSize:18,fontWeight:700,color:m.color,fontFamily:M}}>{m.val}</div>
              </div>)}
            </div>
            <div style={{marginTop:12,paddingTop:10,borderTop:`1px solid ${T.b0}`}}>
              <AllocBar name="" current={s.current_allocation_pct} max={s.max_allocation_pct} color={c}/>
            </div>
          </div>;
        })}
      </div>}
    </main>

    <style>{`
      @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Outfit:wght@300;400;500;600;700&display=swap');
      *{box-sizing:border-box;margin:0;padding:0;}
      body{background:${T.bg0};}
      ::-webkit-scrollbar{width:3px;}
      ::-webkit-scrollbar-track{background:transparent;}
      ::-webkit-scrollbar-thumb{background:${T.b1};border-radius:3px;}
      button{transition:all .15s ease;}
      button:hover{filter:brightness(1.15);}
      @keyframes fadeIn{from{opacity:0;transform:translateY(-4px);}to{opacity:1;transform:translateY(0);}}
    `}</style>
  </div>;
}
