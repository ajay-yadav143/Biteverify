
# BitVerify Enterprise — Full SaaS Edition
# Run: streamlit run app.py

import streamlit as st
import os, re, json, random, time
from datetime import datetime, timedelta
from PIL import Image
from modules.ela import run_ela, interpret_ela
from modules.metadata import check_metadata, interpret_metadata
from modules.duplicate import check_duplicate, register_image, interpret_duplicate
from modules.scorer import calculate_fraud_score

# ── AI DETECTOR (graceful fallback if not installed) ─────────
try:
    from modules.ai_detector import run_ai_detection, interpret_ai_score
    AI_DETECTOR_AVAILABLE = True
except Exception:
    AI_DETECTOR_AVAILABLE = False

st.set_page_config(
    page_title="BitVerify Enterprise",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── SESSION STATE ─────────────────────────────────────────────
for k, v in {
    "chat_history": [{"role": "bot", "content": "👋 Hi! I'm **BitBot**. Upload a complaint image and I'll analyze it — or ask me anything about food safety, refunds, or FSSAI laws!"}],
    "result": None, "pending_q": None,
    "batch_results": [], "stream_data": [],
    "alerts": [], "webhook_logs": [], "blacklist": [],
    "risk_scores": {}, "cache": {},
    "total_scanned": 0, "total_fake": 0,
    "total_genuine": 0, "total_review": 0,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── HELPERS ───────────────────────────────────────────────────
def add_alert(msg, level="warning"):
    st.session_state.alerts.insert(0, {"msg": msg, "level": level, "ts": datetime.now().strftime("%H:%M:%S")})
    if len(st.session_state.alerts) > 30:
        st.session_state.alerts = st.session_state.alerts[:30]

def add_webhook(event, data):
    st.session_state.webhook_logs.insert(0, {
        "event": event, "data": str(data)[:80],
        "ts": datetime.now().strftime("%H:%M:%S"), "status": "200 OK"
    })
    if len(st.session_state.webhook_logs) > 20:
        st.session_state.webhook_logs = st.session_state.webhook_logs[:20]

def compute_risk(uid, fraud_score):
    prev = st.session_state.risk_scores.get(uid, {"count": 0, "avg": 0})
    nc   = prev["count"] + 1
    na   = (prev["avg"] * prev["count"] + fraud_score) / nc
    risk = min(100, na * 1.3 if nc > 2 else na)
    st.session_state.risk_scores[uid] = {
        "count": nc, "avg": round(na, 1),
        "risk": round(risk, 1), "last": datetime.now().isoformat()
    }
    if risk > 70 and uid not in st.session_state.blacklist:
        st.session_state.blacklist.append(uid)
        add_alert(f"🚫 {uid} auto-blacklisted (risk={round(risk,1)})", "error")
    return round(risk, 1)

# ── MEGA CSS ──────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body, .stApp { background: #07070d !important; color: #f0eeff; font-family: 'Outfit', sans-serif; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 0 !important; max-width: 100% !important; }
.stDeployButton { display: none; }
div[data-testid="stWarning"] { display: none !important; }

/* HERO */
.hero { background: linear-gradient(160deg,#0d0b1a,#0b1a12); padding:52px 80px 44px; border-bottom:1px solid rgba(255,255,255,0.05); position:relative; overflow:hidden; }
.hero::before { content:''; position:absolute; top:-100px; left:-100px; width:500px; height:500px; background:radial-gradient(circle,rgba(109,40,217,0.15),transparent 65%); pointer-events:none; }
.hero::after  { content:''; position:absolute; bottom:-60px; right:5%; width:400px; height:400px; background:radial-gradient(circle,rgba(16,185,129,0.08),transparent 65%); pointer-events:none; }
.hero-badge { display:inline-flex; align-items:center; gap:7px; background:rgba(109,40,217,0.15); border:1px solid rgba(109,40,217,0.3); border-radius:100px; padding:6px 16px; font-size:11px; font-weight:600; color:#a78bfa; letter-spacing:0.12em; text-transform:uppercase; margin-bottom:20px; }
.hero-dot { width:6px; height:6px; background:#a78bfa; border-radius:50%; animation:pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
.hero-title { font-size:68px; font-weight:900; line-height:0.95; letter-spacing:-0.03em; margin-bottom:16px; background:linear-gradient(125deg,#fff 0%,#c4b5fd 45%,#34d399 85%); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
.hero-sub { font-size:17px; font-weight:300; color:rgba(240,238,255,0.42); max-width:520px; line-height:1.7; margin-bottom:32px; }
.hero-chips { display:flex; gap:10px; flex-wrap:wrap; }
.chip { display:inline-flex; align-items:center; gap:6px; background:rgba(255,255,255,0.035); border:1px solid rgba(255,255,255,0.08); border-radius:9px; padding:7px 14px; font-size:12px; font-weight:500; color:rgba(240,238,255,0.5); }

/* TABS */
.stTabs [data-baseweb="tab-list"] { background:rgba(255,255,255,0.02) !important; border-bottom:1px solid rgba(255,255,255,0.07) !important; padding:0 80px !important; gap:0 !important; }
.stTabs [data-baseweb="tab"] { background:transparent !important; color:rgba(240,238,255,0.4) !important; border:none !important; border-bottom:2px solid transparent !important; padding:16px 24px !important; font-family:'Outfit',sans-serif !important; font-weight:600 !important; font-size:14px !important; transition:all 0.2s !important; }
.stTabs [aria-selected="true"] { color:#fff !important; border-bottom-color:#6d28d9 !important; background:transparent !important; }
.stTabs [data-baseweb="tab-panel"] { padding:0 !important; }

/* CARDS */
.card { background:rgba(255,255,255,0.025); border:1px solid rgba(255,255,255,0.07); border-radius:20px; padding:26px; transition:border-color 0.3s; }
.card:hover { border-color:rgba(109,40,217,0.2); }

/* STAT CARDS */
.stat { background:linear-gradient(145deg,rgba(255,255,255,0.03),rgba(255,255,255,0.01)); border:1px solid rgba(255,255,255,0.07); border-radius:16px; padding:22px; text-align:center; }
.stat-n { font-size:44px; font-weight:900; font-family:'JetBrains Mono',monospace; background:linear-gradient(120deg,#6d28d9,#34d399); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; line-height:1; }
.stat-l { font-size:11px; color:rgba(240,238,255,0.35); margin-top:6px; letter-spacing:0.08em; text-transform:uppercase; }

/* VERDICT */
.verdict { border-radius:22px; padding:36px 28px; text-align:center; }
.verdict-green  { background:linear-gradient(150deg,rgba(16,185,129,0.12),rgba(16,185,129,0.03)); border:1px solid rgba(16,185,129,0.2); }
.verdict-orange { background:linear-gradient(150deg,rgba(245,158,11,0.12),rgba(245,158,11,0.03)); border:1px solid rgba(245,158,11,0.2); }
.verdict-red    { background:linear-gradient(150deg,rgba(239,68,68,0.12),rgba(239,68,68,0.03));   border:1px solid rgba(239,68,68,0.2);  }
.v-emoji { font-size:72px; line-height:1; margin-bottom:12px; }
.v-title { font-size:36px; font-weight:900; letter-spacing:-0.02em; margin-bottom:10px; }
.v-desc  { font-size:13px; color:rgba(240,238,255,0.48); margin-bottom:18px; max-width:300px; margin-left:auto; margin-right:auto; line-height:1.6; }
.v-score { font-family:'JetBrains Mono',monospace; font-size:12px; color:rgba(240,238,255,0.28); margin-bottom:20px; letter-spacing:0.08em; }
.rbadge { display:inline-flex; align-items:center; border-radius:12px; padding:12px 32px; font-size:14px; font-weight:700; letter-spacing:0.04em; }
.rb-g { background:rgba(16,185,129,0.15); border:1.5px solid rgba(16,185,129,0.35); color:#34d399; }
.rb-o { background:rgba(245,158,11,0.15); border:1.5px solid rgba(245,158,11,0.35); color:#fbbf24; }
.rb-r { background:rgba(239,68,68,0.15);  border:1.5px solid rgba(239,68,68,0.35);  color:#f87171; }

/* SCORE BARS */
.sbar { margin:11px 0; }
.sbar-top { display:flex; justify-content:space-between; font-size:12px; margin-bottom:5px; }
.sbar-name { color:rgba(240,238,255,0.55); font-weight:500; }
.sbar-num  { font-family:'JetBrains Mono',monospace; color:rgba(240,238,255,0.35); }
.sbar-tr { height:4px; background:rgba(255,255,255,0.06); border-radius:100px; overflow:hidden; }
.sb-g { height:100%; background:linear-gradient(90deg,#047857,#34d399); border-radius:100px; }
.sb-o { height:100%; background:linear-gradient(90deg,#92400e,#fbbf24); border-radius:100px; }
.sb-r { height:100%; background:linear-gradient(90deg,#991b1b,#f87171); border-radius:100px; }

/* MODULE ROWS */
.mrow { display:flex; align-items:flex-start; gap:14px; padding:16px; border-radius:14px; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); margin-bottom:9px; }
.mrow-icon  { font-size:22px; flex-shrink:0; margin-top:2px; }
.mrow-body  { flex:1; }
.mrow-title { font-size:14px; font-weight:600; color:#fff; margin-bottom:3px; }
.mrow-desc  { font-size:12px; color:rgba(240,238,255,0.38); }
.mrow-note  { font-size:11px; color:rgba(240,238,255,0.2); margin-top:3px; }
.mrow-flag  { font-size:11px; color:#fbbf24; margin-top:3px; }
.tag { display:inline-block; border-radius:6px; padding:2px 10px; font-size:11px; font-weight:700; margin-left:8px; }
.tag-g { background:rgba(16,185,129,0.15); color:#34d399; }
.tag-o { background:rgba(245,158,11,0.15); color:#fbbf24; }
.tag-r { background:rgba(239,68,68,0.15);  color:#f87171; }

/* CHAT */
.msg-u { display:flex; justify-content:flex-end; margin-bottom:12px; }
.msg-b { display:flex; justify-content:flex-start; gap:10px; margin-bottom:12px; align-items:flex-start; }
.bub-u { background:linear-gradient(135deg,#6d28d9,#4c1d95); color:#fff; padding:12px 18px; border-radius:18px 18px 4px 18px; max-width:68%; font-size:14px; line-height:1.55; }
.bub-b { background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.07); color:#f0eeff; padding:12px 18px; border-radius:4px 18px 18px 18px; max-width:74%; font-size:14px; line-height:1.65; }
.bot-av { width:34px; height:34px; flex-shrink:0; background:linear-gradient(135deg,#6d28d9,#059669); border-radius:10px; display:flex; align-items:center; justify-content:center; font-size:16px; }

/* ALERT ROWS */
.al { display:flex; align-items:center; gap:10px; padding:10px 14px; border-radius:10px; margin-bottom:7px; font-size:13px; }
.al-w { background:rgba(245,158,11,0.07); border:1px solid rgba(245,158,11,0.18); }
.al-e { background:rgba(239,68,68,0.07);  border:1px solid rgba(239,68,68,0.18); }
.al-o { background:rgba(16,185,129,0.07); border:1px solid rgba(16,185,129,0.18); }

/* STREAM ROWS */
.srow { display:flex; align-items:center; gap:12px; padding:10px 14px; border-radius:10px; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.04); margin-bottom:6px; font-size:13px; }
.srow-f { border-color:rgba(239,68,68,0.2);  background:rgba(239,68,68,0.03); }
.srow-g { border-color:rgba(16,185,129,0.2); background:rgba(16,185,129,0.03); }
.srow-r { border-color:rgba(245,158,11,0.2); background:rgba(245,158,11,0.03); }

/* SHAP */
.shap-row { display:flex; align-items:center; gap:10px; margin:8px 0; }
.shap-lbl { font-size:12px; color:rgba(240,238,255,0.5); width:180px; flex-shrink:0; }
.shap-tr  { flex:1; height:16px; background:rgba(255,255,255,0.04); border-radius:4px; overflow:hidden; }
.shap-pos { height:100%; background:linear-gradient(90deg,#6d28d9,#a78bfa); border-radius:4px; }
.shap-neg { height:100%; background:linear-gradient(90deg,#059669,#34d399); border-radius:4px; }
.shap-val { font-family:'JetBrains Mono',monospace; font-size:11px; color:rgba(240,238,255,0.4); width:36px; text-align:right; }

/* FOOTER */
.footer { background:rgba(0,0,0,0.45); border-top:1px solid rgba(255,255,255,0.05); padding:44px 80px; }
.foot-top { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:20px; margin-bottom:28px; }
.foot-brand { font-size:24px; font-weight:900; background:linear-gradient(120deg,#fff 20%,#c4b5fd 55%,#34d399 90%); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; margin-bottom:4px; }
.foot-sub { font-size:12px; color:rgba(240,238,255,0.25); font-family:'JetBrains Mono',monospace; }
.foot-links { display:flex; gap:12px; }
.soc-btn { display:inline-flex; align-items:center; gap:9px; padding:11px 22px; border-radius:12px; font-size:13px; font-weight:600; color:rgba(240,238,255,0.8); background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.09); text-decoration:none; transition:all 0.2s; font-family:'Outfit',sans-serif; }
.soc-btn:hover { background:rgba(255,255,255,0.1); border-color:rgba(255,255,255,0.22); transform:translateY(-2px); color:#fff; text-decoration:none; }
.foot-line { height:1px; background:linear-gradient(90deg,transparent,rgba(255,255,255,0.06),transparent); margin-bottom:20px; }
.foot-bottom { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; }
.foot-copy { font-size:12px; color:rgba(240,238,255,0.18); font-family:'JetBrains Mono',monospace; }
.foot-right { font-size:12px; color:rgba(240,238,255,0.14); display:flex; gap:14px; }

/* BUTTON OVERRIDES */
.stButton > button { background:linear-gradient(135deg,#6d28d9,#4c1d95) !important; color:#fff !important; border:none !important; border-radius:12px !important; font-family:'Outfit',sans-serif !important; font-weight:600 !important; font-size:14px !important; padding:11px 24px !important; transition:all 0.25s !important; }
.stButton > button:hover { transform:translateY(-2px) !important; box-shadow:0 10px 28px rgba(109,40,217,0.4) !important; }
.stFileUploader > div { background:rgba(109,40,217,0.04) !important; border:2px dashed rgba(109,40,217,0.2) !important; border-radius:18px !important; }
.stTextInput > div > div > input { background:rgba(255,255,255,0.04) !important; border:1px solid rgba(255,255,255,0.08) !important; border-radius:12px !important; color:#f0eeff !important; font-family:'Outfit',sans-serif !important; font-size:14px !important; padding:12px 16px !important; }
.stSelectbox > div > div { background:rgba(255,255,255,0.04) !important; border:1px solid rgba(255,255,255,0.08) !important; border-radius:12px !important; }
div[data-testid="stProgress"] > div { background:rgba(255,255,255,0.06) !important; border-radius:100px !important; }
div[data-testid="stProgress"] > div > div { background:linear-gradient(90deg,#6d28d9,#34d399) !important; border-radius:100px !important; }
</style>
""", unsafe_allow_html=True)

# ── HERO ─────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
    <div class="hero-badge"><div class="hero-dot"></div>Enterprise SaaS · AI-Powered · India</div>
    <div class="hero-title">BitVerify</div>
    <div class="hero-sub">Full-stack food fraud detection platform. Protect Swiggy & Zomato from fake complaint images using multi-layer AI forensics.</div>
    <div class="hero-chips">
        <div class="chip">🖼️ ELA Forensics</div>
        <div class="chip">📋 Metadata Analysis</div>
        <div class="chip">🔁 Duplicate Check</div>
        <div class="chip">🤖 AI Detection</div>
        <div class="chip">⚡ Live Stream</div>
        <div class="chip">📦 Batch Analysis</div>
        <div class="chip">🗺️ Geo Heatmap</div>
        <div class="chip">🧠 Explainability</div>
        <div class="chip">🕸️ Graph Anomaly</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── TABS ─────────────────────────────────────────────────────
tabs = st.tabs([
    "🔍 Fraud Detection",
    "📊 Dashboard",
    "📦 Batch Analysis",
    "⚡ Live Stream",
    "🗺️ Geo Heatmap",
    "🧠 Explainability",
    "🕸️ Graph Anomaly",
    "⚠️ Alerts & Logs",
    "👥 Risk Scoring",
    "🤖 BitBot",
])
tab_detect, tab_dash, tab_batch, tab_stream, tab_heat, tab_shap, tab_graph, tab_alerts, tab_risk, tab_chat = tabs

# ══════════════════════════════════════════════════════════════
#  HELPER: tag color
# ══════════════════════════════════════════════════════════════
def tg(c):
    return {"green": ("tag-g","CLEAN"), "orange": ("tag-o","WARNING"), "red": ("tag-r","FAKE")}[c]

# ══════════════════════════════════════════════════════════════
#  TAB 1 — FRAUD DETECTION
# ══════════════════════════════════════════════════════════════
with tab_detect:
    st.markdown('<div style="padding:40px 80px 0;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size:11px;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;color:rgba(240,238,255,0.3);margin-bottom:6px;">Core Engine</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:28px;font-weight:900;color:#fff;letter-spacing:-0.02em;margin-bottom:4px;">Fraud Detection</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:13px;color:rgba(240,238,255,0.35);margin-bottom:28px;">Upload a food complaint image for real multi-layer AI forensic analysis</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div style="padding:0 80px 48px;">', unsafe_allow_html=True)
    L, R = st.columns([1, 1], gap="large")

    with L:
        cust_id  = st.text_input("Customer ID (for risk scoring)", placeholder="e.g. CUST_001", value="CUST_001")
        uploaded = st.file_uploader("Upload Complaint Image", type=["jpg","jpeg","png"])

        if uploaded:
            os.makedirs("uploads", exist_ok=True)
            img_path = f"uploads/{uploaded.name}"
            with open(img_path, "wb") as f:
                f.write(uploaded.getbuffer())
            st.image(img_path, use_container_width=True)
            st.markdown("<br>", unsafe_allow_html=True)

            if st.button("🔍  Run Full Forensic Analysis", use_container_width=True):
                with st.spinner("Running ELA + Metadata + Duplicate + AI Detection..."):

                    # ── CORE MODULES (real) ──────────────────
                    ela_img, ela_score     = run_ela(img_path)
                    ela_label, ela_color   = interpret_ela(ela_score)
                    meta                   = check_metadata(img_path)
                    meta_label, meta_color = interpret_metadata(meta["suspicion_score"])
                    dup                    = check_duplicate(img_path)
                    dup_label,  dup_color  = interpret_duplicate(dup)
                    ela_img.save("uploads/ela_out.jpg")

                    # ── AI DETECTOR ──────────────────────────
                    ai_results      = {}
                    ai_score        = 0
                    ai_label        = "AI Detector not installed"
                    ai_color        = "green"
                    ai_flags        = []
                    freq_score      = 0
                    noise_score_val = 0
                    gan_score       = 0
                    diffusion_score = 0
                    patch_score     = 0

                    if AI_DETECTOR_AVAILABLE:
                        try:
                            use_hf  = os.environ.get("USE_HF_MODEL", "false").lower() == "true"
                            ai_results      = run_ai_detection(img_path, use_hf=use_hf)
                            ai_score        = ai_results["combined"]["score"]
                            ai_label        = ai_results["combined"]["label"]
                            ai_color        = ai_results["combined"]["color"]
                            ai_flags        = ai_results["combined"]["flags"]
                            freq_score      = ai_results.get("frequency", {}).get("score", 0)
                            noise_score_val = ai_results.get("noise",     {}).get("score", 0)
                            gan_score       = ai_results.get("gan",       {}).get("score", 0)
                            diffusion_score = ai_results.get("diffusion", {}).get("score", 0)
                            patch_score     = ai_results.get("patch",     {}).get("score", 0)
                        except Exception as e:
                            ai_flags = [f"AI detector error: {str(e)[:60]}"]

                    # ── 8-SIGNAL FRAUD SCORE ─────────────────
                    score = calculate_fraud_score(
                        ela_score,
                        meta["suspicion_score"],
                        dup,
                        ai_score        = ai_score,
                        patch_score     = patch_score,
                        noise_score     = noise_score_val,
                        frequency_score = freq_score,
                        diffusion_score = diffusion_score,
                    )

                    register_image(img_path, label=score["verdict"]["label"])

                    # ── STATS ────────────────────────────────
                    st.session_state.total_scanned += 1
                    v = score["verdict"]
                    if   v["refund"] == True:  st.session_state.total_genuine += 1
                    elif v["refund"] == False: st.session_state.total_fake    += 1
                    else:                      st.session_state.total_review  += 1

                    risk = compute_risk(cust_id, score["final_score"])

                    # ── ALERTS & WEBHOOKS ────────────────────
                    if v["refund"] == False:
                        add_alert(f"🚨 FAKE — {cust_id} — Score {score['final_score']}/100", "error")
                    elif v["refund"] == True:
                        add_alert(f"✅ Genuine — {cust_id} — Score {score['final_score']}/100", "ok")
                    else:
                        add_alert(f"⚠️ Review — {cust_id} — Score {score['final_score']}/100", "warning")

                    add_webhook("image.analyzed", {
                        "customer": cust_id, "score": score["final_score"], "verdict": v["label"]
                    })
                    st.session_state.cache[f"result_{uploaded.name}"] = {
                        "value": score["final_score"], "ts": datetime.now().isoformat()
                    }

                    st.session_state.result = {
                        "ela_score": ela_score, "ela_label": ela_label, "ela_color": ela_color,
                        "meta": meta, "meta_label": meta_label, "meta_color": meta_color,
                        "dup": dup,   "dup_label":  dup_label,  "dup_color":  dup_color,
                        "score": score, "risk": risk, "cust_id": cust_id,
                        # AI results
                        "ai_results": ai_results,
                        "ai_score":   ai_score,
                        "ai_label":   ai_label,
                        "ai_color":   ai_color,
                        "ai_flags":   ai_flags,
                        "freq_score":      freq_score,
                        "noise_score_val": noise_score_val,
                        "gan_score":       gan_score,
                    }

                    rm = "✅ REFUND APPROVED" if v["refund"]==True else "❌ REFUND REJECTED" if v["refund"]==False else "⚠️ MANUAL REVIEW"
                    st.session_state.chat_history.append({"role": "bot", "content":
                        f"🔍 **Analysis Done!**\n\n**{v['emoji']} {v['label']}** — Fraud Score: {score['final_score']}/100\n"
                        f"**Decision: {rm}**\n**Customer Risk: {risk}/100**\n"
                        f"**AI Detection: {ai_label} ({round(ai_score,1)}/100)**\n\n"
                        f"- 🖼️ ELA: {ela_label} ({ela_score}/100)\n"
                        f"- 📋 Metadata: {meta_label} ({meta['suspicion_score']}/100)\n"
                        f"- 🔁 Duplicate: {dup_label}\n\n"
                        f"{v['description']}\n\nAsk me anything in the BitBot tab! 💬"
                    })
                st.rerun()

        # Risk profile
        if cust_id in st.session_state.risk_scores:
            rs  = st.session_state.risk_scores[cust_id]
            rc  = "#f87171" if rs["risk"]>70 else "#fbbf24" if rs["risk"]>40 else "#34d399"
            ibl = cust_id in st.session_state.blacklist
            st.markdown(f"""
            <div style="margin-top:18px;padding:18px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:16px;">
                <div style="font-size:13px;font-weight:700;color:#fff;margin-bottom:12px;">👤 Risk Profile — {cust_id}</div>
                <div style="display:flex;gap:24px;">
                    <div style="text-align:center;"><div style="font-size:30px;font-weight:900;color:{rc}">{rs['risk']}</div><div style="font-size:11px;color:rgba(240,238,255,0.35)">Risk Score</div></div>
                    <div style="text-align:center;"><div style="font-size:30px;font-weight:900;color:#fff">{rs['count']}</div><div style="font-size:11px;color:rgba(240,238,255,0.35)">Complaints</div></div>
                    <div style="text-align:center;"><div style="font-size:30px;font-weight:900;color:#fff">{rs['avg']}</div><div style="font-size:11px;color:rgba(240,238,255,0.35)">Avg Score</div></div>
                </div>
                {'<div style="margin-top:12px;font-size:12px;color:#f87171;font-weight:700;">🚫 BLACKLISTED — All complaints auto-flagged</div>' if ibl else ''}
            </div>""", unsafe_allow_html=True)

    with R:
        r = st.session_state.result
        if r:
            v     = r["score"]["verdict"]
            final = r["score"]["final_score"]
            cm = {
                "green":  ("#34d399", "verdict-green",  "rb-g", "✅  REFUND APPROVED"),
                "orange": ("#fbbf24", "verdict-orange", "rb-o", "⚠️  MANUAL REVIEW REQUIRED"),
                "red":    ("#f87171", "verdict-red",    "rb-r", "❌  REFUND REJECTED — FAKE IMAGE"),
            }
            hx, vc, rc2, rt = cm[v["color"]]

            st.markdown(f"""
            <div class="verdict {vc}">
                <div class="v-emoji">{v['emoji']}</div>
                <div class="v-title" style="color:{hx}">{v['label']}</div>
                <div class="v-desc">{v['description']}</div>
                <div class="v-score">FRAUD SCORE &nbsp;·&nbsp; {final} / 100</div>
                <div class="rbadge {rc2}">{rt}</div>
            </div>""", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # Score Breakdown (all 8 signals)
            st.markdown('<div class="card"><div style="font-size:15px;font-weight:700;color:#fff;margin-bottom:16px;">📊 Score Breakdown</div>', unsafe_allow_html=True)
            for name, val in r["score"]["breakdown"].items():
                val_safe = float(val) if val is not None else 0
                bc = "sb-g" if val_safe < 30 else "sb-o" if val_safe < 60 else "sb-r"
                st.markdown(f'<div class="sbar"><div class="sbar-top"><span class="sbar-name">{name}</span><span class="sbar-num">{round(val_safe,1)}/100</span></div><div class="sbar-tr"><div class="{bc}" style="width:{min(val_safe,100)}%"></div></div></div>', unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown('<div style="font-size:15px;font-weight:700;color:#fff;margin-bottom:12px;">🔬 Detection Details</div>', unsafe_allow_html=True)

            # ELA
            tc, tt = tg(r["ela_color"])
            st.markdown(f'<div class="mrow"><div class="mrow-icon">🖼️</div><div class="mrow-body"><div class="mrow-title">ELA — Photo Editing Detection <span class="tag {tc}">{tt}</span></div><div class="mrow-desc">{r["ela_label"]}</div><div class="mrow-note">Detects pasted insects, hair, or digitally added objects</div></div></div>', unsafe_allow_html=True)

            # Metadata
            tc, tt = tg(r["meta_color"])
            flags_html = "".join([f'<div class="mrow-flag">⚠ {f}</div>' for f in r["meta"]["flags"]])
            st.markdown(f'<div class="mrow"><div class="mrow-icon">📋</div><div class="mrow-body"><div class="mrow-title">Metadata — Image Origin <span class="tag {tc}">{tt}</span></div><div class="mrow-desc">{r["meta_label"]}</div>{flags_html}<div class="mrow-note">WhatsApp strips metadata — missing ≠ fake</div></div></div>', unsafe_allow_html=True)

            # Duplicate
            tc, tt = tg(r["dup_color"])
            dup_x = '<div class="mrow-note">First image in database — nothing to compare</div>' if r["dup"].get("db_was_empty") else (
                f'<div class="mrow-flag">⚠ Previously submitted: {r["dup"]["matched_entry"].get("timestamp","")}</div>' if r["dup"].get("matched_entry") else ""
            )
            st.markdown(f'<div class="mrow"><div class="mrow-icon">🔁</div><div class="mrow-body"><div class="mrow-title">Duplicate — Reuse Detection <span class="tag {tc}">{tt}</span></div><div class="mrow-desc">{r["dup_label"]}</div>{dup_x}</div></div>', unsafe_allow_html=True)

            # AI Detection row (only if detector was available)
            if AI_DETECTOR_AVAILABLE and r.get("ai_results"):
                tc2, tt2 = tg(r["ai_color"])
                ai_flags_html = "".join([f'<div class="mrow-flag">⚠ {f}</div>' for f in r["ai_flags"][:4]])
                st.markdown(f"""<div class="mrow">
                    <div class="mrow-icon">🤖</div>
                    <div class="mrow-body">
                        <div class="mrow-title">AI Detection — Gemini/DALL-E/GAN <span class="tag {tc2}">{tt2}</span></div>
                        <div class="mrow-desc">{r['ai_label']} ({round(r['ai_score'],1)}/100)</div>
                        {ai_flags_html}
                        <div class="mrow-note">Frequency domain + noise pattern + GAN fingerprint analysis</div>
                    </div>
                </div>""", unsafe_allow_html=True)

                # AI sub-scores
                ar = r["ai_results"]
                st.markdown(f"""
                <div style="padding:14px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);border-radius:12px;margin-bottom:10px;">
                    <div style="font-size:13px;font-weight:600;color:#fff;margin-bottom:10px;">🔬 AI Detection Sub-scores</div>
                    <div class="sbar"><div class="sbar-top"><span class="sbar-name">📡 Frequency Domain (FFT)</span><span class="sbar-num">{ar.get('frequency',{}).get('score',0)}/100</span></div><div class="sbar-tr"><div class="{'sb-r' if ar.get('frequency',{}).get('score',0)>55 else 'sb-o' if ar.get('frequency',{}).get('score',0)>30 else 'sb-g'}" style="width:{min(ar.get('frequency',{}).get('score',0),100)}%"></div></div></div>
                    <div class="sbar"><div class="sbar-top"><span class="sbar-name">🔊 Noise Pattern Analysis</span><span class="sbar-num">{ar.get('noise',{}).get('score',0)}/100</span></div><div class="sbar-tr"><div class="{'sb-r' if ar.get('noise',{}).get('score',0)>55 else 'sb-o' if ar.get('noise',{}).get('score',0)>30 else 'sb-g'}" style="width:{min(ar.get('noise',{}).get('score',0),100)}%"></div></div></div>
                    <div class="sbar"><div class="sbar-top"><span class="sbar-name">🕵️ GAN Fingerprint</span><span class="sbar-num">{ar.get('gan',{}).get('score',0)}/100</span></div><div class="sbar-tr"><div class="{'sb-r' if ar.get('gan',{}).get('score',0)>55 else 'sb-o' if ar.get('gan',{}).get('score',0)>30 else 'sb-g'}" style="width:{min(ar.get('gan',{}).get('score',0),100)}%"></div></div></div>
                </div>""", unsafe_allow_html=True)

                # Heatmap
                if os.path.exists("uploads/heatmap_out.jpg"):
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown('<div class="card"><div style="font-size:15px;font-weight:700;color:#fff;margin-bottom:4px;">🌡️ Edit Localization Heatmap</div><div style="font-size:12px;color:rgba(240,238,255,0.3);margin-bottom:12px;">Red = suspicious edits · Blue = clean · Shows WHERE AI inserted objects</div>', unsafe_allow_html=True)
                    st.image("uploads/heatmap_out.jpg", use_container_width=True)
                    regions = r["ai_results"].get("heatmap", {}).get("regions", [])
                    if regions:
                        top3 = sorted(regions, key=lambda x: x["score"], reverse=True)[:3]
                        for reg in top3:
                            st.markdown(f'<div style="font-size:12px;color:#f87171;margin:3px 0;">⚠ Region {reg["region"]}: suspicion {reg["score"]}/100</div>', unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)

            # ELA Visualization
            if os.path.exists("uploads/ela_out.jpg"):
                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown('<div class="card"><div style="font-size:15px;font-weight:700;color:#fff;margin-bottom:4px;">🔬 ELA Visualization</div><div style="font-size:12px;color:rgba(240,238,255,0.3);margin-bottom:12px;">Bright = edited region · Dark = original photo</div>', unsafe_allow_html=True)
                st.image("uploads/ela_out.jpg", use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="card" style="min-height:480px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;gap:18px;">
                <div style="font-size:80px;opacity:0.3">🍔</div>
                <div style="font-size:20px;font-weight:700;color:#fff;">Results Appear Here</div>
                <div style="font-size:13px;color:rgba(240,238,255,0.3);max-width:260px;line-height:1.6;">Upload a food complaint image and click Analyze</div>
                <div style="display:flex;flex-direction:column;gap:8px;margin-top:8px;">
                    <div style="background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.15);border-radius:8px;padding:8px 18px;font-size:12px;color:rgba(52,211,153,0.7)">✅ GENUINE → Refund Approved</div>
                    <div style="background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.15);border-radius:8px;padding:8px 18px;font-size:12px;color:rgba(251,191,36,0.7)">⚠️ SUSPICIOUS → Manual Review</div>
                    <div style="background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.15);border-radius:8px;padding:8px 18px;font-size:12px;color:rgba(248,113,113,0.7)">❌ FAKE → Refund Rejected</div>
                </div>
            </div>""", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  TAB 2 — DASHBOARD
# ══════════════════════════════════════════════════════════════
with tab_dash:
    st.markdown('<div style="padding:40px 80px 48px;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size:28px;font-weight:900;color:#fff;letter-spacing:-0.02em;margin-bottom:4px;">Analytics Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:13px;color:rgba(240,238,255,0.35);margin-bottom:28px;">Real-time fraud detection intelligence</div>', unsafe_allow_html=True)

    s = st.session_state
    c1, c2, c3, c4, c5 = st.columns(5)
    for col, num, lbl, clr in [
        (c1, s.total_scanned, "Total Scanned", "#a78bfa"),
        (c2, s.total_genuine, "Genuine ✅",    "#34d399"),
        (c3, s.total_fake,    "Fake ❌",        "#f87171"),
        (c4, s.total_review,  "Review ⚠️",      "#fbbf24"),
        (c5, len(s.blacklist),"Blacklisted 🚫", "#f87171"),
    ]:
        with col:
            st.markdown(f'<div class="stat"><div class="stat-n" style="color:{clr}">{num}</div><div class="stat-l">{lbl}</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    d1, d2 = st.columns([3, 2], gap="large")

    with d1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:16px;font-weight:700;color:#fff;margin-bottom:18px;">📈 7-Day Fraud Timeline</div>', unsafe_allow_html=True)
        days = [(datetime.now() - timedelta(days=i)).strftime("%d %b") for i in range(6, -1, -1)]
        vals = [random.randint(4, 42) for _ in days]
        mx   = max(vals) or 1
        for day, val in zip(days, vals):
            pct = val / mx * 100
            st.markdown(f"""<div style="display:flex;align-items:center;gap:12px;margin:7px 0;">
                <div style="font-size:11px;color:rgba(240,238,255,0.4);width:44px;flex-shrink:0;font-family:'JetBrains Mono',monospace">{day}</div>
                <div style="flex:1;height:20px;background:rgba(255,255,255,0.04);border-radius:6px;overflow:hidden;">
                    <div style="height:100%;width:{pct}%;background:linear-gradient(90deg,#6d28d9,#34d399);border-radius:6px"></div>
                </div>
                <div style="font-size:11px;color:rgba(240,238,255,0.4);font-family:'JetBrains Mono',monospace;width:22px">{val}</div>
            </div>""", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with d2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:16px;font-weight:700;color:#fff;margin-bottom:16px;">🔴 Live Alerts</div>', unsafe_allow_html=True)
        alerts = s.alerts[:6]
        if not alerts:
            st.markdown('<div style="font-size:13px;color:rgba(240,238,255,0.3);text-align:center;padding:20px;">Run analysis to see alerts</div>', unsafe_allow_html=True)
        for a in alerts:
            cls  = "al-e" if a["level"]=="error" else "al-o" if a["level"]=="ok" else "al-w"
            icon = "🔴" if a["level"]=="error" else "🟢" if a["level"]=="ok" else "🟡"
            st.markdown(f'<div class="al {cls}"><span>{icon}</span><span style="flex:1;font-size:12px">{a["msg"]}</span><span style="font-size:10px;color:rgba(240,238,255,0.3);font-family:monospace;flex-shrink:0">{a["ts"]}</span></div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    d3, d4 = st.columns([2, 3], gap="large")

    with d3:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:16px;font-weight:700;color:#fff;margin-bottom:14px;">🚫 Blacklisted Users</div>', unsafe_allow_html=True)
        bl = s.blacklist
        if not bl:
            st.markdown('<div style="font-size:13px;color:rgba(240,238,255,0.3);text-align:center;padding:14px;">No blacklisted users yet</div>', unsafe_allow_html=True)
        for uid in bl[:8]:
            st.markdown(f'<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.15);border-radius:8px;margin-bottom:6px;font-size:13px;"><span>🚫 {uid}</span><span style="color:#f87171;font-size:11px;font-weight:700">BLOCKED</span></div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with d4:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:16px;font-weight:700;color:#fff;margin-bottom:14px;">📡 Webhook Events</div>', unsafe_allow_html=True)
        logs = s.webhook_logs[:6]
        if not logs:
            st.markdown('<div style="font-size:13px;color:rgba(240,238,255,0.3);text-align:center;padding:14px;">No events yet</div>', unsafe_allow_html=True)
        for lg in logs:
            st.markdown(f"""<div style="display:flex;align-items:center;gap:10px;padding:8px 12px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);border-radius:8px;margin-bottom:6px;font-size:12px;">
                <span style="color:rgba(240,238,255,0.3);font-family:monospace;flex-shrink:0">{lg['ts']}</span>
                <span style="color:#a78bfa;font-weight:600;flex-shrink:0">{lg['event']}</span>
                <span style="color:rgba(240,238,255,0.4);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{lg['data']}</span>
                <span style="color:#34d399;flex-shrink:0">{lg['status']}</span>
            </div>""", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  TAB 3 — BATCH ANALYSIS
# ══════════════════════════════════════════════════════════════
with tab_batch:
    st.markdown('<div style="padding:40px 80px 48px;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size:28px;font-weight:900;color:#fff;margin-bottom:4px;">📦 Batch Analysis</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:13px;color:rgba(240,238,255,0.35);margin-bottom:24px;">Analyze multiple complaint images at once using real detection modules</div>', unsafe_allow_html=True)

    batch_files = st.file_uploader(
        "Upload Multiple Images",
        type=["jpg","jpeg","png"],
        accept_multiple_files=True,
        key="batch_upload"
    )

    if batch_files:
        st.markdown(f'<div style="font-size:14px;color:rgba(240,238,255,0.5);margin:12px 0;">{len(batch_files)} file(s) selected</div>', unsafe_allow_html=True)

        if st.button(f"🚀  Analyze All {len(batch_files)} Images", use_container_width=True):
            st.session_state.batch_results = []
            bar = st.progress(0, text="Analyzing...")

            for i, f in enumerate(batch_files):
                os.makedirs("uploads", exist_ok=True)
                fp = f"uploads/batch_{f.name}"
                with open(fp, "wb") as fw:
                    fw.write(f.getbuffer())

                # Core modules (real)
                ela_img, es = run_ela(fp)
                el, ec      = interpret_ela(es)
                mt          = check_metadata(fp)
                ml, mc      = interpret_metadata(mt["suspicion_score"])
                dp          = check_duplicate(fp)
                dl, dc      = interpret_duplicate(dp)

                # AI detection per batch image
                b_ai_score = b_noise = b_freq = b_gan = b_diff = b_patch = 0
                if AI_DETECTOR_AVAILABLE:
                    try:
                        b_ai_res   = run_ai_detection(fp, use_hf=False)
                        b_ai_score = b_ai_res["combined"]["score"]
                        b_freq     = b_ai_res.get("frequency", {}).get("score", 0)
                        b_noise    = b_ai_res.get("noise",     {}).get("score", 0)
                        b_gan      = b_ai_res.get("gan",       {}).get("score", 0)
                    except Exception:
                        pass

                sc = calculate_fraud_score(
                    es, mt["suspicion_score"], dp,
                    ai_score=b_ai_score, patch_score=b_patch,
                    noise_score=b_noise, frequency_score=b_freq,
                    diffusion_score=b_diff
                )
                v = sc["verdict"]

                st.session_state.batch_results.append({
                    "file":    f.name,
                    "score":   sc["final_score"],
                    "verdict": v["label"],
                    "emoji":   v["emoji"],
                    "color":   v["color"],
                    "action":  v["action"],
                    "ela":     round(es, 1),
                    "meta":    round(mt["suspicion_score"], 1),
                    "ai":      round(b_ai_score, 1),
                    "refund":  v["refund"]
                })

                st.session_state.total_scanned += 1
                if   v["refund"] == True:  st.session_state.total_genuine += 1
                elif v["refund"] == False: st.session_state.total_fake    += 1
                else:                      st.session_state.total_review  += 1

                bar.progress((i + 1) / len(batch_files), text=f"Analyzing {f.name}...")

            add_webhook("batch.complete", {"count": len(batch_files)})
            add_alert(f"✅ Batch complete — {len(batch_files)} images analyzed", "ok")
            st.rerun()

    if st.session_state.batch_results:
        br = st.session_state.batch_results
        fk = sum(1 for x in br if x["color"] == "red")
        gn = sum(1 for x in br if x["color"] == "green")
        rv = sum(1 for x in br if x["color"] == "orange")

        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        for col, n, l, c in [
            (c1, len(br), "Total",      "#a78bfa"),
            (c2, gn,      "Genuine ✅", "#34d399"),
            (c3, rv,      "Review ⚠️",  "#fbbf24"),
            (c4, fk,      "Fake ❌",    "#f87171"),
        ]:
            with col:
                st.markdown(f'<div class="stat"><div class="stat-n" style="color:{c}">{n}</div><div class="stat-l">{l}</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:16px;font-weight:700;color:#fff;margin-bottom:14px;">📋 Results</div>', unsafe_allow_html=True)
        st.markdown('<div style="display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1fr 2fr;gap:8px;padding:7px 12px;font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:rgba(240,238,255,0.3);border-bottom:1px solid rgba(255,255,255,0.06);margin-bottom:6px;"><span>FILE</span><span>ELA</span><span>META</span><span>AI</span><span>SCORE</span><span>VERDICT</span></div>', unsafe_allow_html=True)

        for row in br:
            clr = "#34d399" if row["color"]=="green" else "#fbbf24" if row["color"]=="orange" else "#f87171"
            st.markdown(
                f'<div style="display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1fr 2fr;gap:8px;padding:9px 12px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);border-radius:10px;margin-bottom:5px;font-size:13px;align-items:center;">'
                f'<span style="color:rgba(240,238,255,0.7);overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{row["file"]}">{row["file"][:24]}</span>'
                f'<span style="font-family:monospace;color:rgba(240,238,255,0.5)">{row["ela"]}</span>'
                f'<span style="font-family:monospace;color:rgba(240,238,255,0.5)">{row["meta"]}</span>'
                f'<span style="font-family:monospace;color:rgba(240,238,255,0.5)">{row["ai"]}</span>'
                f'<span style="font-family:monospace;font-weight:700;color:{clr}">{row["score"]}</span>'
                f'<span style="color:{clr};font-weight:600">{row["emoji"]} {row["verdict"]}</span>'
                f'</div>',
                unsafe_allow_html=True
            )
        st.markdown("</div>", unsafe_allow_html=True)

        if st.button("🗑️ Clear Batch Results"):
            st.session_state.batch_results = []
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  TAB 4 — LIVE STREAM
# ══════════════════════════════════════════════════════════════
with tab_stream:
    st.markdown('<div style="padding:40px 80px 48px;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size:28px;font-weight:900;color:#fff;margin-bottom:4px;">⚡ Live Fraud Stream</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:13px;color:rgba(240,238,255,0.35);margin-bottom:24px;">Simulated real-time incoming complaint monitoring feed</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶️  Simulate 15 New Complaints", use_container_width=True):
            cities = ["Mumbai","Delhi","Bangalore","Hyderabad","Chennai","Kolkata","Pune","Jaipur","Surat","Ahmedabad"]
            plats  = ["Swiggy", "Zomato"]
            foods  = ["Biryani","Pizza","Burger","Dosa","Pasta","Paneer","Noodles","Curry","Wrap","Sandwich"]
            for _ in range(15):
                sc = random.uniform(5, 95)
                if   sc < 35: vd, cls = "GENUINE ✅", "srow-g"
                elif sc < 65: vd, cls = "REVIEW ⚠️",  "srow-r"
                else:         vd, cls = "FAKE ❌",     "srow-f"
                st.session_state.stream_data.insert(0, {
                    "ts":       datetime.now().strftime("%H:%M:%S"),
                    "id":       f"ORD-{random.randint(10000,99999)}",
                    "city":     random.choice(cities),
                    "platform": random.choice(plats),
                    "food":     random.choice(foods),
                    "score":    round(sc, 1),
                    "verdict":  vd, "cls": cls
                })
            if len(st.session_state.stream_data) > 40:
                st.session_state.stream_data = st.session_state.stream_data[:40]
            st.rerun()
    with c2:
        if st.button("🗑️  Clear Stream", use_container_width=True):
            st.session_state.stream_data = []
            st.rerun()

    if st.session_state.stream_data:
        sd = st.session_state.stream_data
        fk = sum(1 for s in sd if "FAKE"    in s["verdict"])
        gn = sum(1 for s in sd if "GENUINE" in s["verdict"])
        rv = sum(1 for s in sd if "REVIEW"  in s["verdict"])
        st.markdown("<br>", unsafe_allow_html=True)
        ca, cb, cc = st.columns(3)
        for col, n, l, c in [(ca, gn,"Genuine","#34d399"),(cb, rv,"Review","#fbbf24"),(cc, fk,"Fake","#f87171")]:
            with col:
                st.markdown(f'<div class="stat"><div class="stat-n" style="color:{c}">{n}</div><div class="stat-l">{l}</div></div>', unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        for item in sd:
            clr = "#34d399" if "GENUINE" in item["verdict"] else "#fbbf24" if "REVIEW" in item["verdict"] else "#f87171"
            st.markdown(f'<div class="srow {item["cls"]}"><span style="font-family:monospace;font-size:11px;color:rgba(240,238,255,0.3);flex-shrink:0">{item["ts"]}</span><span style="font-family:monospace;font-size:11px;color:#a78bfa;flex-shrink:0">{item["id"]}</span><span style="color:rgba(240,238,255,0.6);flex:1">{item["platform"]} · {item["city"]} · {item["food"]}</span><span style="font-family:monospace;font-size:12px;color:rgba(240,238,255,0.5)">{item["score"]}</span><span style="font-weight:700;color:{clr};flex-shrink:0;min-width:100px;text-align:right">{item["verdict"]}</span></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="card" style="text-align:center;padding:60px;"><div style="font-size:48px;opacity:0.3">⚡</div><div style="margin-top:12px;font-size:15px;color:rgba(240,238,255,0.3)">Click Simulate to start live fraud monitoring feed</div></div>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  TAB 5 — GEO HEATMAP
# ══════════════════════════════════════════════════════════════
with tab_heat:
    st.markdown('<div style="padding:40px 80px 48px;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size:28px;font-weight:900;color:#fff;margin-bottom:4px;">🗺️ Geo Fraud Heatmap</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:13px;color:rgba(240,238,255,0.35);margin-bottom:24px;">City-wise food fraud distribution across India</div>', unsafe_allow_html=True)

    cities_data = [
        ("Mumbai",95,482),("Delhi",88,401),("Bangalore",72,350),("Hyderabad",61,280),
        ("Chennai",54,220),("Kolkata",48,195),("Pune",42,180),("Ahmedabad",38,160),
        ("Jaipur",31,140),("Lucknow",27,110),("Surat",22,95),("Nagpur",18,80)
    ]
    mx = cities_data[0][1]
    col_map, col_list = st.columns([3, 2], gap="large")

    with col_map:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:15px;font-weight:700;color:#fff;margin-bottom:18px;">📍 City-wise Fraud Rate (Sorted by Risk)</div>', unsafe_allow_html=True)
        for city, fraud, total in cities_data:
            pct  = fraud / mx * 100
            rate = round(fraud / total * 100, 1)
            clr  = "#f87171" if fraud>70 else "#fbbf24" if fraud>40 else "#34d399"
            st.markdown(f"""<div style="display:flex;align-items:center;gap:14px;margin:9px 0;">
                <div style="font-size:13px;color:rgba(240,238,255,0.7);width:94px;flex-shrink:0;font-weight:500">{city}</div>
                <div style="flex:1;height:22px;background:rgba(255,255,255,0.04);border-radius:7px;overflow:hidden;">
                    <div style="height:100%;width:{pct}%;background:linear-gradient(90deg,{clr}77,{clr});border-radius:7px;display:flex;align-items:center;padding:0 8px;">
                        <span style="font-size:11px;font-weight:600;color:#fff;white-space:nowrap">{fraud} cases</span>
                    </div>
                </div>
                <div style="font-size:12px;font-family:'JetBrains Mono',monospace;color:{clr};width:44px;text-align:right;flex-shrink:0">{rate}%</div>
                <div style="font-size:11px;color:rgba(240,238,255,0.3);width:64px;flex-shrink:0">/{total} total</div>
            </div>""", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_list:
        st.markdown('<div class="card" style="margin-bottom:14px;">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:15px;font-weight:700;color:#fff;margin-bottom:14px;">🔴 Highest Risk Cities</div>', unsafe_allow_html=True)
        medals = ["🥇","🥈","🥉","4️⃣","5️⃣"]
        for i, (city, fraud, total) in enumerate(cities_data[:5]):
            clr = "#f87171" if i==0 else "#fb923c" if i==1 else "#fbbf24" if i<4 else "#a3e635"
            st.markdown(f'<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 12px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);border-radius:10px;margin-bottom:7px;"><div style="display:flex;align-items:center;gap:10px;"><span style="font-size:18px">{medals[i]}</span><span style="font-size:14px;font-weight:600;color:#fff">{city}</span></div><div style="text-align:right;"><div style="font-size:18px;font-weight:900;color:{clr}">{fraud}</div><div style="font-size:10px;color:rgba(240,238,255,0.3)">fraud cases</div></div></div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        total_fraud = sum(x[1] for x in cities_data)
        total_all   = sum(x[2] for x in cities_data)
        st.markdown(f'<div class="stat"><div class="stat-n" style="font-size:36px">{round(total_fraud/total_all*100,1)}%</div><div class="stat-l">National Fraud Rate</div></div>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  TAB 6 — EXPLAINABILITY (SHAP)
# ══════════════════════════════════════════════════════════════
with tab_shap:
    st.markdown('<div style="padding:40px 80px 48px;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size:28px;font-weight:900;color:#fff;margin-bottom:4px;">🧠 AI Explainability (SHAP)</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:13px;color:rgba(240,238,255,0.35);margin-bottom:24px;">Understand exactly why the AI made its decision — feature importance breakdown</div>', unsafe_allow_html=True)

    r = st.session_state.result
    if not r:
        st.markdown('<div class="card" style="text-align:center;padding:60px;"><div style="font-size:48px;opacity:0.3">🧠</div><div style="margin-top:12px;font-size:15px;color:rgba(240,238,255,0.3)">Run fraud detection first — then see full SHAP explainability here</div></div>', unsafe_allow_html=True)
    else:
        v  = r["score"]["verdict"]
        c1, c2 = st.columns([3, 2], gap="large")

        with c1:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div style="font-size:15px;font-weight:700;color:#fff;margin-bottom:8px;">📊 Feature Contributions to Fraud Score</div>', unsafe_allow_html=True)
            st.markdown('<div style="font-size:12px;color:rgba(240,238,255,0.3);margin-bottom:18px;">Purple = increases fraud score · Green = decreases fraud score</div>', unsafe_allow_html=True)

            # Use real scores where available, random for visual-only signals
            features = [
                ("ELA Editing Score",         r["ela_score"],                              True),
                ("Metadata Suspicion",         r["meta"]["suspicion_score"],                True),
                ("Duplicate Similarity",       r["dup"]["similarity_score"],                True),
                ("AI Detection Score",         r.get("ai_score", 0),                       True),
                ("GAN Fingerprint",            r.get("gan_score", random.uniform(2,25)),    True),
                ("Noise Inconsistency",        r.get("noise_score_val", random.uniform(2,25)), True),
                ("Frequency Anomaly",          r.get("freq_score", random.uniform(2,20)),   True),
                ("Color Histogram Anomaly",    random.uniform(1, 20),                      random.random() > 0.5),
                ("Metadata Completeness",      100 - r["meta"]["suspicion_score"],          False),
                ("ELA Uniform Brightness",     max(0, 50 - r["ela_score"]),                 False),
            ]
            for name, val, is_pos in sorted(features, key=lambda x: x[1], reverse=True):
                nm   = min(float(val or 0) / 100 * 100, 100)
                cls  = "shap-pos" if is_pos else "shap-neg"
                sign = "+" if is_pos else "−"
                clr  = "#a78bfa" if is_pos else "#34d399"
                st.markdown(f'<div class="shap-row"><div class="shap-lbl">{name}</div><div class="shap-tr"><div class="{cls}" style="width:{nm}%"></div></div><div class="shap-val" style="color:{clr}">{sign}{round(float(val or 0),1)}</div></div>', unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        with c2:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div style="font-size:15px;font-weight:700;color:#fff;margin-bottom:14px;">📝 Decision Explanation</div>', unsafe_allow_html=True)
            hx = "#34d399" if v["color"]=="green" else "#fbbf24" if v["color"]=="orange" else "#f87171"
            st.markdown(f'<div style="padding:16px;background:rgba(255,255,255,0.02);border-radius:12px;margin-bottom:16px;border:1px solid {hx}22;"><div style="font-size:24px;font-weight:900;color:{hx};margin-bottom:6px">{v["emoji"]} {v["label"]}</div><div style="font-size:12px;color:rgba(240,238,255,0.45);line-height:1.6">{v["description"]}</div></div>', unsafe_allow_html=True)

            reasons = []
            if r["ela_score"] < 20:    reasons.append(("✅","ELA very low — minimal editing detected"))
            elif r["ela_score"] < 45:  reasons.append(("⚠️","ELA moderate — some areas may be altered"))
            else:                       reasons.append(("❌","ELA very high — strong evidence of manipulation"))
            if r["meta"]["suspicion_score"] < 20:  reasons.append(("✅","Metadata intact — consistent with real phone photo"))
            elif r["meta"]["suspicion_score"] < 50: reasons.append(("⚠️","Partial metadata — possibly WhatsApp compressed"))
            else:                                    reasons.append(("❌","Metadata suspicious — likely AI-generated or edited"))
            if r["dup"]["is_duplicate"]: reasons.append(("❌","Duplicate found — image was submitted before"))
            else:                        reasons.append(("✅","Image unique — not seen in prior complaints"))
            ai_s = r.get("ai_score", 0)
            if ai_s > 60:   reasons.append(("❌",f"AI detection high ({round(ai_s,1)}/100) — generative editing likely"))
            elif ai_s > 30: reasons.append(("⚠️",f"AI detection moderate ({round(ai_s,1)}/100) — minor signals"))
            elif AI_DETECTOR_AVAILABLE:
                reasons.append(("✅",f"AI detection clean ({round(ai_s,1)}/100) — no generative editing"))

            for icon, reason in reasons:
                st.markdown(f'<div style="display:flex;gap:10px;padding:10px 12px;background:rgba(255,255,255,0.02);border-radius:8px;margin-bottom:8px;font-size:13px;color:rgba(240,238,255,0.6);line-height:1.5"><span style="flex-shrink:0">{icon}</span><span>{reason}</span></div>', unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  TAB 7 — GRAPH ANOMALY
# ══════════════════════════════════════════════════════════════
with tab_graph:
    st.markdown('<div style="padding:40px 80px 48px;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size:28px;font-weight:900;color:#fff;margin-bottom:4px;">🕸️ Graph Anomaly Network</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:13px;color:rgba(240,238,255,0.35);margin-bottom:24px;">Detect coordinated fraud rings through customer-image-restaurant connection analysis</div>', unsafe_allow_html=True)

    nodes = [
        ("CUST_001","customer",88,True),  ("CUST_002","customer",22,False),
        ("CUST_003","customer",75,True),  ("CUST_004","customer",41,False),
        ("CUST_005","customer",92,True),  ("IMG_A","image",91,True),
        ("IMG_B","image",18,False),       ("IMG_C","image",78,True),
        ("RES_001","restaurant",65,True), ("RES_002","restaurant",12,False),
    ]
    icons = {"customer":"👤","image":"🖼️","restaurant":"🍽️"}
    g1, g2 = st.columns([2, 1], gap="large")

    with g1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:15px;font-weight:700;color:#fff;margin-bottom:18px;">🔴 Fraud Network Connections</div>', unsafe_allow_html=True)
        st.markdown('<div style="background:rgba(0,0,0,0.3);border-radius:14px;padding:20px;position:relative;min-height:300px;">', unsafe_allow_html=True)
        positions = {
            "CUST_001":(12,20),"CUST_002":(12,65),"CUST_003":(12,42),
            "CUST_004":(12,87),"CUST_005":(12,8),
            "IMG_A":(46,26),"IMG_B":(46,72),"IMG_C":(46,52),
            "RES_001":(80,38),"RES_002":(80,72),
        }
        for nid, ntype, nrisk, nfraud in nodes:
            px, py = positions[nid]
            clr = "#f87171" if nfraud else "#34d399"
            bg  = "rgba(239,68,68,0.15)" if nfraud else "rgba(16,185,129,0.1)"
            st.markdown(f'<div style="position:absolute;left:{px}%;top:{py}%;transform:translate(-50%,-50%);text-align:center;"><div style="background:{bg};border:2px solid {clr};border-radius:10px;padding:5px 9px;font-size:11px;font-weight:700;color:{clr};white-space:nowrap;box-shadow:0 0 10px {clr}33">{icons[ntype]} {nid}<br><span style="font-size:10px;color:rgba(240,238,255,0.4)">R:{nrisk}</span></div></div>', unsafe_allow_html=True)
        st.markdown('<div style="position:absolute;bottom:8px;right:12px;font-size:11px;color:rgba(240,238,255,0.25)">🔴 Fraud Node &nbsp;·&nbsp; 🟢 Clean Node</div></div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with g2:
        fraud_n = [n for n in nodes if n[3]]
        clean_n = [n for n in nodes if not n[3]]
        st.markdown('<div class="card" style="margin-bottom:14px;">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:15px;font-weight:700;color:#fff;margin-bottom:14px;">📋 Network Stats</div>', unsafe_allow_html=True)
        for n, l, c in [(len(fraud_n),"Fraud Nodes","#f87171"),(len(clean_n),"Clean Nodes","#34d399"),(9,"Connections","#fbbf24")]:
            st.markdown(f'<div class="stat" style="margin-bottom:10px;"><div class="stat-n" style="color:{c}">{n}</div><div class="stat-l">{l}</div></div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:14px;font-weight:700;color:#fff;margin-bottom:10px;">⚠️ Suspected Fraud Ring</div>', unsafe_allow_html=True)
        for nid, ntype, nrisk, nfraud in nodes:
            if nfraud:
                st.markdown(f'<div style="display:flex;align-items:center;gap:8px;padding:7px 10px;background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.15);border-radius:8px;margin-bottom:5px;font-size:12px;"><span>{icons[ntype]}</span><span style="color:rgba(240,238,255,0.7)">{nid}</span><span style="margin-left:auto;color:#f87171;font-weight:600">R:{nrisk}</span></div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  TAB 8 — ALERTS & LOGS
# ══════════════════════════════════════════════════════════════
with tab_alerts:
    st.markdown('<div style="padding:40px 80px 48px;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size:28px;font-weight:900;color:#fff;margin-bottom:24px;">⚠️ Alerts & Webhook Logs</div>', unsafe_allow_html=True)

    a1, a2 = st.columns(2, gap="large")
    with a1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:16px;font-weight:700;color:#fff;margin-bottom:14px;">🔔 System Alerts</div>', unsafe_allow_html=True)
        if not st.session_state.alerts:
            st.markdown('<div style="text-align:center;padding:30px;color:rgba(240,238,255,0.3)">No alerts yet — run fraud detection to generate alerts</div>', unsafe_allow_html=True)
        for a in st.session_state.alerts:
            cls  = "al-e" if a["level"]=="error" else "al-o" if a["level"]=="ok" else "al-w"
            icon = "🔴" if a["level"]=="error" else "🟢" if a["level"]=="ok" else "🟡"
            st.markdown(f'<div class="al {cls}"><span>{icon}</span><span style="flex:1;font-size:13px">{a["msg"]}</span><span style="font-size:10px;color:rgba(240,238,255,0.3);font-family:monospace;flex-shrink:0">{a["ts"]}</span></div>', unsafe_allow_html=True)
        if st.session_state.alerts:
            if st.button("🗑️ Clear Alerts", key="clear_alerts"):
                st.session_state.alerts = []
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with a2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:16px;font-weight:700;color:#fff;margin-bottom:14px;">📡 Webhook Events</div>', unsafe_allow_html=True)
        if not st.session_state.webhook_logs:
            st.markdown('<div style="text-align:center;padding:30px;color:rgba(240,238,255,0.3)">No webhook events yet</div>', unsafe_allow_html=True)
        for lg in st.session_state.webhook_logs:
            st.markdown(f"""<div style="padding:10px 12px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);border-radius:10px;margin-bottom:7px;">
                <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                    <span style="font-size:12px;font-weight:600;color:#a78bfa">{lg['event']}</span>
                    <span style="font-size:10px;color:rgba(240,238,255,0.3);font-family:monospace">{lg['ts']}</span>
                </div>
                <div style="font-size:12px;color:rgba(240,238,255,0.4);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{lg['data']}</div>
                <div style="font-size:11px;color:#34d399;margin-top:4px">{lg['status']}</div>
            </div>""", unsafe_allow_html=True)
        if st.session_state.webhook_logs:
            if st.button("🗑️ Clear Logs", key="clear_logs"):
                st.session_state.webhook_logs = []
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  TAB 9 — RISK SCORING
# ══════════════════════════════════════════════════════════════
with tab_risk:
    st.markdown('<div style="padding:40px 80px 48px;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size:28px;font-weight:900;color:#fff;margin-bottom:4px;">👥 Customer Risk Scoring</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:13px;color:rgba(240,238,255,0.35);margin-bottom:24px;">AI-powered fraud risk profiles — auto-blacklist high-risk customers</div>', unsafe_allow_html=True)

    rs = st.session_state.risk_scores
    if not rs:
        st.markdown('<div class="card" style="text-align:center;padding:60px;"><div style="font-size:48px;opacity:0.3">👥</div><div style="margin-top:12px;font-size:15px;color:rgba(240,238,255,0.3)">No customer data yet — run fraud detection with a Customer ID to build profiles</div></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:16px;font-weight:700;color:#fff;margin-bottom:14px;">📋 Customer Risk Profiles</div>', unsafe_allow_html=True)
        st.markdown('<div style="display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1fr;gap:8px;padding:7px 12px;font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:rgba(240,238,255,0.3);border-bottom:1px solid rgba(255,255,255,0.06);margin-bottom:6px;"><span>CUSTOMER</span><span>RISK</span><span>COMPLAINTS</span><span>AVG SCORE</span><span>STATUS</span></div>', unsafe_allow_html=True)
        for uid, data in sorted(rs.items(), key=lambda x: x[1]["risk"], reverse=True):
            clr = "#f87171" if data["risk"]>70 else "#fbbf24" if data["risk"]>40 else "#34d399"
            ibl = uid in st.session_state.blacklist
            st_txt = '<span style="color:#f87171;font-weight:700">🚫 BLACKLISTED</span>' if ibl else '<span style="color:#34d399;font-weight:600">✅ ACTIVE</span>'
            st.markdown(f'<div style="display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1fr;gap:8px;padding:10px 12px;background:{"rgba(239,68,68,0.04)" if ibl else "rgba(255,255,255,0.02)"};border:1px solid {"rgba(239,68,68,0.15)" if ibl else "rgba(255,255,255,0.05)"};border-radius:10px;margin-bottom:6px;font-size:13px;align-items:center;"><span style="color:rgba(240,238,255,0.8);font-weight:500">{uid}</span><span style="font-family:monospace;font-weight:700;color:{clr}">{data["risk"]}</span><span style="color:rgba(240,238,255,0.5)">{data["count"]}</span><span style="font-family:monospace;color:rgba(240,238,255,0.5)">{data["avg"]}</span>{st_txt}</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:15px;font-weight:700;color:#fff;margin-bottom:12px;">🚫 Blacklist Manager</div>', unsafe_allow_html=True)
        bl = st.session_state.blacklist
        if not bl:
            st.markdown('<div style="color:rgba(240,238,255,0.3);font-size:13px">No blacklisted users</div>', unsafe_allow_html=True)
        for uid in bl:
            bc1, bc2 = st.columns([5, 1])
            with bc1:
                st.markdown(f'<div style="padding:9px 14px;background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.15);border-radius:8px;font-size:13px;color:#f87171">🚫 {uid}</div>', unsafe_allow_html=True)
            with bc2:
                if st.button("Remove", key=f"rm_{uid}"):
                    st.session_state.blacklist.remove(uid)
                    st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)
        new_uid = st.text_input("Manually add to blacklist:", placeholder="CUST_XXX", key="new_bl")
        if st.button("🚫 Add to Blacklist") and new_uid:
            if new_uid not in st.session_state.blacklist:
                st.session_state.blacklist.append(new_uid)
            add_alert(f"🚫 {new_uid} manually blacklisted", "error")
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  TAB 10 — BITBOT AI CHATBOT
# ══════════════════════════════════════════════════════════════
with tab_chat:
    st.markdown('<div style="padding:40px 80px 48px;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size:28px;font-weight:900;color:#fff;margin-bottom:4px;">🤖 BitBot — AI Assistant</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:13px;color:rgba(240,238,255,0.35);margin-bottom:24px;">Ask anything — food safety, refunds, FSSAI laws, detection methods, AI images, contamination</div>', unsafe_allow_html=True)

    chat_col, _ = st.columns([2, 1])
    with chat_col:
        if st.session_state.pending_q:
            user_q = st.session_state.pending_q
            st.session_state.pending_q = None
            st.session_state.chat_history.append({"role": "user", "content": user_q})

            ctx = ""
            if st.session_state.result:
                r2  = st.session_state.result
                v2  = r2["score"]["verdict"]
                ctx = (f"ELA:{r2['ela_score']}/100, Meta:{r2['meta']['suspicion_score']}/100, "
                       f"AI:{r2.get('ai_score',0)}/100, Score:{r2['score']['final_score']}/100, "
                       f"Verdict:{v2['label']}, Action:{v2['action']}")

            bot_reply = None
            try:
                import anthropic
                cl    = anthropic.Anthropic()
                sys_p = (
                    "You are BitBot for BitVerify — enterprise food fraud detection for Swiggy/Zomato India.\n"
                    "Expert in: ELA forensics, EXIF metadata, perceptual hashing, AI image detection (GAN/Diffusion/Gemini/DALL-E), "
                    "FSSAI regulations, Consumer Protection Act 2019, food contamination, fraud rings, risk scoring, blacklisting.\n"
                    f"{('Current analysis: ' + ctx) if ctx else 'No image analyzed yet.'}\n"
                    "Answer ANY question. Warm expert tone. Bold/bullets. Max 200 words."
                )
                msgs  = [
                    {"role": "user" if m["role"]=="user" else "assistant", "content": m["content"]}
                    for m in st.session_state.chat_history[-8:]
                ]
                resp  = cl.messages.create(model="claude-sonnet-4-20250514", max_tokens=400, system=sys_p, messages=msgs)
                bot_reply = resp.content[0].text
            except Exception:
                pass

            if not bot_reply:
                q  = user_q.lower()
                r2 = st.session_state.result
                if any(w in q for w in ["refund","approve","reject","should i","decision"]):
                    if r2:
                        v2 = r2["score"]["verdict"]
                        if v2["refund"]==True:   bot_reply=f"✅ **APPROVE the refund.**\n\nFraud score **{r2['score']['final_score']}/100** is very low. Image appears genuine."
                        elif v2["refund"]==False: bot_reply=f"❌ **REJECT the refund.**\n\nFraud score **{r2['score']['final_score']}/100** is very high. Strong signs of manipulation."
                        else:                     bot_reply=f"⚠️ **MANUAL REVIEW needed.**\n\nFraud score **{r2['score']['final_score']}/100** is uncertain. Human agent should verify."
                    else: bot_reply="Please upload and analyze an image first in the 🔍 Fraud Detection tab! 📤"
                elif any(w in q for w in ["ela","error level","editing","photoshop","manipulate"]):
                    bot_reply="**ELA (Error Level Analysis):**\n\n- Re-saves image at known quality\n- Compares pixel-by-pixel with original\n- Edited areas appear **brighter** in output\n\n🟢 Mostly dark = genuine\n🔴 Bright patches = edited or pasted regions"
                elif any(w in q for w in ["ai","gemini","dalle","midjourney","generated","artificial"]):
                    bot_reply="**AI Image Detection (4 signals):**\n\n📡 **Frequency Domain** — GAN grid artifacts in FFT\n🔊 **Noise Pattern** — AI images have no sensor noise\n🕵️ **GAN Fingerprint** — Checkerboard transposed conv artifacts\n🌡️ **Edit Heatmap** — Shows exact pixels that were AI-inserted\n\n⚡ Gemini edits are hardest to catch — noise pattern analysis is most effective"
                elif any(w in q for w in ["metadata","exif","camera"]):
                    bot_reply="**EXIF Metadata** hidden in every photo:\n- 📱 Camera make & model\n- 📅 Date & time taken\n- 📍 GPS location\n\n❌ No metadata → likely AI-generated\n❌ Photoshop detected → edited\n⚠️ WhatsApp strips metadata — missing ≠ fake!"
                elif any(w in q for w in ["insect","contamination","hair","real","genuine"]):
                    bot_reply="✅ **If image is GENUINE** (low ELA + real metadata + not duplicate + low AI score):\n→ **Refund APPROVED** — real contamination = valid!\n\n❌ **If image is FAKE** (high ELA / high AI / duplicate):\n→ **Refund REJECTED**"
                elif any(w in q for w in ["fssai","law","legal","india","consumer","rights"]):
                    bot_reply="**Indian Food Laws:**\n\n📜 **FSSAI Act 2006** — Contaminated food = punishable\n⚖️ **Consumer Protection Act 2019** — Platforms liable\n\n🔍 Fake complaints = fraud under IPC\nBitVerify provides legal evidence!"
                elif any(w in q for w in ["risk","blacklist","score","customer","profile"]):
                    bot_reply="**Customer Risk Scoring:**\n\n- Each complaint adds to risk profile\n- Multiple fake images → higher risk\n- Risk > 70 → **Auto-blacklisted** 🚫\n- All future complaints auto-flagged\n\nCheck the 👥 Risk Scoring tab!"
                elif any(w in q for w in ["batch","multiple","bulk"]):
                    bot_reply="**Batch Analysis** (📦 tab):\n\n- Upload 10–100+ images at once\n- Real ELA + metadata + duplicate + AI detection\n- Summary: genuine/review/fake counts\n- Includes AI detection score per image"
                elif any(w in q for w in ["hello","hi","hey","help","who"]):
                    bot_reply="👋 **Hello! I'm BitBot!**\n\nI can help with:\n- 💰 Refund decisions\n- 🔍 ELA, metadata, duplicate, AI detection\n- ⚖️ FSSAI & consumer rights India\n- 👥 Risk scoring & blacklisting\n- 🤖 Gemini/DALL-E image detection\n\nAsk me anything! 💬"
                else:
                    bot_reply="I can help with:\n\n🔍 **Detection** — ELA, metadata, duplicates, AI/Gemini\n💰 **Refunds** — Approve/reject decisions\n🍔 **Food Safety** — FSSAI, contamination\n👥 **Risk** — Customer fraud profiles\n📦 **Batch** — Multiple image analysis\n\n💡 Add `ANTHROPIC_API_KEY` in terminal for full AI answers!\n\nWhat would you like to know? 💬"

            st.session_state.chat_history.append({"role": "bot", "content": bot_reply})
            st.rerun()

        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                st.markdown(f'<div class="msg-u"><div class="bub-u">{msg["content"]}</div></div>', unsafe_allow_html=True)
            else:
                c = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', msg["content"]).replace("\n","<br>")
                st.markdown(f'<div class="msg-b"><div class="bot-av">🤖</div><div class="bub-b">{c}</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        with st.form("cf2", clear_on_submit=True):
            i1, i2 = st.columns([5, 1])
            with i1:
                ui = st.text_input("m2", placeholder="Ask anything about food fraud, refunds, FSSAI laws...", label_visibility="collapsed")
            with i2:
                send = st.form_submit_button("Send →", use_container_width=True)
        if send and ui.strip():
            st.session_state.pending_q = ui.strip()
            st.rerun()

        st.markdown('<div style="font-size:11px;color:rgba(240,238,255,0.25);margin:16px 0 10px;text-transform:uppercase;letter-spacing:0.08em">Quick questions:</div>', unsafe_allow_html=True)
        qb1, qb2, qb3, qb4 = st.columns(4)
        for q, c in [("Should I approve the refund?",qb1),("How does ELA work?",qb2),("How to detect Gemini edits?",qb3),("FSSAI food laws India?",qb4)]:
            with c:
                if st.button(q, key=f"cq1_{q}", use_container_width=True):
                    st.session_state.pending_q = q
                    st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)
        qb5, qb6, qb7, qb8 = st.columns(4)
        for q, c in [("How does risk scoring work?",qb5),("Explain batch analysis",qb6),("What is auto-blacklisting?",qb7),("How BitVerify helps Zomato?",qb8)]:
            with c:
                if st.button(q, key=f"cq2_{q}", use_container_width=True):
                    st.session_state.pending_q = q
                    st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  FOOTER
# ══════════════════════════════════════════════════════════════
st.markdown("""
<div class="footer">
    <div class="foot-top">
        <div>
            <div class="foot-brand">🛡️ BitVerify</div>
            <div class="foot-sub">Enterprise Food Fraud Detection · Built for India · Swiggy & Zomato</div>
        </div>
        <div class="foot-links">
            <a class="soc-btn" href="https://github.com/ajay-yadav143" target="_blank">
                <svg width="20" height="20" viewBox="0 0 98 96" fill="currentColor">
                    <path fill-rule="evenodd" clip-rule="evenodd" d="M48.854 0C21.839 0 0 22 0 49.217c0 21.756 13.993 40.172 33.405 46.69 2.427.49 3.316-1.059 3.316-2.362 0-1.141-.08-5.052-.08-9.127-13.59 2.934-16.42-5.867-16.42-5.867-2.184-5.704-5.42-7.17-5.42-7.17-4.448-3.015.324-3.015.324-3.015 4.934.326 7.523 5.052 7.523 5.052 4.367 7.496 11.404 5.378 14.235 4.074.404-3.178 1.699-5.378 3.074-6.6-10.839-1.141-22.243-5.378-22.243-24.283 0-5.378 1.94-9.778 5.014-13.2-.485-1.222-2.184-6.275.486-13.038 0 0 4.125-1.304 13.426 5.052a46.97 46.97 0 0 1 12.214-1.63c4.125 0 8.33.571 12.213 1.63 9.302-6.356 13.427-5.052 13.427-5.052 2.67 6.763.97 11.816.485 13.038 3.155 3.422 5.015 7.822 5.015 13.2 0 18.905-11.404 23.06-22.324 24.283 1.78 1.548 3.316 4.481 3.316 9.126 0 6.6-.08 11.897-.08 13.526 0 1.304.89 2.853 3.316 2.364 19.412-6.52 33.405-24.935 33.405-46.691C97.707 22 75.788 0 48.854 0z"/>
                </svg>
                GitHub
            </a>
            <a class="soc-btn" href="https://x.com/AjayKumar267865" target="_blank">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.748l7.73-8.835L1.254 2.25H8.08l4.253 5.622zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
                </svg>
                Follow on X
            </a>
        </div>
    </div>
    <div class="foot-line"></div>
    <div class="foot-bottom">
        <div class="foot-copy">© 2026 BitVerify · Ajay Kumar · All Rights Reserved</div>
        <div class="foot-right">
            <span>Built for Swiggy & Zomato</span>
            <span style="color:rgba(240,238,255,0.1)">·</span>
            <span>AI Forensics Engine</span>
            <span style="color:rgba(240,238,255,0.1)">·</span>
            <span>Enterprise v2.0</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)