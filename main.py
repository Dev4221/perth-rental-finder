"""
Perth Rental Finder - FastAPI backend
Replaces Streamlit. Serves the HTML frontend and all API endpoints.
Run: uvicorn main:app --reload
"""
import os, re, json, sys
import datetime as _dt

# Same Windows console encoding issue as diagnose7.py - main.py's own
# print() debug lines (DB connection errors, etc.) could otherwise crash on
# non-cp1252 characters when run directly on Windows.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Add project directory to path so database, agent, rag etc can be found
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from typing import Optional
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv
import pandas as pd
import anthropic

load_dotenv()
app = FastAPI()

# `db` is the imported database module (thin DuckDB wrapper exposing
# query_df / query_one / get_connection), used defensively throughout this
# file via `if not db: ...`. If the import fails (e.g. warehouse not built
# yet, or running outside the project directory), db becomes None and every
# caller already has a fallback path, rather than crashing on startup.
try:
    import database as db
    db.get_connection()
except Exception as _db_err:
    print(f"WARNING: database module failed to load ({_db_err}); "
          f"running with db=None, all data-backed endpoints will return empty results.")
    db = None

from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    tb = traceback.format_exc()
    print(f"UNHANDLED ERROR: {exc}\n{tb}")
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "traceback": tb}
    )

INDEX_HTML = '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>Perth Rental Finder</title>\n<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&display=swap" rel="stylesheet">\n<style>\n*{box-sizing:border-box;margin:0;padding:0}\n:root{\n  --bg:#ffffff;--bg2:#f5f5f4;--bg3:#f0efed;\n  --text:#1a1a1a;--text2:#6b7280;--text3:#9ca3af;\n  --border:#e5e5e3;--border2:#d1d0ce;\n  --green:#0D7C66;--green-bg:#e8f5f1;--green-text:#065F46;\n  --amber:#B45309;--amber-bg:#fef3c7;\n  --red:#B91C1C;--red-bg:#fee2e2;\n  --blue:#1D4ED8;--blue-bg:#eff6ff;\n  --paper:#f7f4ee;--paper2:#efe9dd;--ink:#181614;--ink2:#5a5650;--ink3:#9a958c;\n  --radius:12px;--radius-sm:8px;\n  --serif:\'Fraunces\',ui-serif,Georgia,serif;\n  font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',system-ui,sans-serif;\n  color-scheme:light dark;\n}\n/* Default: dark mode follows OS preference, unless the person has made an\n   explicit choice via the toggle (tracked with data-theme on <html>). */\n@media(prefers-color-scheme:dark){\n  html:not([data-theme]):root,\n  html[data-theme="dark"]:root{\n    --bg:#1c1c1e;--bg2:#2c2c2e;--bg3:#3a3a3c;\n    --text:#f5f5f5;--text2:#aeaeb2;--text3:#636366;\n    --border:#3a3a3c;--border2:#48484a;\n    --green-bg:#0a3326;--green-text:#4ade80;\n    --amber-bg:#3d2800;--red-bg:#3d0f0f;--blue-bg:#0c1a3d;\n    --paper:#211f1c;--paper2:#2a2723;--ink:#f0eee9;--ink2:#b8b3a8;--ink3:#7a766e;\n  }\n}\n/* Explicit light, regardless of OS preference */\nhtml[data-theme="light"]:root{\n  --bg:#ffffff;--bg2:#f5f5f4;--bg3:#f0efed;\n  --text:#1a1a1a;--text2:#6b7280;--text3:#9ca3af;\n  --border:#e5e5e3;--border2:#d1d0ce;\n  --green-bg:#e8f5f1;--green-text:#065F46;\n  --amber-bg:#fef3c7;--red-bg:#fee2e2;--blue-bg:#eff6ff;\n  --paper:#f7f4ee;--paper2:#efe9dd;--ink:#181614;--ink2:#5a5650;--ink3:#9a958c;\n}\n/* Explicit dark, regardless of OS preference */\nhtml[data-theme="dark"]:root{\n  --bg:#1c1c1e;--bg2:#2c2c2e;--bg3:#3a3a3c;\n  --text:#f5f5f5;--text2:#aeaeb2;--text3:#636366;\n  --border:#3a3a3c;--border2:#48484a;\n  --green-bg:#0a3326;--green-text:#4ade80;\n  --amber-bg:#3d2800;--red-bg:#3d0f0f;--blue-bg:#0c1a3d;\n  --paper:#211f1c;--paper2:#2a2723;--ink:#f0eee9;--ink2:#b8b3a8;--ink3:#7a766e;\n}\nbody{background:var(--bg3);color:var(--text);min-height:100vh;display:flex;flex-direction:column;align-items:center}\n.app{width:100%;max-width:780px;min-height:100vh;background:var(--bg);display:flex;flex-direction:column}\n\n/* Header */\n.header{padding:16px 18px 0;border-bottom:0.5px solid var(--border);background:var(--paper)}\n.header-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;gap:10px}\n.wordmark{display:flex;align-items:center;gap:9px;min-width:0}\n.logo{width:30px;height:30px;border-radius:9px;background:var(--green);display:flex;align-items:center;justify-content:center;color:#fff;flex-shrink:0}\n.logo svg{width:16px;height:16px}\n.app-name{font-family:var(--serif);font-size:16px;font-weight:600;letter-spacing:-.01em;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}\n.nav{display:flex;gap:5px;align-items:center;flex-shrink:0}\n.nav-btn{width:32px;height:32px;padding:0;border-radius:9px;border:0.5px solid var(--border2);background:transparent;color:var(--ink2);cursor:pointer;font-family:inherit;transition:all .15s;display:flex;align-items:center;justify-content:center;flex-shrink:0}\n.nav-btn svg{width:15px;height:15px}\n.nav-btn:hover{background:var(--bg2)}\n.nav-btn.active{background:var(--green-bg);color:var(--green-text);border-color:rgba(13,124,102,.3)}\n.nav-btn.danger:hover{color:var(--red);border-color:rgba(185,28,28,.3)}\n.theme-btn{width:32px;height:32px;border-radius:9px;border:0.5px solid var(--border2);background:transparent;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:all .15s;color:var(--ink2);flex-shrink:0}\n.theme-btn svg{width:15px;height:15px}\n.theme-btn:hover{background:var(--bg2)}\n\n/* Chat */\n.chat-body{flex:1;padding:16px 20px;display:flex;flex-direction:column;gap:14px;overflow-y:auto}\n.msg{display:flex;gap:10px;align-items:flex-start}\n.msg.u{flex-direction:row-reverse}\n.av{width:30px;height:30px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:13px}\n.av.ai{background:var(--green-bg);color:var(--green-text)}\n.av.u{background:var(--bg2);border:0.5px solid var(--border);color:var(--text2)}\n.msg-content{max-width:83%;display:flex;flex-direction:column;gap:8px}\n.bub{padding:11px 14px;font-size:13px;line-height:1.7}\n.bub.ai{background:var(--bg2);border-radius:4px 13px 13px 13px;color:var(--text)}\n.bub.u{background:var(--green);color:#fff;border-radius:13px 4px 13px 13px}\n.msg-label{font-size:10px;color:var(--text3);margin-bottom:2px}\n.msg-label.u{text-align:right}\n\n/* Suburb search cards */\n.suburb-card{border:0.5px solid var(--border);border-radius:var(--radius);padding:14px 16px;background:var(--bg)}\n.suburb-card.best{border-color:var(--green);border-width:1.5px}\n.sc-top{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:10px}\n.sc-name{font-family:var(--serif);font-size:16px;font-weight:600;letter-spacing:-.01em}\n.sc-sub{font-size:10px;color:var(--text3);margin-top:2px}\n.sc-right{text-align:right}\n.sc-rent{font-size:20px;font-weight:500;color:var(--green);letter-spacing:-.02em}\n.rank-pill{display:inline-block;font-size:10px;font-weight:500;padding:3px 9px;border-radius:20px;margin-top:4px;background:var(--green-bg);color:var(--green-text)}\n.rank-pill.second{background:var(--bg2);color:var(--text2);border:0.5px solid var(--border)}\n.sc-chips{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:9px}\n.chip{display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:500;padding:3px 9px;border-radius:20px}\n.chip svg{width:11px;height:11px;flex-shrink:0}\n.chip.green{background:var(--green-bg);color:var(--green-text)}\n.chip.blue{background:var(--blue-bg);color:var(--blue)}\n.chip.amber{background:var(--amber-bg);color:var(--amber)}\n.chip.red{background:var(--red-bg);color:var(--red)}\n.chip.gray{background:var(--bg2);color:var(--text2);border:0.5px solid var(--border)}\n.sc-notes{font-size:11px;color:var(--text3);margin-bottom:6px}\n.sc-desc{font-size:12px;color:var(--text2);line-height:1.6;padding-top:8px;border-top:0.5px solid var(--border)}\n\n/* Deep dive card */\n.dive-card{border:0.5px solid var(--border);border-radius:var(--radius);padding:16px;background:var(--bg)}\n.dive-name{font-size:17px;font-weight:500;margin-bottom:2px}\n.dive-sub{font-size:10px;color:var(--text3);margin-bottom:14px}\n.data-rows{background:var(--bg2);border-radius:var(--radius-sm);padding:4px 12px;margin-bottom:10px}\n.dr{display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:0.5px solid var(--border)}\n.dr:last-child{border:none}\n.dr-lbl{font-size:12px;color:var(--text3)}\n.dr-right{display:flex;align-items:center;gap:8px}\n.dr-val{font-size:13px;font-weight:500}\n.dr-val.green{color:var(--green)}\n.dr-val.red{color:var(--red)}\n.dr-val.amber{color:var(--amber)}\n.dr-hist{font-size:10px;color:var(--text3)}\n.chip-rows{background:var(--bg2);border-radius:var(--radius-sm);padding:4px 12px;margin-bottom:10px}\n.cr{display:flex;align-items:center;gap:9px;padding:8px 0;border-bottom:0.5px solid var(--border)}\n.cr:last-child{border:none}\n.cr-icon{width:22px;height:22px;border-radius:6px;display:flex;align-items:center;justify-content:center;flex-shrink:0}\n.cr-icon svg{width:12px;height:12px}\n.cr-icon.green{background:var(--green-bg);color:var(--green-text)}\n.cr-icon.blue{background:var(--blue-bg);color:var(--blue)}\n.cr-icon.amber{background:var(--amber-bg);color:var(--amber)}\n.cr-text{font-size:12px;color:var(--text2);flex:1}\n.cr-badge{font-size:10px;font-weight:500;padding:2px 8px;border-radius:20px;white-space:nowrap}\n.cr-badge.green{background:var(--green-bg);color:var(--green-text)}\n.cr-badge.amber{background:var(--amber-bg);color:var(--amber)}\n.cr-badge.red{background:var(--red-bg);color:var(--red)}\n.trend-note{border-radius:var(--radius-sm);padding:9px 12px;font-size:12px;line-height:1.55;border-radius:0 var(--radius-sm) var(--radius-sm) 0}\n.trend-note.green{background:var(--green-bg);color:var(--green-text);border-left:3px solid var(--green)}\n.trend-note.amber{background:var(--amber-bg);color:var(--amber);border-left:3px solid var(--amber)}\n.trend-note.red{background:var(--red-bg);color:var(--red);border-left:3px solid var(--red)}\n\n/* Property advisor verdict */\n.verdict{border-radius:var(--radius-sm);padding:11px 14px;margin-bottom:10px;font-size:13px;font-weight:500}\n.verdict.caution{background:var(--amber-bg);color:var(--amber);border:0.5px solid rgba(180,83,9,.25)}\n.verdict.walkaway{background:var(--red-bg);color:var(--red);border:0.5px solid rgba(185,28,28,.25)}\n.verdict.proceed{background:var(--green-bg);color:var(--green-text);border:0.5px solid rgba(13,124,102,.25)}\n\n/* Agent prose */\n.agent-prose{font-size:13px;color:var(--text2);line-height:1.75}\n.agent-prose strong,.agent-prose b{color:var(--text);font-weight:500}\n.script-box{background:var(--bg2);border-radius:0 var(--radius-sm) var(--radius-sm) 0;border-left:3px solid var(--green);padding:10px 13px;font-style:italic;font-size:12.5px;line-height:1.7;color:var(--text2);margin-top:8px}\n\n\n/* Input */\n.input-row{padding:10px 16px 14px;border-top:0.5px solid var(--border);display:flex;align-items:center;gap:8px;background:var(--bg)}\n.chat-input{flex:1;height:40px;border-radius:11px;border:0.5px solid var(--border2);background:var(--bg2);font-size:13px;padding:0 13px;color:var(--text);font-family:inherit;outline:none;transition:border .15s}\n.chat-input:focus{border-color:var(--green)}\n.send-btn{width:40px;height:40px;border-radius:11px;border:none;background:var(--green);display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0;transition:opacity .15s}\n.send-btn:hover{opacity:.85}\n.send-btn svg{width:16px;height:16px;fill:none;stroke:#fff;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}\n.mic-btn{width:40px;height:40px;border-radius:50%;border:0.5px solid var(--border2);background:var(--bg2);display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0;transition:all .2s}\n.mic-btn.listening{background:#E05252;border-color:#E05252}\n.mic-btn svg{width:16px;height:16px;fill:none;stroke:var(--text2);stroke-width:2;stroke-linecap:round;stroke-linejoin:round}\n.mic-btn.listening svg{stroke:#fff}\n\n/* Typing indicator */\n.typing{display:flex;gap:4px;align-items:center;padding:11px 14px;background:var(--bg2);border-radius:4px 13px 13px 13px;width:fit-content}\n.typing span{width:7px;height:7px;border-radius:50%;background:var(--text3);animation:dot .8s infinite alternate}\n.typing span:nth-child(2){animation-delay:.15s}\n.typing span:nth-child(3){animation-delay:.3s}\n@keyframes dot{from{opacity:.3;transform:scale(.8)}to{opacity:1;transform:scale(1)}}\n/* Quick-reply chips for conversational questionnaire */\n.qr-wrap{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;max-width:83%}\n.qr-chip{display:inline-flex;align-items:center;padding:7px 14px;border-radius:20px;border:1.5px solid var(--green);background:transparent;color:var(--green-text);font-size:12.5px;font-weight:500;cursor:pointer;font-family:inherit;transition:all .15s}\n.qr-chip:hover,.qr-chip.selected{background:var(--green);color:#fff;border-color:var(--green)}\n.qr-chip.multi.selected{background:var(--green-bg);color:var(--green-text);border-color:var(--green)}\n.qr-submit{margin-top:8px;padding:9px 20px;border-radius:20px;border:none;background:var(--green);color:#fff;font-size:13px;font-weight:500;cursor:pointer;font-family:inherit;opacity:.45;pointer-events:none;transition:all .15s}\n.qr-submit.ready{opacity:1;pointer-events:auto}\n.qr-note{font-size:11px;color:var(--text3);margin-top:3px}\n\n/* Market context strip */\n.market-strip{background:var(--green-bg);border:0.5px solid rgba(13,124,102,.2);border-radius:var(--radius);padding:12px 15px;font-size:12px}\n.market-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:8px}\n.market-cell{text-align:center}\n.market-n{font-size:17px;font-weight:500;color:var(--green);letter-spacing:-.02em}\n.market-l{font-size:10px;color:var(--green-text);opacity:.7;margin-top:1px}\n.market-note{font-size:11px;color:var(--green-text);opacity:.8;line-height:1.5;border-top:0.5px solid rgba(13,124,102,.15);padding-top:7px}\n\n/* Also worth considering label */\n.section-label{font-size:13px;font-weight:500;color:var(--text2);padding:4px 0 2px}\n\n/* Seasonal */\n.seasonal{background:var(--green-bg);border-radius:var(--radius-sm);padding:10px 13px;font-size:12px;color:var(--green-text);line-height:1.6;display:flex;gap:8px;align-items:flex-start}\n.month-pills{display:flex;gap:4px;flex-shrink:0;flex-wrap:wrap;max-width:120px}\n.month-pill{font-size:10px;font-weight:500;padding:2px 8px;border-radius:20px;background:rgba(13,124,102,.15);color:var(--green-text)}\n\n@media(max-width:600px){\n  .market-grid{grid-template-columns:repeat(2,1fr)}\n}\n\n/* Survey / Step-by-step mode */\n.survey-body{flex:1;padding:16px 20px;display:none;flex-direction:column;gap:16px;overflow-y:auto}\n.survey-body.active{display:flex}\n.chat-body.hidden,.input-row.hidden{display:none}\n\n.step-bar{display:flex;align-items:center;margin-bottom:4px}\n.step-num{width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;flex-shrink:0}\n.step-num.done{background:var(--green);color:#fff}\n.step-num.active{background:var(--green);color:#fff;box-shadow:0 0 0 3px rgba(13,124,102,.18)}\n.step-num.todo{background:var(--bg2);color:var(--text3);border:0.5px solid var(--border2)}\n.step-lbl{font-size:11px;margin-left:6px;color:var(--text3)}\n.step-lbl.active{color:var(--green);font-weight:500}\n.step-line{flex:1;height:1.5px;margin:0 6px;border-radius:1px;background:var(--border)}\n.step-line.done{background:var(--green)}\n\n.survey-title{font-size:16px;font-weight:500;margin-bottom:2px}\n.survey-sub{font-size:12px;color:var(--text2);margin-bottom:8px;line-height:1.6}\n\n.budget-display{text-align:center;padding:14px 0}\n.budget-range{font-size:24px;font-weight:500;color:var(--green);letter-spacing:-.02em}\n.budget-count{font-size:11px;color:var(--text3);margin-top:3px}\n.budget-count.warn{color:var(--red);font-weight:500}\n.budget-inputs{display:flex;gap:10px;align-items:center}\n.budget-field{flex:1}\n.budget-field label{font-size:11px;color:var(--text2);display:block;margin-bottom:4px}\n.budget-field input{width:100%;height:40px;border-radius:9px;border:0.5px solid var(--border2);background:var(--bg2);font-size:14px;padding:0 12px;color:var(--text);font-family:inherit;outline:none}\n.budget-field input:focus{border-color:var(--green)}\n\n.amenity-group{margin-bottom:4px}\n.amenity-group-title{font-size:12px;font-weight:500;color:var(--text2);margin-bottom:6px}\n.amenity-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:6px}\n.amenity-chip{display:flex;align-items:center;gap:7px;padding:8px 11px;border-radius:9px;border:0.5px solid var(--border2);background:var(--bg2);font-size:12px;cursor:pointer;transition:all .15s}\n.amenity-chip.selected{background:var(--green-bg);border-color:rgba(13,124,102,.4);color:var(--green-text)}\n.amenity-chip input{display:none}\n.amenity-check{width:16px;height:16px;border-radius:4px;border:1.5px solid var(--border2);flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:10px}\n.amenity-chip.selected .amenity-check{background:var(--green);border-color:var(--green);color:#fff}\n\n.freetext-input{width:100%;min-height:60px;border-radius:9px;border:0.5px solid var(--border2);background:var(--bg2);font-size:13px;padding:10px 12px;color:var(--text);font-family:inherit;outline:none;resize:vertical}\n.freetext-input:focus{border-color:var(--green)}\n\n.survey-nav{display:flex;gap:8px;margin-top:8px}\n.survey-btn{flex:1;padding:11px;border-radius:10px;border:0.5px solid var(--border2);background:transparent;color:var(--text);font-size:13px;font-weight:500;cursor:pointer;font-family:inherit;transition:all .15s}\n.survey-btn.primary{background:var(--green);color:#fff;border:none}\n.survey-btn.primary:hover{opacity:.9}\n.survey-btn:hover{background:var(--bg2)}\n.survey-btn:disabled{opacity:.4;cursor:not-allowed}\n\n.results-header{background:var(--green-bg);border:0.5px solid rgba(13,124,102,.2);border-radius:var(--radius-sm);padding:10px 13px;font-size:12px;color:var(--green-text);line-height:1.6;margin-bottom:6px}\n\n/* Expander / accordion panels */\n.panel-group{display:flex;flex-direction:column;gap:6px;margin-top:4px}\n.expander{border:0.5px solid var(--border);border-radius:var(--radius-sm);overflow:hidden;background:var(--bg)}\n.expander-head{display:flex;align-items:center;justify-content:space-between;padding:11px 14px;cursor:pointer;font-size:12.5px;font-weight:500;user-select:none}\n.expander-head:hover{background:var(--bg2)}\n.expander-chevron{font-size:10px;color:var(--text3);transition:transform .2s}\n.expander.open .expander-chevron{transform:rotate(90deg)}\n.expander-body{display:none;padding:0 14px 14px;font-size:12px;color:var(--text2);line-height:1.65}\n.expander.open .expander-body{display:block}\n\n/* Suburb insight cards */\n.insight-card{background:var(--bg2);border-radius:var(--radius-sm);padding:11px 13px;margin-bottom:8px}\n.insight-name{font-size:12.5px;font-weight:500;margin-bottom:6px}\n.insight-known{font-size:12px;line-height:1.65;margin-bottom:8px}\n.insight-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:8px}\n.insight-box{background:var(--bg);border-radius:7px;padding:8px 10px;border:0.5px solid var(--border)}\n.insight-lbl{font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--text3);margin-bottom:3px;font-weight:500}\n.insight-val{font-size:11.5px;line-height:1.55}\n.insight-watch{font-size:11.5px;line-height:1.6;padding-top:8px;border-top:0.5px solid var(--border)}\n.insight-watch strong{font-weight:500;color:var(--text)}\n\n/* Calculator grids */\n.calc-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:8px 0}\n.calc-card{background:var(--bg2);border-radius:9px;padding:9px 11px;border:0.5px solid var(--border)}\n.calc-card.wide{grid-column:span 3}\n.calc-name{font-size:11.5px;font-weight:500;margin-bottom:2px}\n.calc-sub{font-size:10px;color:var(--text3);margin-bottom:4px}\n.calc-val{font-size:16px;font-weight:500;color:var(--green);letter-spacing:-.02em}\n.calc-val.warn{color:var(--amber)}\n.calc-val.bad{color:var(--red)}\n.calc-note{font-size:10px;color:var(--text3);margin-top:2px}\n\n.share-pills{display:flex;gap:6px;margin:8px 0}\n.share-pill{flex:1;padding:7px;border-radius:8px;border:0.5px solid var(--border2);background:transparent;font-size:11.5px;cursor:pointer;font-family:inherit;color:var(--text)}\n.share-pill.active{background:var(--green-bg);color:var(--green-text);border-color:rgba(13,124,102,.3);font-weight:500}\n\n.calc-input-row{display:flex;gap:8px;margin-bottom:8px}\n.calc-input{flex:1}\n.calc-input label{font-size:11px;color:var(--text2);display:block;margin-bottom:4px}\n.calc-input input,.calc-input select{width:100%;height:34px;border-radius:8px;border:0.5px solid var(--border2);background:var(--bg2);font-size:12.5px;padding:0 10px;color:var(--text);font-family:inherit;outline:none}\n.calc-input input:focus,.calc-input select:focus{border-color:var(--green)}\n\n.law-note{font-size:11px;color:var(--text3);font-style:italic;margin-top:6px;line-height:1.55}\n\n/* Renter checklist */\n.checklist-item{display:flex;gap:10px;padding:9px 0;border-bottom:0.5px solid var(--border)}\n.checklist-item:last-child{border:none}\n.check-box{width:18px;height:18px;border-radius:5px;border:1.5px solid var(--border2);flex-shrink:0;margin-top:1px;display:flex;align-items:center;justify-content:center;font-size:11px;cursor:pointer;transition:all .15s}\n.check-box.done{background:var(--green);border-color:var(--green);color:#fff}\n.check-title{font-size:12px;font-weight:500;margin-bottom:1px}\n.check-src{font-size:10px;color:var(--text3);font-style:italic;margin-bottom:3px}\n.check-desc{font-size:11.5px;color:var(--text2);line-height:1.6}\n\n.slider-row{display:flex;align-items:center;gap:10px;margin:8px 0}\n.slider-row input[type=range]{flex:1;accent-color:var(--green)}\n.slider-val{font-size:13px;font-weight:500;color:var(--green);min-width:36px;text-align:right}\n\n.bar-row{display:flex;align-items:center;gap:8px;margin-bottom:5px}\n.bar-lbl{font-size:11px;color:var(--text3);min-width:34px}\n.bar-track{flex:1;height:6px;border-radius:3px;background:var(--bg2);overflow:hidden;position:relative}\n.bar-fill{height:100%;border-radius:3px}\n.bar-limit{position:absolute;top:0;height:100%;width:1.5px;background:var(--border2)}\n.bar-pct{font-size:11px;font-weight:500;min-width:32px;text-align:right}\n\n/* Property advisor card */\n.advisor-card{border:0.5px solid var(--border);border-radius:var(--radius);overflow:hidden;background:var(--bg)}\n.advisor-verdict{padding:14px 16px;font-size:14px;font-weight:500;display:flex;align-items:center;gap:10px}\n.advisor-verdict.proceed{background:var(--green-bg);color:var(--green-text)}\n.advisor-verdict.caution{background:var(--amber-bg);color:var(--amber)}\n.advisor-verdict.walk_away{background:rgba(220,38,38,.08);color:var(--red)}\n.advisor-verdict-icon{display:inline-flex;align-items:center}\n.advisor-verdict-icon svg{width:18px;height:18px}\n.advisor-section{padding:13px 16px;border-top:0.5px solid var(--border)}\n.advisor-section-title{font-size:11.5px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px;display:flex;align-items:center;gap:6px}\n.advisor-section.illegal .advisor-section-title{color:var(--red)}\n.advisor-section.watch .advisor-section-title{color:var(--amber)}\n.advisor-section.good .advisor-section-title{color:var(--green-text)}\n.advisor-section.script .advisor-section-title{color:var(--text2)}\n.advisor-list{display:flex;flex-direction:column;gap:7px}\n.advisor-list-item{font-size:12.5px;line-height:1.65;color:var(--text2);display:flex;gap:8px}\n.advisor-list-item .bullet{flex-shrink:0;margin-top:1px}\n.advisor-section.illegal .bullet{color:var(--red)}\n.advisor-section.watch .bullet{color:var(--amber)}\n.advisor-section.good .bullet{color:var(--green-text)}\n</style>\n</head>\n<body>\n<div class="app">\n  <!-- Header -->\n  <div class="header">\n    <div class="header-top">\n      <div class="wordmark">\n        <div class="logo"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg></div>\n        <div>\n          <div class="app-name">Perth Rental Finder</div>\n        </div>\n      </div>\n      <div class="nav">\n        <button class="nav-btn active" id="chat-btn" onclick="setMode(\'chat\')" title="Chat" aria-label="Chat"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg></button>\n        <button class="nav-btn" id="survey-btn-nav" onclick="setMode(\'survey\')" title="Step by step" aria-label="Step by step"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg></button>\n        <button class="nav-btn danger" onclick="clearChat()" title="Clear chat" aria-label="Clear chat"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button>\n        <button class="theme-btn" id="theme-btn" onclick="toggleTheme()" title="Switch light/dark mode" aria-label="Switch light/dark mode"></button>\n      </div>\n    </div>\n  </div>\n\n  <!-- Chat body -->\n  <div class="chat-body" id="chat-body"></div>\n\n  <!-- Survey / Step-by-step body -->\n  <div class="survey-body" id="survey-body">\n\n    <!-- Step bar -->\n    <div class="step-bar" id="survey-step-bar"></div>\n\n    <!-- Step 1: Budget -->\n    <div id="survey-step-1">\n      <div class="survey-title">What\'s your weekly rental budget?</div>\n      <div class="survey-sub">We\'ll show you suburbs that fit, using real bond data.</div>\n      <div class="budget-inputs">\n        <div class="budget-field">\n          <label>Minimum ($/wk)</label>\n          <input type="number" id="survey-min" value="400" step="50" min="100" max="3000" oninput="updateBudgetDisplay()" onchange="updateBudgetDisplay()">\n        </div>\n        <div class="budget-field">\n          <label>Maximum ($/wk)</label>\n          <input type="number" id="survey-max" value="700" step="50" min="100" max="5000" oninput="updateBudgetDisplay()" onchange="updateBudgetDisplay()">\n        </div>\n      </div>\n      <div class="budget-display">\n        <div class="budget-range" id="budget-range-display">$400 – $700/wk</div>\n        <div class="budget-count" id="budget-count-display">Loading suburb count…</div>\n      </div>\n      <div class="survey-nav">\n        <button class="survey-btn primary" id="survey-step1-next" onclick="surveyStep(2)">Next: what matters to you →</button>\n      </div>\n    </div>\n\n    <!-- Step 2: What matters -->\n    <div id="survey-step-2" style="display:none">\n      <div class="survey-title">What matters to you nearby?</div>\n      <div class="survey-sub">Select anything that\'s important and we\'ll prioritise suburbs close to these.</div>\n      <div id="amenity-groups"></div>\n      <div class="amenity-group">\n        <div class="amenity-group-title">Anything else?</div>\n        <textarea class="freetext-input" id="survey-freetext" placeholder="e.g. quiet street, near Fremantle, ground floor…"></textarea>\n      </div>\n      <div class="survey-nav">\n        <button class="survey-btn" onclick="surveyStep(1)">← Back</button>\n        <button class="survey-btn primary" onclick="runSurveySearch()">Find my suburbs</button>\n      </div>\n    </div>\n\n    <!-- Step 3: Results -->\n    <div id="survey-step-3" style="display:none">\n      <div class="survey-title">Your matches</div>\n      <div class="results-header" id="survey-results-header"></div>\n      <div id="survey-results-cards"></div>\n      <div id="survey-results-text" class="agent-prose" style="margin-top:8px"></div>\n      <div id="survey-results-panel" style="margin-top:8px"></div>\n      <div class="survey-nav">\n        <button class="survey-btn" onclick="surveyStep(1)">← Edit my answers</button>\n      </div>\n    </div>\n\n  </div>\n\n  <!-- Input -->\n  <div class="input-row">\n    <button class="mic-btn" id="mic-btn" onclick="toggleMic()" title="Voice input">\n      <svg viewBox="0 0 24 24"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>\n    </button>\n    <input class="chat-input" id="chat-input" placeholder="Ask anything about renting in Perth…"\n           onkeydown="if(event.key===\'Enter\'&&!event.shiftKey){event.preventDefault();send()}">\n    <button class="send-btn" onclick="send()">\n      <svg viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>\n    </button>\n  </div>\n</div>\n\n<script>\nconst API = \'\';\nlet history = [];\nlet budget = {min_r: null, max_r: null};\n\n// ── Conversation persistence ───────────────────────────────────────────────\nfunction saveHistory() {\n  try {\n    // Save both the message history and the full rendered chat HTML\n    localStorage.setItem(\'perth_history\', JSON.stringify(history));\n    const body = document.getElementById(\'chat-body\');\n    if (body) localStorage.setItem(\'perth_chat_html\', body.innerHTML);\n  } catch(e) {}\n}\nfunction renderUserMessage(text) {\n  // Render-only version of addUserMessage. does NOT push to history or save\n  const body = document.getElementById(\'chat-body\');\n  const wrap = document.createElement(\'div\');\n  wrap.className = \'msg user\';\n  wrap.innerHTML = `<div class="bubble user">${text.replace(/\\n/g,\'<br>\')}</div>`;\n  body.appendChild(wrap);\n}\n\nfunction renderAIMessage(text) {\n  // Render-only version of addAIMessage. does NOT push to history or save\n  const wrap = document.createElement(\'div\');\n  wrap.className = \'msg\';\n  wrap.innerHTML = `\n    <div class="av ai"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg></div>\n    <div class="bubble ai">${text.replace(/\\n/g,\'<br>\')}</div>`;\n  document.getElementById(\'chat-body\').appendChild(wrap);\n}\n\nfunction loadHistory() {\n  try {\n    const savedHTML = localStorage.getItem(\'perth_chat_html\');\n    const savedHistory = localStorage.getItem(\'perth_history\');\n    if (savedHTML && savedHistory) {\n      history = JSON.parse(savedHistory);\n      const body = document.getElementById(\'chat-body\');\n      body.innerHTML = savedHTML;\n      // Re-attach any event listeners that were in the restored HTML\n      chatQ.step = 4; // Mark questionnaire as done so free-form chat works\n      scrollBottom();\n      return true;\n    }\n  } catch(e) { console.warn(\'loadHistory error:\', e); }\n  return false;\n}\nfunction clearHistory() {\n  try {\n    localStorage.removeItem(\'perth_history\');\n    localStorage.removeItem(\'perth_chat_html\');\n  } catch(e) {}\n}\n\n// ── Conversational questionnaire state ────────────────────────────────────\nlet chatQ = { step: 0, min_r: null, max_r: null, area: \'\', amenities: [] };\n\nconst Q_AREA_OPTIONS = [\n  \'Inner city / north of river\',\'South of river\',\'Northern suburbs\',\'Southern suburbs\',\n  \'Near the beach\',\'Near Fremantle\',\'Eastern suburbs\',\'No preference\'\n];\nconst Q_PRIORITY_OPTIONS = [\n  {label:\'🚆 Train station\',value:\'Train station\'},\n  {label:\'🚌 Bus routes\',value:\'Bus routes\'},\n  {label:\'🏫 Primary school\',value:\'Primary school\'},\n  {label:\'🎓 High school\',value:\'High school\'},\n  {label:\'🌊 Near the beach\',value:\'Near the beach\'},\n  {label:\'🌳 Parks / green space\',value:\'Parks and green space\'},\n  {label:\'🏥 Hospital nearby\',value:\'Hospital\'},\n  {label:\'🛒 Shopping centre\',value:\'Shopping centre\'},\n  {label:\'☕ Cafes & restaurants\',value:\'Cafes and restaurants\'},\n  {label:\'🐶 Dog-friendly\',value:\'Dog-friendly areas\'},\n];\nlet rec = null, listening = false, finalText = \'\', interimText = \'\';\n// Cached perth-stats response, fetched once at load. The header panel that\n// used to display these numbers (and that makeMarketStrip() previously\n// copied its values FROM) has been removed, so this is now the one real\n// source of live rent-stat data for anything in the page that still needs\n// it, rather than each spot fetching independently or silently falling\n// back to stale hardcoded numbers.\nlet perthStatsCache = null;\nasync function loadPerthStatsCache() {\n  try {\n    const r = await fetch(\'/api/perth-stats\');\n    perthStatsCache = await r.json();\n  } catch(e) { perthStatsCache = null; }\n}\n\n// ── Theme toggle ──────────────────────────────────────────────────────────────\n// Defaults to OS preference (handled by the @media rule in CSS when no\n// data-theme attribute is set at all). A manual choice is stored so it\n// persists across visits and overrides the OS default from then on.\nfunction applyStoredTheme() {\n  try {\n    const saved = localStorage.getItem(\'theme\');\n    if (saved === \'light\' || saved === \'dark\') {\n      document.documentElement.setAttribute(\'data-theme\', saved);\n    }\n  } catch(e) {}\n  updateThemeIcon();\n}\nfunction currentTheme() {\n  const attr = document.documentElement.getAttribute(\'data-theme\');\n  if (attr === \'light\' || attr === \'dark\') return attr;\n  return matchMedia(\'(prefers-color-scheme: dark)\').matches ? \'dark\' : \'light\';\n}\nconst SUN_ICON = \'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>\';\nconst MOON_ICON = \'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>\';\nfunction updateThemeIcon() {\n  const btn = document.getElementById(\'theme-btn\');\n  if (btn) btn.innerHTML = currentTheme() === \'dark\' ? SUN_ICON : MOON_ICON;\n}\nfunction toggleTheme() {\n  const next = currentTheme() === \'dark\' ? \'light\' : \'dark\';\n  document.documentElement.setAttribute(\'data-theme\', next);\n  try { localStorage.setItem(\'theme\', next); } catch(e) {}\n  updateThemeIcon();\n}\napplyStoredTheme();\n\n// ── Init ──────────────────────────────────────────────────────────────────────\nwindow.onload = async () => {\n  loadPerthStatsCache();\n  if (!loadHistory()) startQuestionnaire();\n};\n\nfunction startQuestionnaire() {\n  chatQ = { step: 1, min_r: null, max_r: null, area: \'\', amenities: [] };\n  addAIMessage("Hi! I\\\'ll help you find the best Perth suburb for your budget and lifestyle. Just a couple of quick questions.\\n\\nWhat\\\'s your weekly rental budget? You can type a number like $600/wk, or a range like $500–$650/wk. (These are whole-property rents. Use the sharehouse calculator in results to split costs.)");\n}\n\nfunction renderQuickReplies(options, multi, onDone) {\n  // single-select toggle with Next button, or multi-select with Find button\n  const body = document.getElementById(\'chat-body\');\n  const wrap = document.createElement(\'div\');\n  wrap.className = \'qr-wrap\'; wrap.id = \'qr-active\';\n  let selected = [];\n  let submitCol = null;\n  const btnText = multi ? \'Find my suburbs →\' : \'Next →\';\n  const noteText = multi ? \'Pick as many as you like, then tap Find.\' : \'Tap your choice, then tap Next.\';\n  options.forEach(opt => {\n    const label = typeof opt===\'object\' ? opt.label : opt;\n    const value = typeof opt===\'object\' ? opt.value : opt;\n    const chip = document.createElement(\'button\');\n    chip.className = \'qr-chip multi\';\n    chip.textContent = label;\n    chip.onclick = () => {\n      if (!multi) {\n        wrap.querySelectorAll(\'.qr-chip\').forEach(c => c.classList.remove(\'selected\'));\n        selected = [value];\n        chip.classList.add(\'selected\');\n      } else {\n        const idx = selected.indexOf(value);\n        if (idx >= 0) { selected.splice(idx,1); chip.classList.remove(\'selected\'); }\n        else { selected.push(value); chip.classList.add(\'selected\'); }\n      }\n      if (submitCol) submitCol.querySelector(\'.qr-submit\').classList.toggle(\'ready\', selected.length > 0);\n    };\n    wrap.appendChild(chip);\n  });\n  body.appendChild(wrap);\n  submitCol = document.createElement(\'div\');\n  submitCol.style.cssText = \'display:flex;flex-direction:column;gap:4px;margin-top:8px;max-width:83%\';\n  const btn = document.createElement(\'button\');\n  btn.className = \'qr-submit\'; btn.textContent = btnText;\n  btn.onclick = () => {\n    if (!selected.length) return;\n    wrap.remove(); submitCol.remove();\n    const labels = selected.map(v => { const m = options.find(o=>(typeof o===\'object\'?o.value:o)===v); return typeof m===\'object\'?m.label:m; });\n    addUserMessage(labels.join(\', \'));\n    onDone(selected);\n  };\n  const note = document.createElement(\'div\');\n  note.className = \'qr-note\'; note.textContent = noteText;\n  submitCol.appendChild(btn); submitCol.appendChild(note);\n  body.appendChild(submitCol);\n  wrap._submitCol = submitCol;\n  scrollBottom();\n}\n\nfunction removeActiveQR() {\n  const el = document.getElementById(\'qr-active\');\n  if (el) { if (el._submitCol) el._submitCol.remove(); el.remove(); }\n}\n\nasync function advanceQuestionnaire(userInput) {\n  removeActiveQR();\n  // Save user input to history (chip selections arrive as arrays, text as string)\n  const userText = Array.isArray(userInput) ? userInput.join(\', \') : userInput;\n  if (chatQ.step >= 1 && chatQ.step <= 3) {\n    history.push({role:\'user\', content:userText});\n    saveHistory();\n  }\n  if (chatQ.step === 1) {\n    const nums = [...(userInput.matchAll ? userInput.matchAll(/\\d{3,5}/g) : [])].map(m=>parseInt(m[0])).filter(n=>n>100&&n<20000);\n    if (nums.length >= 2) { chatQ.min_r=Math.min(...nums); chatQ.max_r=Math.max(...nums); }\n    else if (nums.length === 1) { chatQ.min_r=Math.max(nums[0]-50,100); chatQ.max_r=nums[0]+50; }\n    else { addAIMessage("I didn\\\'t quite catch that. Try something like $600/wk or $500–$650/wk."); return; }\n    // Validate against real data range\n    if (chatQ.max_r < 250) {\n      addAIMessage("That\\\'s below Perth\\\'s rental floor. The most affordable suburbs start around $380–$420/wk. Try a budget of at least $380/wk.");\n      return;\n    }\n    if (chatQ.min_r > 1274) {\n      addAIMessage("Our data covers Perth\\\'s rental market, backed by 470,254 WA government bond records. The highest rent in our dataset is $1,274/wk. $" + chatQ.min_r + "/wk sits outside what bond records capture.\\n\\nFor this budget, REIWA.com.au or a specialist agent like Acton or Abode Property would be better placed to help.");\n      chatQ.step = 0;\n      return;\n    }\n    if (chatQ.max_r > 1274) {\n      chatQ.max_r = 1274;\n      addAIMessage("We\\\'ve capped the upper end at $1,274/wk, the highest rent in our dataset. Searching within that range now.");\n    }\n    chatQ.step = 2;\n    addAIMessage(\'Got it: $\'+chatQ.min_r+\'–$\'+chatQ.max_r+\'/wk. Which part of Perth are you looking in?\');\n    renderQuickReplies(Q_AREA_OPTIONS, false, vals => advanceQuestionnaire(vals));\n  } else if (chatQ.step === 2) {\n    chatQ.area = Array.isArray(userInput) ? userInput[0] : userInput;\n    chatQ.step = 3;\n    addAIMessage(\'Good. What matters most to you nearby? Pick as many as you like, then tap Find.\');\n    renderQuickReplies(Q_PRIORITY_OPTIONS, true, vals => advanceQuestionnaire(vals));\n  } else if (chatQ.step === 3) {\n    chatQ.amenities = Array.isArray(userInput) ? userInput : [];\n    chatQ.step = 4;\n    await runGuidedSearch();\n  }\n}\n\nasync function runGuidedSearch() {\n  const typing = addTyping();\n  try {\n    const areaMap = {\n      \'Inner city / north of river\':\'near CBD north of river\',\n      \'South of river\':\'south of river\',\'Northern suburbs\':\'northern suburbs\',\n      \'Southern suburbs\':\'southern suburbs\',\'Near the beach\':\'near the beach coastal\',\n      \'Near Fremantle\':\'near Fremantle\',\'Eastern suburbs\':\'eastern suburbs\',\'No preference\':\'\',\n    };\n    const areaRegionFilter = {\n      \'Inner city / north of river\':\'north\',\'South of river\':\'south\',\n      \'Northern suburbs\':\'north\',\'Southern suburbs\':\'south\',\'Near the beach\':\'\',\n      \'Near Fremantle\':\'south\',\'Eastern suburbs\':\'east\',\'No preference\':\'\',\n    };\n    const freetext = areaMap[chatQ.area] || chatQ.area;\n    const regionFilter = areaRegionFilter[chatQ.area] || \'\';\n    const resp = await fetch(\'/api/survey-search\', {\n      method:\'POST\', headers:{\'Content-Type\':\'application/json\'},\n      body: JSON.stringify({min_r:chatQ.min_r, max_r:chatQ.max_r, amenities:chatQ.amenities, freetext, region_filter:regionFilter})\n    });\n    const d = await resp.json();\n    typing.remove();\n    if (d.min_r) budget = {min_r:d.min_r, max_r:d.max_r};\n    renderResponse({workflow:\'search\', cards:d.cards, also_cards:d.also_cards, text:d.text});\n    setTimeout(() => addAIMessage(\'You can keep chatting from here. Ask me to dive deeper into any suburb, compare two, or anything else about renting in Perth.\'), 400);\n  } catch(e) {\n    typing.remove();\n    addAIMessage(\'Something went wrong searching. Try typing your search directly.\');\n  }\n}\n\n// ── Send message ───────────────────────────────────────────────────────────────\nasync function send(text) {\n  const input = document.getElementById(\'chat-input\');\n  const msg = text || input.value.trim();\n  if (!msg) return;\n  input.value = \'\';\n\n  if (chatQ.step >= 1 && chatQ.step <= 3) {\n    addUserMessage(msg);\n    advanceQuestionnaire(msg);\n    return;\n  }\n\n  // Quick budget sanity check for free-form messages\n  const _budgetMatch = msg.match(/\\$?\\s*(\\d{3,5})\\s*(?:\\/wk|pw|per week|a week)?/i);\n  if (_budgetMatch) {\n    const _bval = parseInt(_budgetMatch[1]);\n    if (_bval > 1274) {\n      addAIMessage("Our data tops out at $1,274/wk. $" + _bval + "/wk is above what bond records capture. For this budget, try REIWA.com.au or a specialist agent like Acton or Abode Property.");\n      return;\n    }\n    if (_bval < 300 && msg.match(/\\b(budget|afford|week|wk|rent|looking|search|find)\\b/i)) {\n      addAIMessage("Perth\\\'s rental floor is around $380–$420/wk. At $" + _bval + "/wk, there are no real Perth metro options. The results would be remote WA towns, not suburbs you\\\'d want to commute from. Try a budget of at least $380/wk.");\n      return;\n    }\n  }\n\n  addUserMessage(msg);\n  // Send the history snapshot from BEFORE this turn. so history[-1] on the\n  // backend is the previous assistant message (e.g. a budget question),\n  // not this current message. Push to the real history afterwards.\n  const historySnapshot = history.slice();\n  history.push({role:\'user\', content:msg});\n  saveHistory();\n\n  const typing = addTyping();\n\n  try {\n    const r = await fetch(\'/api/chat\', {\n      method:\'POST\',\n      headers:{\'Content-Type\':\'application/json\'},\n      body: JSON.stringify({message:msg, history: historySnapshot, min_r:budget.min_r, max_r:budget.max_r})\n    });\n    const d = await r.json();\n    typing.remove();\n\n    if (d.min_r) budget = {min_r:d.min_r, max_r:d.max_r};\n\n    renderResponse(d);\n  } catch(e) {\n    typing.remove();\n    addAIMessage(`Error: ${e.message}`);\n  }\n}\n\n// ── Render response ───────────────────────────────────────────────────────────\nfunction renderResponse(d) {\n  const wrap = document.createElement(\'div\');\n  wrap.className = \'msg\';\n  const av = document.createElement(\'div\');\n  av.className = \'av ai\';\n  av.innerHTML = \'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>\';\n  const content = document.createElement(\'div\');\n  content.className = \'msg-content\';\n  const lbl = document.createElement(\'div\');\n  lbl.className = \'msg-label\';\n  lbl.textContent = \'Perth Rental Assistant\';\n  content.appendChild(lbl);\n\n  if (d.workflow === \'search\' && d.cards && d.cards.length) {\n    // Compact cards first\n    d.cards.forEach((card, i) => content.appendChild(makeSearchCard(card, i)));\n    if (d.also_cards && d.also_cards.length) {\n      const lbl2 = document.createElement(\'div\');\n      lbl2.className = \'section-label\';\n      lbl2.textContent = \'Also worth considering\';\n      content.appendChild(lbl2);\n      d.also_cards.forEach(card => content.appendChild(makeSearchCard(card, 99)));\n    }\n    // Agent text\n    if (d.text) {\n      const bub = document.createElement(\'div\');\n      bub.className = \'agent-prose\';\n      bub.innerHTML = formatProse(d.text);\n      content.appendChild(bub);\n    }\n    // Market strip\n    content.appendChild(makeMarketStrip());\n    // Renter tools panel (insights, calculators, checklist)\n    content.appendChild(makePanel((d.cards||[]).concat(d.also_cards||[])));\n  } else if (d.workflow === \'deep_dive\') {\n    if (d.card) content.appendChild(makeDiveCard(d.card));\n    if (d.text) {\n      const bub = document.createElement(\'div\');\n      bub.className = \'agent-prose\';\n      bub.innerHTML = formatProse(d.text);\n      content.appendChild(bub);\n    }\n    // Renter tools panel for this one suburb\n    if (d.card) {\n      const panelCard = {name: d.card.name, rent: d.card.rent, insight: d.insight || null};\n      content.appendChild(makePanel([panelCard]));\n    }\n  } else if (d.workflow === \'compare\' && d.cards && d.cards.length) {\n    d.cards.forEach((card, i) => content.appendChild(makeSearchCard(card, i)));\n    if (d.text) {\n      const bub = document.createElement(\'div\');\n      bub.className = \'agent-prose\';\n      bub.innerHTML = formatProse(d.text);\n      content.appendChild(bub);\n    }\n    content.appendChild(makePanel(d.cards));\n  } else if (d.workflow === \'property_advisor\' && d.advisor) {\n    content.appendChild(makeAdvisorCard(d.advisor));\n  } else {\n    const bub = document.createElement(\'div\');\n    bub.className = \'bub ai\';\n    bub.innerHTML = formatProse(d.text || \'\');\n    content.appendChild(bub);\n  }\n\n  wrap.appendChild(av);\n  wrap.appendChild(content);\n  document.getElementById(\'chat-body\').appendChild(wrap);\n  scrollBottom();\n  saveHistory();\n}\n\n// ── Card builders ──────────────────────────────────────────────────────────────\nfunction makeSearchCard(card, i) {\n  const el = document.createElement(\'div\');\n  el.className = \'suburb-card\' + (i===0?\' best\':\'\');\n\n  const top = `\n    <div class="sc-top">\n      <div>\n        <div class="sc-name">${card.name}</div>\n        <div class="sc-sub">${card.notes}</div>\n      </div>\n      <div class="sc-right">\n        <div class="sc-rent">$${Math.round(card.rent)}/wk</div>\n        <div class="rank-pill${i>0?\' second\':\'\'}">${card.rank}</div>\n        ${card.rank_reason ? `<div style="font-size:9.5px;color:var(--text3);margin-top:3px;max-width:140px;line-height:1.3">${card.rank_reason}</div>` : \'\'}\n      </div>\n    </div>`;\n\n  const chips = (card.chips||[]).map(c =>\n    `<span class="chip ${c.color}">${chipIcon(c.icon)} ${c.text}</span>`\n  ).join(\'\');\n\n  const desc = card.desc ? `<div class="sc-desc">${card.desc}</div>` : \'\';\n\n  el.innerHTML = top +\n    `<div class="sc-chips">${chips}</div>` + desc;\n  return el;\n}\n\nfunction makeDiveCard(c) {\n  const el = document.createElement(\'div\');\n  el.className = \'dive-card\';\n\n  const rentRows = [\n    `<div class="dr"><span class="dr-lbl">Typical rent</span><div class="dr-right">${c.hist_note?`<span class="dr-hist">${c.hist_note}</span>`:\'\'}\n      <span class="dr-val green">$${Math.round(c.rent)}/wk</span></div></div>`,\n    c.rent2 ? `<div class="dr"><span class="dr-lbl">2-bedroom</span><span class="dr-val">$${Math.round(c.rent2)}/wk</span></div>` : \'\',\n    c.rent3 ? `<div class="dr"><span class="dr-lbl">3-bedroom</span><span class="dr-val">$${Math.round(c.rent3)}/wk</span></div>` : \'\',\n    `<div class="dr"><span class="dr-lbl">Rent trend</span><span class="dr-val" style="color:${c.trend_color}">${c.trend_txt}</span></div>`,\n    c.br ? `<div class="dr"><span class="dr-lbl">Tenants kept bond</span><span class="dr-val" style="color:${c.br_color}">${c.br}% (${c.br_label})</span></div>` : \'\',\n    c.tenure ? `<div class="dr"><span class="dr-lbl">How long people stay</span><span class="dr-val">${c.tenure} avg</span></div>` : \'\',\n  ].filter(Boolean).join(\'\');\n\n  const chipRows = [\n    c.train_text ? `<div class="cr"><div class="cr-icon green">${CHIP_ICONS.train}</div><span class="cr-text">${c.train_text}</span></div>` : \'\',\n    c.school_text ? `<div class="cr"><div class="cr-icon blue">${CHIP_ICONS.school}</div><span class="cr-text">${c.school_text}</span></div>` : \'\',\n    `<div class="cr"><div class="cr-icon amber">${CHIP_ICONS.shield}</div><span class="cr-text">Crime level for this area</span><span class="cr-badge" style="background:${c.sc_color}18;color:${c.sc_color}">${c.sc_label}</span></div>`,\n  ].filter(Boolean).join(\'\');\n\n  const tnColor = c.trend_color==="#0D7C66"?"green":c.trend_color==="#E05252"?"red":"amber";\n\n  el.innerHTML = `\n    <div class="dive-name">${c.name}</div>\n    <div class="dive-sub">Postcode ${c.postcode} · real WA government bond data</div>\n    <div class="data-rows">${rentRows}</div>\n    <div class="chip-rows">${chipRows}</div>\n    <div class="trend-note ${tnColor}">${c.trend_txt}: ${c.trend_note}. Check <a href="https://reiwa.com.au" target="_blank" style="color:inherit">reiwa.com.au</a> for current listings.</div>`;\n  return el;\n}\n\nfunction makeAdvisorCard(a) {\n  const el = document.createElement(\'div\');\n  el.className = \'advisor-card\';\n\n  const VERDICT_SVG = {\n    proceed: CHIP_ICONS.green,\n    caution: \'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4"/><path d="M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L14.7 3.86a2 2 0 0 0-3.4 0z"/><circle cx="12" cy="16.5" r=".6" fill="currentColor" stroke="none"/></svg>\',\n    walk_away: CHIP_ICONS.red,\n  };\n  const verdictIcon = VERDICT_SVG[a.verdict] || VERDICT_SVG.caution;\n  const verdictLabel = {proceed:\'Proceed\', caution:\'Proceed with caution\', walk_away:\'Walk away\'}[a.verdict] || \'Proceed with caution\';\n\n  let html = `<div class="advisor-verdict ${a.verdict || \'caution\'}">\n    <span class="advisor-verdict-icon">${verdictIcon}</span>\n    <div><strong>${verdictLabel}.</strong> ${a.verdict_text || \'\'}</div>\n  </div>`;\n\n  const ICON_BAN = \'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" width="13" height="13" style="vertical-align:-2px;margin-right:4px"><circle cx="12" cy="12" r="9"/><line x1="5.5" y1="5.5" x2="18.5" y2="18.5"/></svg>\';\n  const ICON_WARN = \'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" width="13" height="13" style="vertical-align:-2px;margin-right:4px"><path d="M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L14.7 3.86a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13"/><circle cx="12" cy="16.5" r=".5" fill="currentColor" stroke="none"/></svg>\';\n  const ICON_CHECK = \'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" width="13" height="13" style="vertical-align:-2px;margin-right:4px"><polyline points="20 6 9 17 4 12"/></svg>\';\n  const ICON_CHAT = \'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" width="13" height="13" style="vertical-align:-2px;margin-right:4px"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>\';\n\n  if (a.illegal && a.illegal.length) {\n    html += `<div class="advisor-section illegal">\n      <div class="advisor-section-title">${ICON_BAN}Illegal, raise this</div>\n      <div class="advisor-list">${a.illegal.map(t => `<div class="advisor-list-item"><span class="bullet">●</span><span>${t}</span></div>`).join(\'\')}</div>\n    </div>`;\n  }\n  if (a.watch_out && a.watch_out.length) {\n    html += `<div class="advisor-section watch">\n      <div class="advisor-section-title">${ICON_WARN}Watch out</div>\n      <div class="advisor-list">${a.watch_out.map(t => `<div class="advisor-list-item"><span class="bullet">●</span><span>${t}</span></div>`).join(\'\')}</div>\n    </div>`;\n  }\n  if (a.good_signs && a.good_signs.length) {\n    html += `<div class="advisor-section good">\n      <div class="advisor-section-title">${ICON_CHECK}Good signs</div>\n      <div class="advisor-list">${a.good_signs.map(t => `<div class="advisor-list-item"><span class="bullet">●</span><span>${t}</span></div>`).join(\'\')}</div>\n    </div>`;\n  }\n  if (a.script) {\n    html += `<div class="advisor-section script">\n      <div class="advisor-section-title">${ICON_CHAT}What to say to the agent</div>\n      <div class="script-box">${a.script}</div>\n    </div>`;\n  }\n\n  el.innerHTML = html;\n  return el;\n}\n\nfunction makeMarketStrip() {\n  const el = document.createElement(\'div\');\n  el.className = \'market-strip\';\n  el.innerHTML = `\n    <div class="market-grid">\n      <div class="market-cell"><div class="market-n" id="ms-rent">$700/wk</div><div class="market-l">Perth typical rent</div></div>\n      <div class="market-cell"><div class="market-n" id="ms-pct">+37%</div><div class="market-l">Since March 2023</div></div>\n      <div class="market-cell"><div class="market-n">32%</div><div class="market-l">Of avg income on rent</div></div>\n      <div class="market-cell"><div class="market-n" style="color:var(--green)">Good</div><div class="market-l">Time to search</div></div>\n    </div>\n    <div class="market-note">Perth is the least affordable capital city in Australia for renters. Based on 470,254 real WA government bond records.</div>`;\n  // Pull live values from the perthStatsCache fetched once at page load\n  // (replaces the old approach of copying from the now-removed header\n  // panel\'s DOM elements). Falls back to the static placeholder text above\n  // if the fetch hasn\'t completed yet or failed, rather than showing\n  // nothing or throwing.\n  if (perthStatsCache) {\n    if (perthStatsCache.lr) el.querySelector(\'#ms-rent\').textContent = `$${perthStatsCache.lr}/wk`;\n    if (perthStatsCache.pct) el.querySelector(\'#ms-pct\').textContent = `+${perthStatsCache.pct}%`;\n  }\n  return el;\n}\n\n// ── Helpers ───────────────────────────────────────────────────────────────────\nconst CHIP_ICONS = {\n  train: \'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="3" width="16" height="13" rx="3"/><path d="M4 11h16"/><path d="M9 16l-2 4"/><path d="M15 16l2 4"/><circle cx="8.5" cy="13.5" r=".6" fill="currentColor" stroke="none"/><circle cx="15.5" cy="13.5" r=".6" fill="currentColor" stroke="none"/></svg>\',\n  school: \'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2 8l10 5 8-4.4V15"/><path d="M6 10.5V16c0 1.5 2.7 3 6 3s6-1.5 6-3v-5.5"/></svg>\',\n  shield: \'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2 4 5v6c0 5 3.4 8.7 8 11 4.6-2.3 8-6 8-11V5z"/></svg>\',\n  dollar: \'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="2" x2="12" y2="22"/><path d="M17 6.5c0-1.9-2.2-3-5-3s-5 1.1-5 3 2.2 2.6 5 3 5 1.1 5 3-2.2 3-5 3-5-1.1-5-3"/></svg>\',\n  green: \'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>\',\n  red: \'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="13"/><circle cx="12" cy="16" r=".6" fill="currentColor" stroke="none"/></svg>\',\n  amber: \'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="13"/><circle cx="12" cy="16" r=".6" fill="currentColor" stroke="none"/></svg>\',\n};\nfunction chipIcon(icon) {\n  return CHIP_ICONS[icon] || \'\';\n}\n\nfunction formatProse(text) {\n  if (!text) return \'\';\n  // Convert **bold** to <strong>\n  text = text.replace(/\\*\\*(.+?)\\*\\*/g, \'<strong>$1</strong>\');\n  // Convert newlines to paragraphs\n  const paras = text.split(/\\n\\n+/).filter(p => p.trim());\n  if (paras.length <= 1) return `<p>${text.replace(/\\n/g,\'<br>\')}</p>`;\n  return paras.map(p => `<p style="margin-bottom:8px">${p.replace(/\\n/g,\'<br>\')}</p>`).join(\'\');\n}\n\nfunction addUserMessage(text) {\n  const wrap = document.createElement(\'div\');\n  wrap.className = \'msg u\';\n  wrap.innerHTML = `\n    <div class="av u"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></div>\n    <div class="msg-content">\n      <div class="msg-label u">You</div>\n      <div class="bub u">${text}</div>\n    </div>`;\n  document.getElementById(\'chat-body\').appendChild(wrap);\n  scrollBottom();\n}\n\nfunction addAIMessage(text) {\n  if (text && text.length > 0) {\n    history.push({role:\'assistant\', content:text});\n    saveHistory();\n  }\n  const wrap = document.createElement(\'div\');\n  wrap.className = \'msg\';\n  wrap.innerHTML = `\n    <div class="av ai"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg></div>\n    <div class="msg-content">\n      <div class="bub ai">${formatProse(text)}</div>\n    </div>`;\n  document.getElementById(\'chat-body\').appendChild(wrap);\n  scrollBottom();\n}\n\nfunction addTyping() {\n  const wrap = document.createElement(\'div\');\n  wrap.className = \'msg\';\n  wrap.innerHTML = `\n    <div class="av ai"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg></div>\n    <div class="typing"><span></span><span></span><span></span></div>`;\n  document.getElementById(\'chat-body\').appendChild(wrap);\n  scrollBottom();\n  return wrap;\n}\n\nfunction scrollBottom() {\n  const body = document.getElementById(\'chat-body\');\n  body.scrollTop = body.scrollHeight;\n}\n\nfunction clearChat() {\n  history = [];\n  budget = {min_r:null, max_r:null};\n\n  // Reset chat\n  document.getElementById(\'chat-body\').innerHTML = \'\';\n  clearHistory();\n  startQuestionnaire();\n\n  // Reset survey state completely\n  surveyState.step = 1;\n  surveyState.amenities = [];\n  const minInput = document.getElementById(\'survey-min\');\n  const maxInput = document.getElementById(\'survey-max\');\n  if (minInput) minInput.value = 400;\n  if (maxInput) maxInput.value = 700;\n  if (document.getElementById(\'survey-freetext\')) document.getElementById(\'survey-freetext\').value = \'\';\n  document.getElementById(\'survey-results-cards\').innerHTML = \'\';\n  document.getElementById(\'survey-results-text\').innerHTML = \'\';\n  document.getElementById(\'survey-results-header\').textContent = \'\';\n  document.getElementById(\'survey-results-panel\').innerHTML = \'\';\n  for (let i = 1; i <= 3; i++) {\n    document.getElementById(`survey-step-${i}`).style.display = (i === 1) ? \'block\' : \'none\';\n  }\n  renderAmenityGroups();\n\n  // Always switch back to chat view\n  setMode(\'chat\');\n}\n\nlet surveyState = { step: 1, amenities: [] };\nlet AMENITY_GROUPS = {};\n\nfunction setMode(m) {\n  const chatBody = document.getElementById(\'chat-body\');\n  const surveyBody = document.getElementById(\'survey-body\');\n  const inputRow = document.querySelector(\'.input-row\');\n  const chatBtn = document.getElementById(\'chat-btn\');\n  const surveyBtn = document.getElementById(\'survey-btn-nav\');\n\n  if (m === \'survey\') {\n    chatBody.classList.add(\'hidden\');\n    inputRow.classList.add(\'hidden\');\n    surveyBody.classList.add(\'active\');\n    chatBtn.classList.remove(\'active\');\n    surveyBtn.classList.add(\'active\');\n    initSurvey();\n  } else {\n    chatBody.classList.remove(\'hidden\');\n    inputRow.classList.remove(\'hidden\');\n    surveyBody.classList.remove(\'active\');\n    chatBtn.classList.add(\'active\');\n    surveyBtn.classList.remove(\'active\');\n  }\n}\n\nasync function initSurvey() {\n  if (Object.keys(AMENITY_GROUPS).length === 0) {\n    try {\n      const r = await fetch(\'/api/amenity-groups\');\n      const d = await r.json();\n      AMENITY_GROUPS = d.groups || {};\n      renderAmenityGroups();\n    } catch(e) {}\n  }\n  surveyStep(surveyState.step);\n  updateBudgetDisplay();\n}\n\nfunction renderAmenityGroups() {\n  const el = document.getElementById(\'amenity-groups\');\n  el.innerHTML = Object.entries(AMENITY_GROUPS).map(([group, items]) => `\n    <div class="amenity-group">\n      <div class="amenity-group-title">${group}</div>\n      <div class="amenity-grid">\n        ${items.map(opt => {\n          const selected = surveyState.amenities.includes(opt);\n          const label = opt.replace(\'Near \', \'\');\n          return `<label class="amenity-chip${selected?\' selected\':\'\'}" onclick="toggleAmenity(this, \'${opt.replace(/\'/g,"\\\\\'")}\')">\n            <span class="amenity-check">${selected?\'✓\':\'\'}</span>${label}\n          </label>`;\n        }).join(\'\')}\n      </div>\n    </div>\n  `).join(\'\');\n}\n\nfunction toggleAmenity(el, opt) {\n  const idx = surveyState.amenities.indexOf(opt);\n  if (idx >= 0) surveyState.amenities.splice(idx, 1);\n  else surveyState.amenities.push(opt);\n  el.classList.toggle(\'selected\');\n  const check = el.querySelector(\'.amenity-check\');\n  check.textContent = el.classList.contains(\'selected\') ? \'✓\' : \'\';\n}\n\nfunction surveyStep(n) {\n  surveyState.step = n;\n  for (let i = 1; i <= 3; i++) {\n    document.getElementById(`survey-step-${i}`).style.display = (i === n) ? \'block\' : \'none\';\n  }\n  renderStepBar(n);\n  if (n === 1) updateBudgetDisplay();\n}\n\nfunction renderStepBar(current) {\n  const labels = [\'Budget\',\'What matters\',\'Results\'];\n  const el = document.getElementById(\'survey-step-bar\');\n  let html = \'\';\n  labels.forEach((lbl, i) => {\n    const num = i + 1;\n    let cls = \'todo\', content = num;\n    if (num < current) { cls = \'done\'; content = \'✓\'; }\n    else if (num === current) { cls = \'active\'; }\n    html += `<div style="display:flex;align-items:center;gap:5px">\n      <div class="step-num ${cls}">${content}</div>\n      <div class="step-lbl ${cls===\'active\'?\'active\':\'\'}">${lbl}</div>\n    </div>`;\n    if (num < labels.length) html += `<div class="step-line ${num<current?\'done\':\'\'}"></div>`;\n  });\n  el.innerHTML = html;\n}\n\nlet budgetCountTimer = null;\nfunction updateBudgetDisplay() {\n  const min_r = parseInt(document.getElementById(\'survey-min\').value) || 0;\n  const max_r = parseInt(document.getElementById(\'survey-max\').value) || 0;\n  document.getElementById(\'budget-range-display\').textContent = `$${min_r.toLocaleString()} – $${max_r.toLocaleString()}/wk`;\n\n  const lbl = document.getElementById(\'budget-count-display\');\n  const nextBtn = document.getElementById(\'survey-step1-next\');\n\n  // Validate: minimum must be less than maximum\n  if (min_r >= max_r) {\n    lbl.textContent = \'Minimum must be less than maximum\';\n    lbl.classList.add(\'warn\');\n    nextBtn.disabled = true;\n    return;\n  }\n  lbl.classList.remove(\'warn\');\n  nextBtn.disabled = false;\n\n  clearTimeout(budgetCountTimer);\n  budgetCountTimer = setTimeout(async () => {\n    try {\n      const r = await fetch(`/api/suburb-count?min_r=${min_r}&max_r=${max_r}`);\n      const d = await r.json();\n      lbl.textContent = `${d.count} suburbs match this range`;\n    } catch(e) {}\n  }, 300);\n}\n\nasync function runSurveySearch() {\n  const min_r = parseInt(document.getElementById(\'survey-min\').value) || 400;\n  const max_r = parseInt(document.getElementById(\'survey-max\').value) || 700;\n  const freetext = document.getElementById(\'survey-freetext\').value;\n\n  surveyStep(3);\n  document.getElementById(\'survey-results-header\').textContent = \'Searching Perth suburbs…\';\n  document.getElementById(\'survey-results-cards\').innerHTML = \'\';\n  document.getElementById(\'survey-results-text\').innerHTML = \'\';\n\n  try {\n    const r = await fetch(\'/api/survey-search\', {\n      method: \'POST\',\n      headers: {\'Content-Type\':\'application/json\'},\n      body: JSON.stringify({min_r, max_r, amenities: surveyState.amenities, freetext})\n    });\n    const d = await r.json();\n\n    document.getElementById(\'survey-results-header\').textContent =\n      `${d.cards.length + (d.also_cards?.length||0)} suburbs found for $${min_r.toLocaleString()}–$${max_r.toLocaleString()}/wk · 470,254 real WA bond records`;\n\n    const cardsEl = document.getElementById(\'survey-results-cards\');\n    cardsEl.innerHTML = \'\';\n    (d.cards || []).forEach((card, i) => cardsEl.appendChild(makeSearchCard(card, i)));\n    if (d.also_cards && d.also_cards.length) {\n      const lbl = document.createElement(\'div\');\n      lbl.className = \'section-label\';\n      lbl.textContent = \'Also worth considering\';\n      cardsEl.appendChild(lbl);\n      d.also_cards.forEach(card => cardsEl.appendChild(makeSearchCard(card, 99)));\n    }\n    document.getElementById(\'survey-results-text\').innerHTML = formatProse(d.text || \'\');\n\n    // Renter tools panel\n    const panelHost = document.getElementById(\'survey-results-panel\');\n    panelHost.innerHTML = \'\';\n    panelHost.appendChild(makePanel((d.cards||[]).concat(d.also_cards||[])));\n  } catch(e) {\n    document.getElementById(\'survey-results-header\').textContent = `Error: ${e.message}`;\n  }\n}\n\n// ── Voice input ───────────────────────────────────────────────────────────────\nfunction toggleMic() {\n  if (!(\'webkitSpeechRecognition\' in window || \'SpeechRecognition\' in window)) {\n    alert(\'Voice input requires Chrome or Edge.\'); return;\n  }\n  if (listening) { stopListening(); return; }\n  startListening();\n}\n\nfunction startListening() {\n  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;\n  rec = new SR(); rec.lang=\'en-AU\'; rec.continuous=true; rec.interimResults=true;\n  rec.onstart = () => {\n    listening=true; finalText=\'\'; interimText=\'\';\n    document.getElementById(\'mic-btn\').classList.add(\'listening\');\n    document.getElementById(\'chat-input\').placeholder=\'Listening, speak now…\';\n  };\n  rec.onresult = e => {\n    interimText=\'\';\n    for(let i=e.resultIndex;i<e.results.length;i++){\n      if(e.results[i].isFinal) finalText+=e.results[i][0].transcript+\' \';\n      else interimText+=e.results[i][0].transcript;\n    }\n    document.getElementById(\'chat-input\').value = (finalText+interimText).trim();\n  };\n  rec.onerror = () => reset();\n  rec.onend = () => { if(listening) rec.start(); };\n  rec.start();\n}\n\nfunction stopListening() {\n  listening=false;\n  if(rec){rec.onend=null;try{rec.stop();}catch(e){}}\n  document.getElementById(\'mic-btn\').classList.remove(\'listening\');\n  document.getElementById(\'chat-input\').placeholder=\'Ask anything about renting in Perth…\';\n  if(finalText.trim()||interimText.trim()) send((finalText+interimText).trim());\n  finalText=\'\'; interimText=\'\';\n}\n\n// ══════════════════════════════════════════════════════════════════════════\n// EXPANDER PANEL. renter tools shown after search results\n// ══════════════════════════════════════════════════════════════════════════\n\nlet panelCounter = 0;\n\nfunction makePanel(cards) {\n  panelCounter++;\n  const pid = panelCounter;\n  const primary = cards[0] || {rent: 600, name: \'this suburb\'};\n\n  const el = document.createElement(\'div\');\n  el.className = \'panel-group\';\n  el.innerHTML = [\n    makeExpander(\'insights-\'+pid, \'What these suburbs are actually like\', insightsHTML(cards)),\n    makeExpander(\'afford-\'+pid, \'What can I actually afford?\', affordHTML(pid, cards)),\n    makeExpander(\'share-\'+pid, \'Splitting the rent?\', shareHTML(pid, cards)),\n    makeExpander(\'moving-\'+pid, \'How much does this cost, upfront and over a year?\', movingHTML(primary.rent)),\n    makeExpander(\'lease-\'+pid, "What does it cost to break my lease? WA law calculator", leaseHTML(pid, primary.rent)),\n    makeExpander(\'scenario-\'+pid, \'What happens to my budget if rent keeps rising?\', scenarioHTML(pid, primary.rent)),\n    makeExpander(\'checklist-\'+pid, \'Before you sign and after you move in: your renter checklist\', checklistHTML(pid)),\n  ].join(\'\');\n\n  // Wire up interactivity after insertion\n  setTimeout(() => {\n    initShareCalc(pid, cards);\n    initAffordCalc(pid, cards);\n    initLeaseCalc(pid, primary.rent);\n    initScenarioCalc(pid, primary.rent);\n  }, 0);\n\n  return el;\n}\n\nfunction makeExpander(id, title, bodyHtml) {\n  return `<div class="expander" id="exp-${id}">\n    <div class="expander-head" onclick="toggleExpander(\'${id}\')">\n      <span>${title}</span>\n      <span class="expander-chevron">▶</span>\n    </div>\n    <div class="expander-body">${bodyHtml}</div>\n  </div>`;\n}\n\nfunction toggleExpander(id) {\n  document.getElementById(\'exp-\'+id).classList.toggle(\'open\');\n}\n\n// ── Suburb insights ──────────────────────────────────────────────────────\nfunction insightsHTML(cards) {\n  let html = \'<div style="font-size:11px;color:var(--text3);margin-bottom:8px">Research-backed profiles combined with real bond data, not marketing copy.</div>\';\n  cards.forEach(c => {\n    if (c.insight) {\n      const i = c.insight;\n      html += `<div class="insight-card">\n        <div class="insight-name">${c.name}</div>\n        <div class="insight-known">${i.known_for}</div>\n        <div class="insight-grid">\n          <div class="insight-box"><div class="insight-lbl">Who lives here</div><div class="insight-val">${i.who}</div></div>\n          <div class="insight-box"><div class="insight-lbl">Good for</div><div class="insight-val">${i.good_for}</div></div>\n        </div>\n        <div class="insight-watch"><strong>Watch out:</strong> ${i.watch_out}</div>\n      </div>`;\n    } else {\n      html += `<div class="insight-card" style="font-style:italic;color:var(--text3);font-size:11.5px">\n        ${c.name}: profile not yet researched. Ask "tell me everything about ${c.name}" for a data-backed profile.\n      </div>`;\n    }\n  });\n  return html;\n}\n\n// ── Affordability calculator ────────────────────────────────────────────\nfunction affordHTML(pid, cards) {\n  return `\n    <div style="font-size:11px;color:var(--text3);margin-bottom:8px">Stays in your browser and is never saved. Enter your salary to see what lands in your account each week after tax.</div>\n    <div class="calc-input-row">\n      <div class="calc-input">\n        <label>My yearly salary (before tax)</label>\n        <input type="number" id="afford-salary-${pid}" placeholder="e.g. 70000" min="0" step="1000">\n      </div>\n    </div>\n    <div id="afford-result-${pid}"></div>\n  `;\n}\n\nfunction calcTakehome(annual) {\n  let tax;\n  if (annual <= 18200) tax = 0;\n  else if (annual <= 45000) tax = (annual-18200)*0.19;\n  else if (annual <= 120000) tax = 5092+(annual-45000)*0.325;\n  else if (annual <= 180000) tax = 29467+(annual-120000)*0.37;\n  else tax = 51667+(annual-180000)*0.45;\n  return Math.round((annual-tax-annual*0.02)/52);\n}\n\nfunction initAffordCalc(pid, cards) {\n  const input = document.getElementById(`afford-salary-${pid}`);\n  if (!input) return;\n  const update = () => {\n    const salary = parseFloat(input.value) || 0;\n    const resultEl = document.getElementById(`afford-result-${pid}`);\n    if (salary <= 0) { resultEl.innerHTML = \'\'; return; }\n    const weekly = calcTakehome(salary);\n    const limit = Math.round(weekly*0.30);\n    const shareLimit = Math.round(weekly*2*0.30);\n\n    let cards3 = `<div class="calc-grid">\n      <div class="calc-card"><div class="calc-name">Weekly take-home</div><div class="calc-val">$${weekly.toLocaleString()}/wk</div></div>\n      <div class="calc-card"><div class="calc-name">Comfortable rent limit (30%)</div><div class="calc-val">$${limit.toLocaleString()}/wk</div></div>\n      <div class="calc-card"><div class="calc-name">If sharing with 1 other</div><div class="calc-val">$${shareLimit.toLocaleString()}/wk</div></div>\n    </div>`;\n\n    let perSuburb = \'<div style="margin-top:10px">\';\n    cards.forEach(c => {\n      const pct = Math.round(c.rent/weekly*100);\n      const cls = pct<=30?\'\':( pct<=38?\'warn\':\'bad\');\n      const verdict = pct<=30?\'Within your comfortable range\':(pct<=38?\'A bit of a stretch\':\'Above your comfortable range\');\n      perSuburb += `<div class="bar-row"><span class="bar-lbl" style="min-width:90px">${c.name}</span>\n        <div class="bar-track"><div class="bar-fill" style="width:${Math.min(pct,100)}%;background:${cls===\'bad\'?\'var(--red)\':cls===\'warn\'?\'var(--amber)\':\'var(--green)\'}"></div>\n        <div class="bar-limit" style="left:${Math.min(30/Math.max(pct,30)*100,100)}%"></div></div>\n        <span class="bar-pct" style="color:${cls===\'bad\'?\'var(--red)\':cls===\'warn\'?\'var(--amber)\':\'var(--green)\'}">${pct}%</span></div>\n        <div style="font-size:10.5px;color:var(--text3);margin:-2px 0 8px 98px">${verdict}</div>`;\n    });\n    perSuburb += \'</div>\';\n\n    resultEl.innerHTML = cards3 + perSuburb;\n  };\n  input.addEventListener(\'input\', update);\n}\n\n// ── Sharehouse calculator ───────────────────────────────────────────────\nfunction shareHTML(pid, cards) {\n  const cardsHtml = cards.map(c =>\n    `<div class="calc-card" id="share-card-${pid}-${c.name.replace(/\\s/g,\'\')}">\n      <div class="calc-name">${c.name}</div>\n      <div class="calc-sub">$${Math.round(c.rent)}/wk total</div>\n      <div class="calc-val" data-rent="${c.rent}">$${Math.round(c.rent/2)}/wk</div>\n      <div class="calc-note">per person</div>\n    </div>`\n  ).join(\'\');\n\n  return `\n    <div style="font-size:11px;color:var(--text3);margin-bottom:8px">These are full property rents, not individual rooms. Split by how many people are sharing.</div>\n    <div class="calc-grid">${cardsHtml}</div>\n    <div class="share-pills">\n      <button class="share-pill" onclick="setSharers(${pid},1,this)">Just me</button>\n      <button class="share-pill active" onclick="setSharers(${pid},2,this)">2 people</button>\n      <button class="share-pill" onclick="setSharers(${pid},3,this)">3 people</button>\n      <button class="share-pill" onclick="setSharers(${pid},4,this)">4 people</button>\n    </div>\n    <div id="share-info-${pid}" style="font-size:11.5px;color:var(--text2);line-height:1.6"></div>\n  `;\n}\n\nfunction initShareCalc(pid, cards) {\n  setSharers(pid, 2, null);\n}\n\nfunction setSharers(pid, n, btn) {\n  const exp = document.getElementById(\'exp-share-\'+pid);\n  if (!exp) return;\n  exp.querySelectorAll(\'.share-pill\').forEach(b => b.classList.remove(\'active\'));\n  if (btn) btn.classList.add(\'active\');\n  else exp.querySelectorAll(\'.share-pill\')[n-1].classList.add(\'active\');\n\n  exp.querySelectorAll(\'.calc-card .calc-val\').forEach(el => {\n    const rent = parseFloat(el.dataset.rent);\n    el.textContent = `$${Math.round(rent/n)}/wk`;\n  });\n\n  const info = {\n    1: "On a single income, many Perth suburbs are a stretch. Sharing doubles what you can afford.",\n    2: "Sharing with one other person opens up significantly more of Perth\'s rental market.",\n    3: "Sharing with 2 others opens up even more options across Perth.",\n    4: "Sharing with 3 others makes almost every Perth suburb affordable."\n  }[n] || "";\n  document.getElementById(`share-info-${pid}`).textContent = info;\n}\n\n// ── Moving costs ─────────────────────────────────────────────────────────\nfunction movingHTML(rent) {\n  const bond = rent*4, advance = rent*2, annual = rent*52, utilities = 2400;\n  const upfrontLow = bond+advance+300, upfrontHigh = bond+advance+900;\n  return `\n    <div style="font-size:11px;color:var(--text3);margin-bottom:8px">Most people think in weekly rent. Here is the full picture based on $${Math.round(rent)}/wk.</div>\n    <div class="calc-grid">\n      <div class="calc-card"><div class="calc-name">Upfront bond</div><div class="calc-val">$${Math.round(bond).toLocaleString()}</div><div class="calc-note">4 weeks rent · returned when you leave</div></div>\n      <div class="calc-card"><div class="calc-name">2 weeks rent in advance</div><div class="calc-val">$${Math.round(advance).toLocaleString()}</div><div class="calc-note">Paid before you get the keys</div></div>\n      <div class="calc-card"><div class="calc-name">Moving truck or van hire</div><div class="calc-val" style="font-size:13px">$300–$600</div><div class="calc-note">Perth removalist, 2-bedroom</div></div>\n      <div class="calc-card wide" style="background:var(--green-bg);border-color:rgba(13,124,102,.2)">\n        <div class="calc-name" style="color:var(--green-text)">Cash you need before moving in</div>\n        <div class="calc-val">$${Math.round(upfrontLow).toLocaleString()} – $${Math.round(upfrontHigh).toLocaleString()}</div>\n      </div>\n      <div class="calc-card"><div class="calc-name">Rent for 12 months</div><div class="calc-val">$${Math.round(annual).toLocaleString()}</div></div>\n      <div class="calc-card"><div class="calc-name">Utilities estimate</div><div class="calc-val">$${utilities.toLocaleString()}</div></div>\n      <div class="calc-card"><div class="calc-name">Total year one cost</div><div class="calc-val">$${Math.round(annual+utilities).toLocaleString()}</div></div>\n    </div>\n  `;\n}\n\n// ── Break lease calculator ──────────────────────────────────────────────\nfunction leaseHTML(pid, rent) {\n  return `\n    <div style="font-size:11px;color:var(--text3);margin-bottom:8px">Based on the WA Residential Tenancies Act 1987.</div>\n    <div class="calc-input-row">\n      <div class="calc-input">\n        <label>Lease type</label>\n        <select id="lease-type-${pid}">\n          <option value="fixed">Fixed term</option>\n          <option value="periodic">Periodic (month to month)</option>\n        </select>\n      </div>\n      <div class="calc-input">\n        <label>Weekly rent ($)</label>\n        <input type="number" id="lease-rent-${pid}" value="${Math.round(rent)}" min="100" step="10">\n      </div>\n    </div>\n    <div class="calc-input-row">\n      <div class="calc-input">\n        <label>Weeks remaining</label>\n        <input type="number" id="lease-remaining-${pid}" value="16" min="0" max="104">\n      </div>\n      <div class="calc-input">\n        <label>Weeks already served</label>\n        <input type="number" id="lease-served-${pid}" value="8" min="0" max="104">\n      </div>\n    </div>\n    <div id="lease-result-${pid}"></div>\n  `;\n}\n\nfunction initLeaseCalc(pid, rent) {\n  const ids = [`lease-type-${pid}`,`lease-rent-${pid}`,`lease-remaining-${pid}`,`lease-served-${pid}`];\n  const els = ids.map(id => document.getElementById(id));\n  if (els.some(e => !e)) return;\n  const update = () => {\n    const type = els[0].value;\n    const r = parseFloat(els[1].value) || 0;\n    const weeksLeft = parseFloat(els[2].value) || 0;\n    const weeksServed = parseFloat(els[3].value) || 0;\n    const resultEl = document.getElementById(`lease-result-${pid}`);\n\n    if (type === \'periodic\') {\n      resultEl.innerHTML = `<div class="calc-card" style="background:var(--green-bg);border-color:rgba(13,124,102,.2)">\n        <div class="calc-name" style="color:var(--green-text)">Your cost: $0</div>\n        <div style="font-size:11.5px;color:var(--green-text);line-height:1.6;margin-top:4px">On a periodic lease you owe nothing beyond your 21-day notice period. Give notice in writing today and your liability ends in 21 days.</div>\n      </div>`;\n      return;\n    }\n\n    const reletFee = Math.round(r);\n    const estVacantWeeks = Math.min(weeksLeft, 5);\n    const vacantCost = Math.round(r * estVacantWeeks);\n    const total = reletFee + vacantCost;\n    const pctServed = Math.round(weeksServed / Math.max(weeksServed+weeksLeft,1) * 100);\n\n    resultEl.innerHTML = `\n      <div class="calc-grid">\n        <div class="calc-card"><div class="calc-name">Maximum exposure</div><div class="calc-val bad">$${total.toLocaleString()}</div><div class="calc-note">worst case</div></div>\n        <div class="calc-card"><div class="calc-name">Reletting fee (capped)</div><div class="calc-val warn">$${reletFee.toLocaleString()}</div><div class="calc-note">1 week rent max (s.62A)</div></div>\n        <div class="calc-card"><div class="calc-name">Lease served</div><div class="calc-val">${pctServed}%</div><div class="calc-note">${weeksServed} of ${weeksServed+weeksLeft} weeks</div></div>\n      </div>\n      <div style="background:var(--amber-bg);border-radius:8px;padding:9px 11px;margin:8px 0;font-size:11.5px;color:var(--amber);line-height:1.6">\n        <strong>Your estimated cost: $${total.toLocaleString()}</strong>, but this is the maximum. The landlord must actively relet the property. If they find a new tenant in 2 weeks, your vacancy cost drops to $${Math.round(r*2).toLocaleString()}.\n      </div>\n      <div class="law-note">✓ Reletting fee capped at 1 week rent (s.62A RTA 1987). ✓ Landlord must actively relet. ✓ You can find your own replacement tenant. ✓ Get any agreement in writing.</div>\n      <div class="script-box" style="margin-top:8px">"I need to vacate before my lease ends and understand I am liable for reasonable break lease costs under s.62A of the RTA 1987. I am willing to assist in finding a replacement tenant to minimise your vacancy period. Can we agree a timeline in writing?"</div>\n    `;\n  };\n  els.forEach(e => e.addEventListener(\'input\', update));\n  els[0].addEventListener(\'change\', update);\n  update();\n}\n\n// ── Rent scenario planner ───────────────────────────────────────────────\nfunction scenarioHTML(pid, rent) {\n  return `\n    <div style="font-size:11px;color:var(--text3);margin-bottom:8px">Perth rents rose 37% between 2023 and 2026. See what different scenarios mean for your budget.</div>\n    <div class="calc-input-row">\n      <div class="calc-input">\n        <label>Current weekly rent ($)</label>\n        <input type="number" id="scenario-rent-${pid}" value="${Math.round(rent)}" min="100" step="10">\n      </div>\n      <div class="calc-input">\n        <label>Your weekly take-home pay ($)</label>\n        <input type="number" id="scenario-income-${pid}" value="1100" min="0" step="50">\n      </div>\n    </div>\n    <label style="font-size:11px;color:var(--text2)">Annual rent increase</label>\n    <div class="slider-row">\n      <input type="range" id="scenario-rate-${pid}" min="0" max="20" value="8" step="1">\n      <span class="slider-val" id="scenario-rate-val-${pid}">8%</span>\n    </div>\n    <div id="scenario-result-${pid}"></div>\n  `;\n}\n\nfunction initScenarioCalc(pid, rent) {\n  const rentEl = document.getElementById(`scenario-rent-${pid}`);\n  const incomeEl = document.getElementById(`scenario-income-${pid}`);\n  const rateEl = document.getElementById(`scenario-rate-${pid}`);\n  if (!rentEl || !incomeEl || !rateEl) return;\n\n  const update = () => {\n    const r = parseFloat(rentEl.value) || 0;\n    const income = parseFloat(incomeEl.value) || 0;\n    const rate = parseFloat(rateEl.value) || 0;\n    document.getElementById(`scenario-rate-val-${pid}`).textContent = rate + \'%\';\n\n    const r1 = Math.round(r*(1+rate/100));\n    const r2 = Math.round(r*Math.pow(1+rate/100,2));\n    const r3 = Math.round(r*Math.pow(1+rate/100,3));\n    const pct = v => income>0 ? Math.round(v/income*100) : 0;\n    const color = p => p<=30?\'var(--green)\':(p<=38?\'var(--amber)\':\'var(--red)\');\n    const verdict = p => p<=30?\'Within your comfortable range\':(p<=38?\'Above the 30% comfort point\':\'Financially straining\');\n\n    const p0=pct(r), p1=pct(r1), p2=pct(r2), p3=pct(r3);\n\n    let cardsHtml = [[1,r1,p1],[2,r2,p2],[3,r3,p3]].map(([yr,rr,p]) =>\n      `<div class="calc-card"><div class="calc-name" style="color:${color(p)}">Year ${yr}</div>\n        <div class="calc-val" style="color:${color(p)}">$${rr}/wk</div>\n        <div class="calc-sub">${p}% of your income</div>\n        <div class="calc-note" style="color:${color(p)}">${verdict(p)}</div></div>`\n    ).join(\'\');\n\n    let barsHtml = \'\';\n    if (income > 0) {\n      const maxPct = Math.max(p0,p1,p2,p3,40);\n      [[\'Now\',p0],[\'Yr 1\',p1],[\'Yr 2\',p2],[\'Yr 3\',p3]].forEach(([lbl,p]) => {\n        barsHtml += `<div class="bar-row"><span class="bar-lbl">${lbl}</span>\n          <div class="bar-track"><div class="bar-fill" style="width:${Math.min(p/maxPct*100,100)}%;background:${color(p)}"></div>\n          <div class="bar-limit" style="left:${Math.min(30/maxPct*100,100)}%"></div></div>\n          <span class="bar-pct" style="color:${color(p)}">${p}%</span></div>`;\n      });\n    }\n\n    const extra3 = r3 - r;\n    const totalExtra = Math.round(((r1-r)+(r2-r)+(r3-r))*52);\n    const perthR3 = Math.round(r*Math.pow(1.11,3));\n\n    document.getElementById(`scenario-result-${pid}`).innerHTML = `\n      <div class="calc-grid">${cardsHtml}</div>\n      ${barsHtml ? `<div style="margin:10px 0"><div style="font-size:10px;color:var(--text3);display:flex;justify-content:space-between;margin-bottom:5px"><span>Rent as % of your income</span><span>← 30% comfort limit</span></div>${barsHtml}</div>` : \'\'}\n      <div class="calc-grid">\n        <div class="calc-card"><div class="calc-name">Extra per week, year 3</div><div class="calc-val bad">+$${extra3}/wk</div></div>\n        <div class="calc-card"><div class="calc-name">Total extra over 3 years</div><div class="calc-val bad">+$${totalExtra.toLocaleString()}</div></div>\n        <div class="calc-card"><div class="calc-name">At Perth\'s ~11%/yr rate</div><div class="calc-val warn">$${perthR3}/wk</div></div>\n      </div>\n      <div class="law-note">Scenario tool, not a prediction. WA law limits rent increases to once per 12 months with 60 days notice (Residential Tenancies Amendment Act 2024).</div>\n    `;\n  };\n  rentEl.addEventListener(\'input\', update);\n  incomeEl.addEventListener(\'input\', update);\n  rateEl.addEventListener(\'input\', update);\n  update();\n}\n\n// ── Renter checklist ─────────────────────────────────────────────────────\nconst CHECKLIST_ITEMS = [\n  ["Inspect the property in person before signing", "s.27, RTA 1987", "Walk through every room. Test taps, flush toilets, check locks, look for mould. If anything is broken, ask for written confirmation it will be fixed before move-in, not a verbal promise."],\n  ["Check and return the condition report within 7 business days", "s.27A, RTA 1987", "The landlord must give you a condition report before or when you move in. Check every item. Add and photograph anything wrong. Return your signed copy within 7 business days."],\n  ["Take date-stamped photos and video on move-in day", "Best practice, protects your bond", "Photograph every room, every wall, every appliance, inside cupboards and under sinks. Date-stamped photos are your best protection if the landlord claims bond money for pre-existing damage."],\n  ["Confirm the bond is within the legal limit", "s.32, RTA 1987", "Maximum bond is 4 weeks rent, no more. If asked for more, refuse in writing and contact Consumer Protection WA."],\n  ["Verify your Bond Reference Number within 3 weeks", "s.32(2), RTA 1987", "Landlords must lodge your bond with the WA Bond Administrator within 14 days. You will receive a Bond Reference Number, so keep it."],\n  ["Read every line of the lease before you sign", "RTA 1987", "Check: weekly rent, lease dates, break-lease conditions, pet rules, who pays which utilities, and any special conditions. Once signed you are legally bound."],\n  ["Know your repair rights", "s.43, RTA 1987", "Urgent repairs (burst pipes, no hot water, broken heating, security issues) must be fixed within 24 hours. Always report repairs in writing."],\n  ["Understand the 2024 rent increase rules", "s.30, RTA 1987 amended July 2024", "Since 29 July 2024, landlords can only increase rent once every 12 months and must give 60 days written notice."],\n  ["Know your rights when leaving", "s.62, RTA 1987", "On a periodic lease give at least 21 days written notice. If you break a fixed-term lease early you may owe compensation, but the landlord must try to find a new tenant."],\n  ["Where to get free confidential help", "Consumer Protection WA · Tenancy WA", "Consumer Protection WA: commerce.wa.gov.au/consumer-protection. Tenancy WA: tenancywa.org.au, free legal advice for renters."],\n];\n\nfunction checklistHTML(pid) {\n  return `<div style="font-size:11px;color:var(--text3);margin-bottom:4px">Based on the WA Residential Tenancies Act 1987. Tick each one as you go.</div>` +\n    CHECKLIST_ITEMS.map((item, i) => `\n      <div class="checklist-item">\n        <div class="check-box" id="chk-${pid}-${i}" onclick="toggleCheck(${pid},${i})"></div>\n        <div>\n          <div class="check-title">${item[0]}</div>\n          <div class="check-src">${item[1]}</div>\n          <div class="check-desc">${item[2]}</div>\n        </div>\n      </div>`).join(\'\');\n}\n\nfunction toggleCheck(pid, i) {\n  const el = document.getElementById(`chk-${pid}-${i}`);\n  el.classList.toggle(\'done\');\n  el.textContent = el.classList.contains(\'done\') ? \'✓\' : \'\';\n}\n</script>\n</body>\n</html>\n'
DASHBOARD_HTML = '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>Perth Rental Market: Dashboard</title>\n<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&display=swap" rel="stylesheet">\n<style>\n*{box-sizing:border-box;margin:0;padding:0}\n:root{\n  --bg:#ffffff;--bg2:#f5f5f4;--bg3:#f0efed;\n  --ink:#181614;--ink2:#5a5650;--ink3:#9a958c;\n  --paper:#f7f4ee;--paper2:#efe9dd;\n  --text:#1a1a1a;--text2:#6b7280;--text3:#9ca3af;\n  --border:#e5e5e3;--border2:#d1d0ce;\n  --green:#0D7C66;--green-bg:#e8f5f1;--green-text:#065F46;\n  --amber:#B45309;--amber-bg:#fef3c7;\n  --red:#B91C1C;--red-bg:#fee2e2;\n  --blue:#1D4ED8;--blue-bg:#eff6ff;\n  --radius:12px;--radius-sm:8px;\n  --serif:\'Fraunces\',ui-serif,Georgia,serif;\n  font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',system-ui,sans-serif;\n}\n@media(prefers-color-scheme:dark){\n  :root{\n    --bg:#1c1c1e;--bg2:#2c2c2e;--bg3:#3a3a3c;\n    --ink:#f0eee9;--ink2:#b8b3a8;--ink3:#7a766e;\n    --paper:#211f1c;--paper2:#2a2723;\n    --text:#f5f5f5;--text2:#aeaeb2;--text3:#636366;\n    --border:#3a3a3c;--border2:#48484a;\n    --green-bg:#0a3326;--green-text:#4ade80;\n    --amber-bg:#3d2800;--red-bg:#3d0f0f;--blue-bg:#0c1a3d;\n  }\n}\nbody{background:var(--bg3);color:var(--text);min-height:100vh}\n.wrap{max-width:1080px;margin:0 auto;padding:0 24px 60px}\n\n.top{display:flex;align-items:center;justify-content:space-between;padding:24px 0 18px;flex-wrap:wrap;gap:12px}\n.brand{display:flex;align-items:center;gap:10px}\n.logo{width:32px;height:32px;border-radius:9px;background:var(--green);display:flex;align-items:center;justify-content:center;color:#fff;font-size:16px;flex-shrink:0}\n.brand-name{font-size:15px;font-weight:500;letter-spacing:-.01em}\n.brand-sub{font-size:11px;color:var(--text3)}\n.nav-link{font-size:12.5px;color:var(--text2);text-decoration:none;border:0.5px solid var(--border2);padding:6px 14px;border-radius:20px;transition:all .15s}\n.nav-link:hover{background:var(--bg2)}\n\n/* Tab navigation */\n.tabbar{display:flex;gap:4px;border-bottom:1px solid var(--border);margin-bottom:32px;overflow-x:auto}\n.tab{font-size:13.5px;font-weight:500;color:var(--text2);background:none;border:none;padding:10px 16px;cursor:pointer;border-bottom:2px solid transparent;white-space:nowrap;transition:color .15s,border-color .15s;font-family:inherit}\n.tab:hover{color:var(--text)}\n.tab.active{color:var(--green-text);border-bottom-color:var(--green)}\n.page{display:none}\n.page.active{display:block}\n\n/* Hero */\n.hero{background:var(--paper);border-radius:20px;padding:48px 44px;margin-bottom:36px;position:relative;overflow:hidden}\n.hero-eyebrow{font-size:11.5px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:var(--ink3);margin-bottom:18px}\n.hero-stat{font-family:var(--serif);font-weight:500;font-size:88px;line-height:0.95;letter-spacing:-.02em;color:var(--ink);font-optical-sizing:auto}\n.hero-stat .unit{font-size:34px;color:var(--ink2);font-weight:400}\n.hero-claim{font-family:var(--serif);font-size:26px;font-weight:500;line-height:1.25;color:var(--ink);margin:14px 0 18px;max-width:600px}\n.hero-facts{display:flex;gap:28px;flex-wrap:wrap;margin-top:24px;padding-top:22px;border-top:1px solid var(--paper2)}\n.hero-fact{max-width:220px}\n.hero-fact-n{font-family:var(--serif);font-size:24px;font-weight:500;color:var(--green-text);letter-spacing:-.01em}\n.hero-fact-l{font-size:12px;color:var(--ink2);margin-top:2px;line-height:1.45}\n\nh2.section-title{font-family:var(--serif);font-size:22px;font-weight:500;letter-spacing:-.01em;color:var(--ink)}\n.section-deck{font-size:13.5px;color:var(--text2);line-height:1.6;max-width:560px;margin-top:4px}\n\n.section{margin-bottom:40px}\n.section-head{margin-bottom:18px}\n.section-note{font-size:11.5px;color:var(--text3);margin-top:6px}\n\n.card{background:var(--bg);border:0.5px solid var(--border);border-radius:var(--radius);padding:18px 20px}\n\n.chart-card{position:relative;height:280px}\n.chart-card.tall{height:340px}\n.chart-card.feature{height:360px;padding:28px 24px}\n\n.region-table{width:100%;font-size:13px;border-collapse:collapse}\n.region-table th{text-align:left;font-size:11px;color:var(--text3);font-weight:500;padding:0 12px 8px 0;border-bottom:0.5px solid var(--border)}\n.region-table td{padding:10px 12px 10px 0;border-bottom:0.5px solid var(--border)}\n.region-table tr:last-child td{border-bottom:none}\n.region-table td.num{text-align:right;font-variant-numeric:tabular-nums}\n.bar-cell{display:flex;align-items:center;gap:8px}\n.bar-track{flex:1;height:6px;border-radius:3px;background:var(--bg2);overflow:hidden;max-width:140px}\n.bar-fill{height:100%;border-radius:3px;background:var(--green)}\n.coverage-pct{font-size:11px;color:var(--text3)}\n\n.two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px}\n.list-card{background:var(--bg2);border-radius:var(--radius-sm);padding:14px 16px}\n.list-head{font-size:11.5px;font-weight:500;color:var(--text2);margin-bottom:10px;text-transform:uppercase;letter-spacing:.03em}\n.list-row{display:flex;align-items:center;justify-content:space-between;padding:7px 0;font-size:13px;border-bottom:0.5px solid var(--border)}\n.list-row:last-child{border-bottom:none}\n.list-suburb{font-weight:500}\n.list-region{font-size:11px;color:var(--text3);margin-top:1px}\n.list-rent{font-weight:500;color:var(--green);font-variant-numeric:tabular-nums}\n\n.coverage-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}\n.coverage-item{text-align:center;padding:12px 8px;background:var(--bg2);border-radius:var(--radius-sm)}\n.coverage-n{font-size:18px;font-weight:500;color:var(--green)}\n.coverage-l{font-size:10.5px;color:var(--text3);margin-top:2px;line-height:1.4}\n\n.stress-row{display:flex;align-items:center;gap:12px;padding:9px 0;border-bottom:0.5px solid var(--border)}\n.stress-row:last-child{border-bottom:none}\n.stress-name{flex:0 0 140px;font-size:13px;font-weight:500}\n.stress-track{flex:1;height:8px;border-radius:4px;background:var(--bg2);overflow:hidden;position:relative}\n.stress-fill{height:100%;border-radius:4px}\n.stress-pct{flex:0 0 50px;text-align:right;font-size:13px;font-weight:500;font-variant-numeric:tabular-nums}\n.empty-note{font-size:12.5px;color:var(--text3);padding:8px 0}\n\n.legend-row{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:10px;font-size:11.5px;color:var(--text2)}\n.legend-dot{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px;vertical-align:-1px}\n\n.foot-note{font-size:11.5px;color:var(--text3);line-height:1.6;border-top:0.5px solid var(--border);padding-top:16px;margin-top:8px}\n.foot-note a{color:var(--text2);text-decoration:underline}\n\n@media(max-width:760px){\n  .hero{padding:32px 24px}\n  .hero-stat{font-size:56px}\n  .hero-claim{font-size:20px}\n  .two-col{grid-template-columns:1fr}\n  .coverage-grid{grid-template-columns:repeat(2,1fr)}\n}\n</style>\n</head>\n<body>\n<div class="wrap">\n\n  <div class="top">\n    <div class="brand">\n      <div class="logo">&#127968;</div>\n      <div>\n        <div class="brand-name">Perth Rental Finder</div>\n        <div class="brand-sub">Market overview</div>\n      </div>\n    </div>\n    <div style="display:flex;align-items:center;gap:10px">\n      <select id="region-filter" class="nav-link" style="cursor:pointer;font-family:inherit;-webkit-appearance:none;appearance:none;background-image:url(\'data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2210%22 height=%226%22 viewBox=%220 0 10 6%22><path d=%22M1 1l4 4 4-4%22 stroke=%22%236b7280%22 stroke-width=%221.4%22 fill=%22none%22/></svg>\');background-repeat:no-repeat;background-position:right 12px center;padding-right:30px">\n        <option value="">All regions</option>\n      </select>\n      <a class="nav-link" href="/">&larr; Back to chat</a>\n    </div>\n  </div>\n\n  <div class="hero">\n    <div class="hero-eyebrow" id="hero-eyebrow">470,254 real WA government bond records &middot; March 2023 &ndash; May 2026</div>\n    <div class="hero-stat" id="hero-stat">$700<span class="unit">/wk</span></div>\n    <div class="hero-claim" id="hero-claim">Perth is now the least affordable capital city in Australia for renters &mdash; and the gap is still widening.</div>\n    <div class="hero-facts">\n      <div class="hero-fact"><div class="hero-fact-n" id="hero-pct">+37%</div><div class="hero-fact-l" id="hero-pct-label">Median rent since March 2023</div></div>\n      <div class="hero-fact"><div class="hero-fact-n" id="hero-yoy">&hellip;</div><div class="hero-fact-l" id="hero-yoy-label">Year-on-year change, median of suburbs with 12+ months of history</div></div>\n      <div class="hero-fact"><div class="hero-fact-n">16 days</div><div class="hero-fact-l">Median time a Perth rental stays listed before being leased</div></div>\n      <div class="hero-fact"><div class="hero-fact-n" id="hero-suburbs">&hellip;</div><div class="hero-fact-l" id="hero-suburbs-label">Suburbs in this dataset, from inner Perth to regional WA</div></div>\n    </div>\n  </div>\n\n  <!-- Tab navigation: persistent across page switches, current page always\n       highlighted, consistent placement -- the region filter above applies\n       to every tab\'s content, so switching tabs never resets or ignores\n       the active filter (the specific usability problem this rebuild\n       exists to fix). -->\n  <div class="tabbar" role="tablist" aria-label="Dashboard sections">\n    <button class="tab active" role="tab" aria-selected="true" data-page="overview">Overview</button>\n    <button class="tab" role="tab" aria-selected="false" data-page="regional">Regional</button>\n    <button class="tab" role="tab" aria-selected="false" data-page="affordability">Affordability</button>\n    <button class="tab" role="tab" aria-selected="false" data-page="safety">Safety</button>\n  </div>\n\n\n  <div class="page active" data-page="overview">\n  <div class="section">\n    <div class="section-head">\n      <h2 class="section-title">Most of Perth has already crossed the comfort line</h2>\n      <div class="section-deck">Spending more than 30% of income on rent is the standard measure of housing stress. Here\'s where every suburb in this dataset sits against Perth\'s median rent, all at once. Click a bar to see which suburbs are in that range.</div>\n    </div>\n    <div class="card chart-card feature">\n      <canvas id="distChart" role="img" aria-label="Bar chart of suburb count by weekly rent bucket">Most suburbs cluster between $500 and $800 per week.</canvas>\n    </div>\n    <div class="card" id="bucket-detail" style="display:none;margin-top:12px">\n      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">\n        <div class="list-head" id="bucket-detail-title" style="margin-bottom:0">Suburbs</div>\n        <button id="bucket-detail-close" style="background:none;border:none;cursor:pointer;color:var(--text3);font-size:12px;text-decoration:underline">close</button>\n      </div>\n      <div id="bucket-detail-list"></div>\n    </div>\n  </div>\n\n  <div class="section">\n    <div class="section-head">\n      <h2 class="section-title">The climb since 2023</h2>\n      <div class="section-deck">Perth-wide median weekly rent, month by month, since the start of this dataset.</div>\n    </div>\n    <div class="card chart-card">\n      <canvas id="trendChart" role="img" aria-label="Line chart of Perth median weekly rent from March 2023 to May 2026">Median rent rose from $510/wk to $700/wk over the period.</canvas>\n    </div>\n  </div>\n  </div>\n\n  <div class="page" data-page="regional">\n  <div class="section">\n    <div class="section-head">\n      <h2 class="section-title">No two corners of Perth are rising the same way</h2>\n      <div class="section-deck">Median of each suburb\'s most recent reported rent, grouped by region.</div>\n    </div>\n    <div class="card">\n      <table class="region-table" id="region-table">\n        <thead><tr><th>Region</th><th>Suburbs</th><th>Coverage</th><th style="text-align:right">Median rent</th></tr></thead>\n        <tbody></tbody>\n      </table>\n    </div>\n  </div>\n\n  <div class="section">\n    <div class="section-head">\n      <h2 class="section-title">The extremes, right now</h2>\n      <div class="section-deck">By most recent reported median rent.</div>\n    </div>\n    <div class="two-col">\n      <div class="list-card">\n        <div class="list-head">Cheapest</div>\n        <div id="cheapest-list"></div>\n      </div>\n      <div class="list-card">\n        <div class="list-head">Priciest</div>\n        <div id="priciest-list"></div>\n      </div>\n    </div>\n  </div>\n\n  <div class="section">\n    <div class="section-head">\n      <h2 class="section-title">Suburbs are pulling apart, not together</h2>\n      <div class="section-deck">Full-period percentage change, limited to suburbs with at least 3 months of reported history.</div>\n    </div>\n    <div class="two-col">\n      <div class="list-card">\n        <div class="list-head">Rising fastest</div>\n        <div id="risers-list"></div>\n      </div>\n      <div class="list-card">\n        <div class="list-head">Falling fastest</div>\n        <div id="fallers-list"></div>\n      </div>\n    </div>\n  </div>\n  </div>\n\n  <div class="page" data-page="affordability">\n  <div class="section" id="stress-section">\n    <div class="section-head">\n      <h2 class="section-title">Who\'s actually being squeezed</h2>\n      <div class="section-deck" id="stress-note">Rent as a share of typical local income, for suburbs where that\'s measured directly rather than estimated.</div>\n    </div>\n    <div class="card">\n      <div id="stress-list"></div>\n    </div>\n  </div>\n\n  <div class="section" id="scatter-section">\n    <div class="section-head">\n      <h2 class="section-title">Higher income doesn\'t always mean higher rent</h2>\n      <div class="section-deck" id="scatter-note">Each point is one suburb with both a measured rent and income figure.</div>\n    </div>\n    <div class="card chart-card">\n      <canvas id="scatterChart" role="img" aria-label="Scatter plot of weekly rent against typical local annual income, one point per suburb">Suburbs with higher local income tend to have higher rent, but not in every case.</canvas>\n    </div>\n  </div>\n  </div>\n\n  <div class="page" data-page="safety">\n  <div class="section" id="crime-section">\n    <div class="section-head">\n      <h2 class="section-title">Safety isn\'t one number</h2>\n      <div class="section-deck">Reported incidents by category and police district &mdash; the underlying figures behind the single safety score shown in the chat app.</div>\n    </div>\n    <div class="card chart-card tall">\n      <canvas id="crimeChart" role="img" aria-label="Stacked bar chart of reported burglary, vehicle theft, assault, and property damage incidents by police district">Property damage and burglary are typically the largest categories across districts.</canvas>\n    </div>\n  </div>\n  </div>\n\n  <div class="section">\n    <div class="section-head">\n      <h2 class="section-title">What\'s actually behind these numbers</h2>\n      <div class="section-deck">Coverage varies by field &mdash; here\'s exactly how much.</div>\n    </div>\n    <div class="card">\n      <div class="coverage-grid" id="coverage-grid"></div>\n      <div class="foot-note">\n        Every suburb shown here has at least one real reported rent figure. A smaller set additionally has\n        a detailed affordability profile (2&ndash;3 bedroom rent split, tenancy duration, ATO income, SEIFA decile) &mdash;\n        that\'s a genuine difference in what the source data contains, not a limitation of this dashboard.\n        The rental stress, income comparison, and crime sections above are scoped to whichever suburbs actually\n        have that underlying data &mdash; they are not Perth-wide rankings. See <a href="https://github.com">DATA_QUALITY.md</a>\n        in the project repo for the full methodology, including how estimated values are flagged and never presented as measured.\n      </div>\n    </div>\n  </div>\n\n</div>\n\n<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>\n<script>\nconst isDark = matchMedia(\'(prefers-color-scheme: dark)\').matches;\nconst GREEN = \'#0D7C66\';\nconst GREEN_LIGHT = \'rgba(13,124,102,0.12)\';\nconst GRID = isDark ? \'rgba(255,255,255,0.08)\' : \'rgba(0,0,0,0.06)\';\nconst TICK = isDark ? \'#aeaeb2\' : \'#6b7280\';\n\nfunction fmtMoney(v){ return \'$\' + Math.round(v).toLocaleString(); }\n\nlet dashboardRegionsPopulated = false;\n// Tracks the live Chart.js instance for each canvas, so loadDashboard()\n// can destroy the previous chart before creating a new one. Without this,\n// calling new Chart() on a canvas that already has a chart on it silently\n// fails to render -- which is exactly why selecting a different region\n// updated the hero stats (plain text, no such issue) but every chart kept\n// showing the original, unfiltered data regardless of which region was\n// selected.\nconst liveCharts = { trend: null, dist: null, scatter: null, crime: null };\nfunction destroyChart(key) {\n  if (liveCharts[key]) {\n    liveCharts[key].destroy();\n    liveCharts[key] = null;\n  }\n}\n\nasync function loadDashboard(region) {\n  let d;\n  try {\n    const url = region ? `/api/dashboard?region=${encodeURIComponent(region)}` : \'/api/dashboard\';\n    const r = await fetch(url);\n    d = await r.json();\n  } catch(e) {\n    document.querySelector(\'.wrap\').innerHTML = \'<p style="padding:40px;color:var(--text2)">Could not load dashboard data. Is the warehouse built?</p>\';\n    return;\n  }\n  if (!d || !d.coverage) {\n    document.querySelector(\'.wrap\').innerHTML = \'<p style="padding:40px;color:var(--text2)">Dashboard data is not available yet &mdash; the warehouse build steps may not have been run.</p>\';\n    return;\n  }\n\n  // Reset the per-page chart instance lists at the start of every load\n  // (including region changes), since the actual Chart instances are about\n  // to be destroyed and recreated below -- stale references here would\n  // make tab-switch resize() calls target charts that no longer exist.\n  // Safe to reference directly: loadDashboard() is only ever CALLED (not\n  // just defined) after chartInstancesByPage\'s own declaration has run,\n  // since the script executes top-to-bottom once and the only call sites\n  // are the tab click handlers and the final loadDashboard() at the\n  // bottom of the script, both of which come after the const declaration.\n  Object.keys(chartInstancesByPage).forEach(k => { chartInstancesByPage[k] = []; });\n\n  // Populate the region filter dropdown once, from the real distinct\n  // region list the backend returns (not hardcoded), so it can never drift\n  // out of sync with what\'s actually in the warehouse.\n  if (!dashboardRegionsPopulated && d.all_regions) {\n    const sel = document.getElementById(\'region-filter\');\n    d.all_regions.forEach(r => {\n      const opt = document.createElement(\'option\');\n      opt.value = r; opt.textContent = r;\n      if (r === d.current_region) opt.selected = true;\n      sel.appendChild(opt);\n    });\n    sel.addEventListener(\'change\', () => loadDashboard(sel.value || null));\n    dashboardRegionsPopulated = true;\n  }\n\n  // Hero stats -- text adjusts honestly depending on whether a region\n  // filter is active, rather than always implying a Perth-wide figure.\n  const scopeLabel = d.current_region ? d.current_region : \'Perth-wide\';\n  const firstRent = d.perth_trend[0]?.rent || 0;\n  const lastRent = d.perth_trend[d.perth_trend.length-1]?.rent || 0;\n  const pctChange = firstRent ? Math.round((lastRent/firstRent - 1) * 100) : 0;\n  document.getElementById(\'hero-stat\').innerHTML = fmtMoney(lastRent) + \'<span class="unit">/wk</span>\';\n  document.getElementById(\'hero-pct\').textContent = (pctChange >= 0 ? \'+\' : \'\') + pctChange + \'%\';\n  document.getElementById(\'hero-pct-label\').textContent = d.current_region\n    ? `Median rent since March 2023, ${scopeLabel}`\n    : \'Median rent since March 2023\';\n  document.getElementById(\'hero-suburbs\').textContent = d.coverage.total_suburbs.toLocaleString();\n  document.getElementById(\'hero-suburbs-label\').textContent = d.current_region\n    ? `Suburbs in ${scopeLabel} with data in this dataset`\n    : \'Suburbs in this dataset, from inner Perth to regional WA\';\n  document.getElementById(\'hero-claim\').textContent = d.current_region\n    ? `Here\'s what the real bond data shows for ${scopeLabel} specifically.`\n    : \'Perth is now the least affordable capital city in Australia for renters \\u2014 and the gap is still widening.\';\n\n  // Year-on-year stat -- a genuine, computed figure (latest reported month\n  // vs the same month 12 back, median across qualifying suburbs), not a\n  // restatement of the since-dataset-start percentage above. Honest about\n  // sample size, and about the case where too few suburbs have a full 12\n  // months of history to compute it at all (e.g. a small region filter).\n  if (d.yoy_pct !== null && d.yoy_pct !== undefined && d.yoy_suburb_count > 0) {\n    document.getElementById(\'hero-yoy\').textContent = (d.yoy_pct >= 0 ? \'+\' : \'\') + d.yoy_pct + \'%\';\n    document.getElementById(\'hero-yoy-label\').textContent =\n      `Year-on-year change, median across ${d.yoy_suburb_count} suburb${d.yoy_suburb_count === 1 ? \'\' : \'s\'} with 12+ months of history`;\n  } else {\n    document.getElementById(\'hero-yoy\').textContent = \'\\u2013\';\n    document.getElementById(\'hero-yoy-label\').textContent = \'Not enough 12-month history in this scope to compute year-on-year change\';\n  }\n\n  // Trend chart\n  destroyChart(\'trend\');\n  const trendChartInstance = new Chart(document.getElementById(\'trendChart\'), {\n    type: \'line\',\n    data: {\n      labels: d.perth_trend.map(p => p.month),\n      datasets: [{\n        data: d.perth_trend.map(p => p.rent),\n        borderColor: GREEN, backgroundColor: GREEN_LIGHT, fill: true,\n        tension: 0.25, pointRadius: 0, borderWidth: 2,\n      }]\n    },\n    options: {\n      responsive: true, maintainAspectRatio: false,\n      plugins: { legend: { display: false } },\n      scales: {\n        x: { grid: { display: false }, ticks: { color: TICK, maxTicksLimit: 8, font: { size: 11 } } },\n        y: { grid: { color: GRID }, ticks: { color: TICK, callback: v => fmtMoney(v), font: { size: 11 } } }\n      }\n    }\n  });\n  liveCharts.trend = trendChartInstance;\n  chartInstancesByPage.overview.push(trendChartInstance);\n\n  // Region table\n  const maxRegionRent = Math.max(...d.regions.filter(r => r.median_rent).map(r => r.median_rent), 1);\n  document.querySelector(\'#region-table tbody\').innerHTML = d.regions.map(r => {\n    const pct = r.suburb_count ? Math.round(r.with_rent / r.suburb_count * 100) : 0;\n    const barPct = r.median_rent ? Math.round(r.median_rent / maxRegionRent * 100) : 0;\n    return `<tr>\n      <td>${r.region}</td>\n      <td class="num">${r.suburb_count}</td>\n      <td><span class="coverage-pct">${pct}% with rent data</span></td>\n      <td class="num"><div class="bar-cell" style="justify-content:flex-end">\n        <div class="bar-track"><div class="bar-fill" style="width:${barPct}%"></div></div>\n        ${r.median_rent ? fmtMoney(r.median_rent) + \'/wk\' : \'&ndash;\'}\n      </div></td>\n    </tr>`;\n  }).join(\'\');\n\n  // Distribution chart (the lead visual - slightly richer treatment:\n  // value labels on each bar, since exact counts matter here and Chart.js\n  // doesn\'t show them by default without the datalabels plugin)\n  destroyChart(\'dist\');\n  const distChart = new Chart(document.getElementById(\'distChart\'), {\n    type: \'bar\',\n    data: {\n      labels: d.distribution.map(b => b.bucket),\n      datasets: [{ data: d.distribution.map(b => b.n), backgroundColor: GREEN, borderRadius: 6, maxBarThickness: 64 }]\n    },\n    options: {\n      responsive: true, maintainAspectRatio: false,\n      layout: { padding: { top: 24 } },\n      plugins: { legend: { display: false } },\n      onHover: (evt, els) => { evt.native.target.style.cursor = els.length ? \'pointer\' : \'default\'; },\n      onClick: (evt, els) => {\n        if (!els.length) return;\n        const bucket = d.distribution[els[0].index].bucket;\n        loadBucketDetail(bucket, d.current_region);\n      },\n      scales: {\n        x: { grid: { display: false }, ticks: { color: TICK, font: { size: 12 } } },\n        y: { grid: { color: GRID }, ticks: { color: TICK, precision: 0, font: { size: 11 } } }\n      }\n    },\n    plugins: [{\n      id: \'barValueLabels\',\n      afterDatasetsDraw(chart) {\n        const { ctx } = chart;\n        chart.getDatasetMeta(0).data.forEach((bar, i) => {\n          const val = chart.data.datasets[0].data[i];\n          if (!val) return;\n          ctx.save();\n          ctx.fillStyle = TICK;\n          ctx.font = \'500 12px -apple-system, BlinkMacSystemFont, sans-serif\';\n          ctx.textAlign = \'center\';\n          ctx.fillText(val, bar.x, bar.y - 8);\n          ctx.restore();\n        });\n      }\n    }]\n  });\n  liveCharts.dist = distChart;\n  chartInstancesByPage.overview.push(distChart);\n\n  // Cheapest / priciest lists\n  const listRow = s => `<div class="list-row">\n    <div><div class="list-suburb">${s.suburb}</div><div class="list-region">${s.region}</div></div>\n    <div class="list-rent">${fmtMoney(s.rent)}/wk</div>\n  </div>`;\n  document.getElementById(\'cheapest-list\').innerHTML = d.cheapest.map(listRow).join(\'\');\n  document.getElementById(\'priciest-list\').innerHTML = d.priciest.map(listRow).join(\'\');\n\n  // Risers / fallers\n  const moverRow = s => `<div class="list-row">\n    <div><div class="list-suburb">${s.suburb}</div><div class="list-region">${s.region}</div></div>\n    <div class="list-rent" style="color:${s.pct >= 0 ? GREEN : \'#B91C1C\'}">${s.pct >= 0 ? \'+\' : \'\'}${s.pct}%</div>\n  </div>`;\n  const movers = d.movers || { risers: [], fallers: [] };\n  document.getElementById(\'risers-list\').innerHTML = movers.risers.length\n    ? movers.risers.map(moverRow).join(\'\')\n    : \'<div class="empty-note">Not enough suburbs with sufficient history yet.</div>\';\n  document.getElementById(\'fallers-list\').innerHTML = movers.fallers.length\n    ? movers.fallers.map(moverRow).join(\'\')\n    : \'<div class="empty-note">Not enough suburbs with sufficient history yet.</div>\';\n\n  // Rental stress ranking (scoped to suburbs with a measured rent_to_income_ratio)\n  const stress = d.rental_stress || [];\n  document.getElementById(\'stress-note\').textContent =\n    `Rent as a share of typical local income \\u2014 measured for ${stress.length} suburb${stress.length === 1 ? \'\' : \'s\'} with full affordability data`;\n  if (stress.length) {\n    const maxRatio = Math.max(...stress.map(s => s.ratio_pct), 1);\n    document.getElementById(\'stress-list\').innerHTML = stress.map(s => {\n      const color = s.ratio_pct >= 50 ? \'#B91C1C\' : (s.ratio_pct >= 35 ? \'#B45309\' : GREEN);\n      const width = Math.min(Math.round(s.ratio_pct / maxRatio * 100), 100);\n      return `<div class="stress-row">\n        <div class="stress-name">${s.suburb}</div>\n        <div class="stress-track"><div class="stress-fill" style="width:${width}%;background:${color}"></div></div>\n        <div class="stress-pct" style="color:${color}">${s.ratio_pct}%</div>\n      </div>`;\n    }).join(\'\');\n  } else {\n    document.getElementById(\'stress-list\').innerHTML = \'<div class="empty-note">No suburbs with measured income-to-rent data in this build.</div>\';\n  }\n\n  // Affordability scatter (same scope as above, made visible via point count)\n  const scatter = d.affordability_scatter || [];\n  document.getElementById(\'scatter-note\').textContent =\n    `${scatter.length} suburb${scatter.length === 1 ? \'\' : \'s\'} with both a measured rent and income figure`;\n  const scatterCard = document.getElementById(\'scatter-section\').querySelector(\'.chart-card\');\n  if (scatter.length) {\n    // Restore the canvas if a previous empty-state replaced it (see else\n    // branch below) -- otherwise document.getElementById(\'scatterChart\')\n    // would return null here and `new Chart(null, ...)` would throw.\n    if (!document.getElementById(\'scatterChart\')) {\n      scatterCard.innerHTML = \'<canvas id="scatterChart" role="img" aria-label="Scatter plot of weekly rent against typical local annual income, one point per suburb"></canvas>\';\n    }\n    destroyChart(\'scatter\');\n    const scatterChartInstance = new Chart(document.getElementById(\'scatterChart\'), {\n      type: \'scatter\',\n      data: {\n        datasets: [{\n          data: scatter.map(s => ({ x: s.income, y: s.rent, suburb: s.suburb })),\n          backgroundColor: GREEN, pointRadius: 5, pointHoverRadius: 7,\n        }]\n      },\n      options: {\n        responsive: true, maintainAspectRatio: false,\n        plugins: {\n          legend: { display: false },\n          tooltip: { callbacks: { label: ctx => `${ctx.raw.suburb}: ${fmtMoney(ctx.raw.y)}/wk, $${ctx.raw.x.toLocaleString()}/yr income` } }\n        },\n        scales: {\n          x: { title: { display: true, text: \'Typical local annual income\', color: TICK, font: { size: 11 } },\n               grid: { color: GRID }, ticks: { color: TICK, callback: v => \'$\' + (v/1000) + \'k\', font: { size: 11 } } },\n          y: { title: { display: true, text: \'Weekly rent\', color: TICK, font: { size: 11 } },\n               grid: { color: GRID }, ticks: { color: TICK, callback: v => fmtMoney(v), font: { size: 11 } } }\n        }\n      }\n    });\n    liveCharts.scatter = scatterChartInstance;\n    chartInstancesByPage.affordability.push(scatterChartInstance);\n  } else {\n    destroyChart(\'scatter\');\n    scatterCard.innerHTML =\n      \'<div class="empty-note" style="padding:20px">No suburbs with both a measured rent and income figure in this build.</div>\';\n  }\n\n  // Crime by type (district-level, stacked bar)\n  const crime = d.crime_by_district || [];\n  const crimeCard = document.getElementById(\'crime-section\').querySelector(\'.chart-card\');\n  // Remove any legend inserted by a previous load -- insertAdjacentHTML\n  // below would otherwise stack a new legend on top of the old one every\n  // time the region filter changes, rather than replacing it.\n  const oldLegend = document.querySelector(\'#crime-section .legend-row\');\n  if (oldLegend) oldLegend.remove();\n  if (crime.length) {\n    const CRIME_COLORS = { burglary: \'#1D4ED8\', vehicle_theft: \'#B45309\', assault: \'#B91C1C\', property_damage: \'#6b7280\' };\n    const crimeLabels = { burglary: \'Burglary\', vehicle_theft: \'Vehicle theft\', assault: \'Assault\', property_damage: \'Property damage\' };\n    if (!document.getElementById(\'crimeChart\')) {\n      crimeCard.innerHTML = \'<canvas id="crimeChart" role="img" aria-label="Stacked bar chart of reported burglary, vehicle theft, assault, and property damage incidents by police district"></canvas>\';\n    }\n    destroyChart(\'crime\');\n    const crimeChartInstance = new Chart(document.getElementById(\'crimeChart\'), {\n      type: \'bar\',\n      data: {\n        labels: crime.map(c => c.district),\n        datasets: Object.keys(crimeLabels).map(key => ({\n          label: crimeLabels[key],\n          data: crime.map(c => c[key]),\n          backgroundColor: CRIME_COLORS[key],\n        }))\n      },\n      options: {\n        responsive: true, maintainAspectRatio: false,\n        plugins: { legend: { display: false } },\n        scales: {\n          x: { stacked: true, grid: { display: false }, ticks: { color: TICK, font: { size: 11 }, autoSkip: false, maxRotation: 30 } },\n          y: { stacked: true, grid: { color: GRID }, ticks: { color: TICK, precision: 0, font: { size: 11 } } }\n        }\n      }\n    });\n    liveCharts.crime = crimeChartInstance;\n    chartInstancesByPage.safety.push(crimeChartInstance);\n    const legendHtml = Object.keys(crimeLabels).map(key =>\n      `<span><span class="legend-dot" style="background:${CRIME_COLORS[key]}"></span>${crimeLabels[key]}</span>`\n    ).join(\'\');\n    document.querySelector(\'#crime-section .card\').insertAdjacentHTML(\'afterbegin\', `<div class="legend-row">${legendHtml}</div>`);\n  } else {\n    destroyChart(\'crime\');\n    crimeCard.innerHTML =\n      \'<div class="empty-note" style="padding:20px">No district-level crime data in this build.</div>\';\n  }\n\n  // Coverage grid\n  const c = d.coverage;\n  const covItems = [\n    { n: c.total_suburbs, l: \'Total suburbs\' },\n    { n: c.with_rent, l: \'With rent history\' },\n    { n: c.with_profile, l: \'With full profile\' },\n    { n: c.with_train, l: \'Near a train station\' },\n    { n: c.with_crime, l: \'With crime data\' },\n  ];\n  document.getElementById(\'coverage-grid\').innerHTML = covItems.map(i =>\n    `<div class="coverage-item"><div class="coverage-n">${i.n.toLocaleString()}</div><div class="coverage-l">${i.l}</div></div>`\n  ).join(\'\');\n}\n\n// Bucket drill-down: clicking a histogram bar fetches the real suburb list\n// for that price band from a dedicated endpoint (the dashboard only ever\n// receives aggregate counts otherwise, not the full suburb list, so this\n// can\'t be done client-side from data already on the page).\nasync function loadBucketDetail(bucket, region) {\n  const panel = document.getElementById(\'bucket-detail\');\n  const title = document.getElementById(\'bucket-detail-title\');\n  const list = document.getElementById(\'bucket-detail-list\');\n  panel.style.display = \'block\';\n  title.textContent = `Suburbs in ${bucket}/wk`;\n  list.innerHTML = \'<div class="empty-note">Loading…</div>\';\n  panel.scrollIntoView({ behavior: \'smooth\', block: \'nearest\' });\n  try {\n    const url = `/api/dashboard/bucket?bucket=${encodeURIComponent(bucket)}` + (region ? `&region=${encodeURIComponent(region)}` : \'\');\n    const r = await fetch(url);\n    const data = await r.json();\n    const suburbs = data.suburbs || [];\n    if (!suburbs.length) {\n      list.innerHTML = \'<div class="empty-note">No suburbs found in this range.</div>\';\n      return;\n    }\n    title.textContent = `${suburbs.length} suburb${suburbs.length === 1 ? \'\' : \'s\'} in ${bucket}/wk${region ? ` \\u2014 ${region}` : \'\'}`;\n    list.innerHTML = suburbs.map(s => `<div class="list-row">\n      <div><div class="list-suburb">${s.suburb}</div><div class="list-region">${s.region}</div></div>\n      <div class="list-rent">${fmtMoney(s.rent)}/wk</div>\n    </div>`).join(\'\');\n  } catch (e) {\n    list.innerHTML = \'<div class="empty-note">Could not load suburbs for this range.</div>\';\n  }\n}\ndocument.getElementById(\'bucket-detail-close\').addEventListener(\'click\', () => {\n  document.getElementById(\'bucket-detail\').style.display = \'none\';\n});\n\n// Tab navigation. Charts are created once during the initial\n// loadDashboard() call, before any page is hidden, so canvas measurement\n// at creation time is correct -- but Chart.js doesn\'t automatically know\n// to redraw when its container goes from display:none back to visible\n// (a well-known Chart.js gotcha: a chart inside a hidden container can\n// end up sized 0x0 if it\'s ever told to resize while hidden), so each\n// chart instance is resized explicitly when its page becomes active again.\nconst chartInstancesByPage = { overview: [], regional: [], affordability: [], safety: [] };\ndocument.querySelectorAll(\'.tab\').forEach(tab => {\n  tab.addEventListener(\'click\', () => {\n    const target = tab.dataset.page;\n    document.querySelectorAll(\'.tab\').forEach(t => {\n      t.classList.toggle(\'active\', t === tab);\n      t.setAttribute(\'aria-selected\', t === tab ? \'true\' : \'false\');\n    });\n    document.querySelectorAll(\'.page\').forEach(p => {\n      p.classList.toggle(\'active\', p.dataset.page === target);\n    });\n    (chartInstancesByPage[target] || []).forEach(c => c && c.resize());\n    document.getElementById(\'bucket-detail\').style.display = \'none\';\n  });\n});\n\nloadDashboard();\n</script>\n</body>\n</html>\n'

_cache = {}

# ── Simple per-IP rate limit for /api/chat ──────────────────────────────────
# This app calls the Anthropic API on every chat message, which is billed
# per-token on whatever API key is configured. Since this is deployed
# publicly (a portfolio piece, link shareable with anyone), an unbounded
# endpoint means anyone who finds the URL could drive up real cost on the
# account behind ANTHROPIC_API_KEY. This is a coarse, in-memory limiter -
# fine for Render's free tier (single instance, resets on restart) but NOT
# a substitute for setting a spend limit in the Anthropic Console, which is
# the real backstop against a runaway or malicious cost spike.
_rate_limit_state = {}
RATE_LIMIT_MAX_REQUESTS = 30   # per window, per IP
RATE_LIMIT_WINDOW_SECONDS = 3600  # 1 hour

def _check_rate_limit(client_ip: str) -> bool:
    """Returns True if the request should be allowed, False if rate-limited."""
    now = _dt.datetime.now(_dt.timezone.utc).timestamp()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    timestamps = _rate_limit_state.get(client_ip, [])
    timestamps = [t for t in timestamps if t > window_start]
    if len(timestamps) >= RATE_LIMIT_MAX_REQUESTS:
        _rate_limit_state[client_ip] = timestamps
        return False
    timestamps.append(now)
    _rate_limit_state[client_ip] = timestamps
    return True


def cached(key, fn, ttl=600):
    import time
    now = time.time()
    if key in _cache and now - _cache[key]["t"] < ttl:
        return _cache[key]["v"]
    v = fn()
    _cache[key] = {"v": v, "t": now}
    return v

# ── DATA FUNCTIONS ─────────────────────────────────────────────────────────────
def get_perth_stats():
    if not db: return {}
    try:
        trend = db.query_df("SELECT month,median_rent,p25_rent,p75_rent,new_tenancies FROM perth_monthly_trend ORDER BY month")
        fr=float(trend.iloc[0]["median_rent"]); lr=float(trend.iloc[-1]["median_rent"])
        tb = db.query_one("SELECT COUNT(*) FROM rental_bonds")
        return dict(fr=fr, lr=lr, pct=round((lr/fr-1)*100), trend=trend, total_bonds=max(int(tb),470000))
    except: return {}

# Shared rent-bucket boundaries, used by both the dashboard histogram
# aggregation and the bucket-suburbs lookup endpoint below it -- defined
# once here so the two can never drift apart and disagree about where a
# suburb belongs. (min_inclusive, max_exclusive); max=None means open-ended.
RENT_BUCKETS = [
    ("<$400", 0, 400),
    ("$400-499", 400, 500),
    ("$500-599", 500, 600),
    ("$600-699", 600, 700),
    ("$700-799", 700, 800),
    ("$800-999", 800, 1000),
    ("$1000+", 1000, None),
]
RENT_BUCKET_SQL_CASE = "CASE " + " ".join(
    f"WHEN median_weekly_rent < {hi} THEN '{label}'" for label, lo, hi in RENT_BUCKETS if hi is not None
) + f" ELSE '{RENT_BUCKETS[-1][0]}' END"

def get_dashboard_data(region=None):
    """Aggregates for the market overview dashboard, read from the warehouse
    (dim_suburb / fact_rent_trend / fact_suburb_profile) - same source of
    truth as the chat app, not a separate query path. Returns a dict that's
    JSON-safe (no NaN/pd.NA leaking through) for direct API use.

    region: optional exact region name (e.g. "Perth - southern suburbs") to
    scope every query to. None means Perth-wide / all regions, the default
    and only cached path."""
    if not db: return {}
    try:
        tables = [t for (t,) in db.get_connection().execute("SHOW TABLES").fetchall()]
        if "dim_suburb" not in tables:
            return {}

        # All distinct region names, queried unfiltered regardless of the
        # current region param, both for the filter dropdown and to
        # validate the requested region BEFORE it ever touches a query
        # string. This file has no existing example of db.query_df /
        # query_one accepting a bound-parameters argument, so rather than
        # assume that API exists and risk a TypeError, the requested region
        # is checked against this real, already-known set of values (never
        # arbitrary input) and only then safely inlined - single quotes
        # doubled per standard SQL-literal escaping as defense in depth,
        # even though an allowlisted value should never contain one.
        all_regions_df = db.query_df("SELECT DISTINCT region FROM dim_suburb WHERE region IS NOT NULL ORDER BY region")
        all_regions = [r["region"] for _, r in all_regions_df.iterrows()]
        if region and region not in all_regions:
            region = None  # unknown/invalid region -> fall back to unfiltered, not an error

        def _sql_lit(s):
            return "'" + s.replace("'", "''") + "'"

        region_filter_sql = f"AND d.region = {_sql_lit(region)}" if region else ""

        # Perth-wide (or region-scoped) monthly trend (for the headline chart)
        perth_trend = []
        if region:
            pt = db.query_df(f"""
                SELECT month_key as month, MEDIAN(median_weekly_rent) as median_rent
                FROM fact_rent_trend f JOIN dim_suburb d ON d.suburb_key = f.suburb_key
                WHERE d.region = {_sql_lit(region)}
                GROUP BY month_key ORDER BY month_key
            """)
            perth_trend = [{"month": r["month"], "rent": round(float(r["median_rent"]))} for _, r in pt.iterrows()] if not pt.empty else []
        elif "perth_monthly_trend" in tables:
            pt = db.query_df("SELECT month, median_rent FROM perth_monthly_trend ORDER BY month")
            perth_trend = [{"month": r["month"], "rent": round(float(r["median_rent"]))} for _, r in pt.iterrows()]

        # Year-over-year: latest reported month vs the same month 12 back,
        # computed per-suburb then taking the region's (or Perth-wide)
        # median of those individual changes -- a standard real-estate
        # dashboard metric (alongside month-over-month) that wasn't
        # previously surfaced as its own figure, only implicitly via the
        # "since dataset start" percentage on the hero stat.
        yoy_df = db.query_df(f"""
            WITH ranked AS (
                SELECT f.suburb_key, f.median_weekly_rent, f.month_key,
                       ROW_NUMBER() OVER (PARTITION BY f.suburb_key ORDER BY f.month_key DESC) as rn_desc
                FROM fact_rent_trend f
                JOIN dim_suburb d ON d.suburb_key = f.suburb_key
                WHERE 1=1 {region_filter_sql}
            ),
            latest AS (SELECT suburb_key, median_weekly_rent, month_key FROM ranked WHERE rn_desc = 1),
            year_ago AS (
                SELECT l.suburb_key, f.median_weekly_rent as rent_12mo_ago
                FROM latest l
                JOIN fact_rent_trend f ON f.suburb_key = l.suburb_key
                  AND f.month_key = strftime(strptime(l.month_key || '-01','%Y-%m-%d') - INTERVAL 12 MONTH, '%Y-%m')
            )
            SELECT l.suburb_key, l.median_weekly_rent as latest_rent, y.rent_12mo_ago
            FROM latest l JOIN year_ago y ON y.suburb_key = l.suburb_key
            WHERE y.rent_12mo_ago > 0
        """)
        yoy_pct = None
        yoy_suburb_count = 0
        if not yoy_df.empty:
            yoy_df = yoy_df.copy()
            yoy_df["pct"] = (yoy_df["latest_rent"] / yoy_df["rent_12mo_ago"] - 1) * 100
            yoy_pct = round(float(yoy_df["pct"].median()), 1)
            yoy_suburb_count = len(yoy_df)

        # Region breakdown: suburb count, median of each suburb's latest rent, coverage
        region_df = db.query_df(f"""
            WITH latest_rent AS (
                SELECT suburb_key, median_weekly_rent,
                       ROW_NUMBER() OVER (PARTITION BY suburb_key ORDER BY month_key DESC) as rn
                FROM fact_rent_trend
            )
            SELECT d.region,
                   COUNT(DISTINCT d.suburb_key) as suburb_count,
                   COUNT(DISTINCT lr.suburb_key) as with_rent,
                   MEDIAN(lr.median_weekly_rent) as median_rent
            FROM dim_suburb d
            LEFT JOIN latest_rent lr ON lr.suburb_key = d.suburb_key AND lr.rn = 1
            WHERE 1=1 {region_filter_sql}
            GROUP BY d.region
            ORDER BY median_rent DESC NULLS LAST
        """)
        regions = []
        for _, r in region_df.iterrows():
            regions.append({
                "region": r["region"] if pd.notna(r["region"]) else "Unknown",
                "suburb_count": int(r["suburb_count"]),
                "with_rent": int(r["with_rent"]),
                "median_rent": round(float(r["median_rent"])) if pd.notna(r["median_rent"]) else None,
            })

        # All distinct region names, for the filter dropdown -- queried
        # unfiltered regardless of the current region param, so the
        # dropdown always shows every option, not just the current one.
        all_regions_df = db.query_df("SELECT DISTINCT region FROM dim_suburb WHERE region IS NOT NULL ORDER BY region")
        all_regions = [r["region"] for _, r in all_regions_df.iterrows()]

        # Rent distribution buckets across all suburbs' latest rent (for a histogram)
        dist_df = db.query_df(f"""
            WITH latest_rent AS (
                SELECT f.suburb_key, f.median_weekly_rent,
                       ROW_NUMBER() OVER (PARTITION BY f.suburb_key ORDER BY f.month_key DESC) as rn
                FROM fact_rent_trend f
                JOIN dim_suburb d ON d.suburb_key = f.suburb_key
                WHERE 1=1 {region_filter_sql}
            )
            SELECT {RENT_BUCKET_SQL_CASE} as bucket, COUNT(*) as n
            FROM latest_rent WHERE rn = 1
            GROUP BY bucket
        """)
        bucket_order = [label for label, lo, hi in RENT_BUCKETS]
        dist_map = {r["bucket"]: int(r["n"]) for _, r in dist_df.iterrows()}
        distribution = [{"bucket": b, "n": dist_map.get(b, 0)} for b in bucket_order]

        # Coverage summary (the 26-vs-1,000 story, made visible)
        coverage_where = f"WHERE 1=1 {region_filter_sql}" if region else ""
        coverage = {
            "total_suburbs": int(db.query_one(f"SELECT COUNT(*) FROM dim_suburb d {coverage_where}")),
            "with_rent": int(db.query_one(f"SELECT COUNT(DISTINCT f.suburb_key) FROM fact_rent_trend f JOIN dim_suburb d ON d.suburb_key=f.suburb_key {coverage_where}")) if "fact_rent_trend" in tables else 0,
            "with_profile": int(db.query_one(f"SELECT COUNT(*) FROM fact_suburb_profile p JOIN dim_suburb d ON d.suburb_key=p.suburb_key {coverage_where + (' AND' if coverage_where else 'WHERE')} p.median_rent_2br IS NOT NULL")) if "fact_suburb_profile" in tables else 0,
            "with_income": int(db.query_one(f"SELECT COUNT(*) FROM fact_suburb_profile p JOIN dim_suburb d ON d.suburb_key=p.suburb_key {coverage_where + (' AND' if coverage_where else 'WHERE')} p.ato_median_income IS NOT NULL")) if "fact_suburb_profile" in tables else 0,
            "with_train": int(db.query_one(f"SELECT COUNT(*) FROM fact_suburb_amenities a JOIN dim_suburb d ON d.suburb_key=a.suburb_key {coverage_where + (' AND' if coverage_where else 'WHERE')} a.has_train_2km = true")) if "fact_suburb_amenities" in tables else 0,
            "with_crime": int(db.query_one(f"SELECT COUNT(*) FROM fact_suburb_amenities a JOIN dim_suburb d ON d.suburb_key=a.suburb_key {coverage_where + (' AND' if coverage_where else 'WHERE')} a.safety_score IS NOT NULL")) if "fact_suburb_amenities" in tables else 0,
        }

        # Cheapest and most expensive suburbs with a real, recent rent figure
        extremes_df = db.query_df(f"""
            WITH latest_rent AS (
                SELECT f.suburb_key, f.median_weekly_rent, f.month_key,
                       ROW_NUMBER() OVER (PARTITION BY f.suburb_key ORDER BY f.month_key DESC) as rn
                FROM fact_rent_trend f
                JOIN dim_suburb d ON d.suburb_key = f.suburb_key
                WHERE 1=1 {region_filter_sql}
            )
            SELECT d.suburb_name, d.region, lr.median_weekly_rent
            FROM latest_rent lr JOIN dim_suburb d ON d.suburb_key = lr.suburb_key
            WHERE lr.rn = 1
            ORDER BY lr.median_weekly_rent ASC LIMIT 5
        """)
        cheapest = [{"suburb": r["suburb_name"], "region": r["region"], "rent": round(float(r["median_weekly_rent"]))}
                    for _, r in extremes_df.iterrows()]

        extremes_df2 = db.query_df(f"""
            WITH latest_rent AS (
                SELECT f.suburb_key, f.median_weekly_rent,
                       ROW_NUMBER() OVER (PARTITION BY f.suburb_key ORDER BY f.month_key DESC) as rn
                FROM fact_rent_trend f
                JOIN dim_suburb d ON d.suburb_key = f.suburb_key
                WHERE 1=1 {region_filter_sql}
            )
            SELECT d.suburb_name, d.region, lr.median_weekly_rent
            FROM latest_rent lr JOIN dim_suburb d ON d.suburb_key = lr.suburb_key
            WHERE lr.rn = 1
            ORDER BY lr.median_weekly_rent DESC LIMIT 5
        """)
        priciest = [{"suburb": r["suburb_name"], "region": r["region"], "rent": round(float(r["median_weekly_rent"]))}
                    for _, r in extremes_df2.iterrows()]

        # Fastest risers / fallers: % change from each suburb's earliest to
        # latest reported rent. Requires at least 3 months of history so a
        # single noisy data point can't dominate the ranking. This is a
        # cross-suburb question the chat app never answers - it only ever
        # shows one suburb's own trend at a time.
        movers_df = db.query_df(f"""
            WITH ranked AS (
                SELECT f.suburb_key, f.median_weekly_rent, f.month_key,
                       ROW_NUMBER() OVER (PARTITION BY f.suburb_key ORDER BY f.month_key ASC) as rn_first,
                       ROW_NUMBER() OVER (PARTITION BY f.suburb_key ORDER BY f.month_key DESC) as rn_last,
                       COUNT(*) OVER (PARTITION BY f.suburb_key) as n_months
                FROM fact_rent_trend f
                JOIN dim_suburb d ON d.suburb_key = f.suburb_key
                WHERE 1=1 {region_filter_sql}
            )
            SELECT d.suburb_name, d.region,
                   MAX(CASE WHEN rn_first = 1 THEN median_weekly_rent END) as first_rent,
                   MAX(CASE WHEN rn_last = 1 THEN median_weekly_rent END) as last_rent,
                   MAX(n_months) as n_months
            FROM ranked r JOIN dim_suburb d ON d.suburb_key = r.suburb_key
            WHERE r.n_months >= 3
            GROUP BY d.suburb_name, d.region
        """)
        movers = {"risers": [], "fallers": []}
        if not movers_df.empty:
            movers_df = movers_df[(movers_df["first_rent"] > 0) & movers_df["first_rent"].notna() & movers_df["last_rent"].notna()].copy()
            movers_df["pct_change"] = (movers_df["last_rent"] / movers_df["first_rent"] - 1) * 100
            movers_df = movers_df.sort_values("pct_change", ascending=False)
            # Guard against risers/fallers overlapping when the qualifying
            # pool is small (e.g. early in the warehouse's life, or a sparse
            # subset of suburbs with >=3 months of history) - take at most
            # half the pool from each end rather than a fixed 5, so the same
            # suburb can never appear as both a riser and a faller.
            n = len(movers_df)
            take = min(5, n // 2) if n >= 2 else 0
            top_risers = movers_df.head(take)
            top_fallers = movers_df.tail(take).sort_values("pct_change") if take else movers_df.iloc[0:0]
            movers = {
                "risers": [{"suburb": r["suburb_name"], "region": r["region"], "pct": round(float(r["pct_change"])),
                            "rent": round(float(r["last_rent"]))} for _, r in top_risers.iterrows()],
                "fallers": [{"suburb": r["suburb_name"], "region": r["region"], "pct": round(float(r["pct_change"])),
                             "rent": round(float(r["last_rent"]))} for _, r in top_fallers.iterrows()],
            }

        # Rental stress: rent_to_income_ratio is only populated for the 26
        # rich-profile suburbs (see DATA_QUALITY.md), so this section is
        # explicitly scoped and labeled as covering that subset only - never
        # implied to be a Perth-wide ranking.
        stress_df = db.query_df(f"""
            SELECT d.suburb_name, d.region, p.rent_to_income_ratio, p.ato_median_income
            FROM fact_suburb_profile p JOIN dim_suburb d ON d.suburb_key = p.suburb_key
            WHERE p.rent_to_income_ratio IS NOT NULL {region_filter_sql}
            ORDER BY p.rent_to_income_ratio DESC
        """) if "fact_suburb_profile" in tables else pd.DataFrame()
        rental_stress = [
            {"suburb": r["suburb_name"], "region": r["region"],
             "ratio_pct": round(float(r["rent_to_income_ratio"]) * 100),
             "income": round(float(r["ato_median_income"])) if pd.notna(r["ato_median_income"]) else None}
            for _, r in stress_df.iterrows()
        ]

        # Affordability vs income scatter: same 26-suburb scope, makes that
        # scope visible as the chart's own point count rather than hidden.
        scatter_df = db.query_df(f"""
            WITH latest_rent AS (
                SELECT f.suburb_key, f.median_weekly_rent,
                       ROW_NUMBER() OVER (PARTITION BY f.suburb_key ORDER BY f.month_key DESC) as rn
                FROM fact_rent_trend f
                JOIN dim_suburb d ON d.suburb_key = f.suburb_key
                WHERE 1=1 {region_filter_sql}
            )
            SELECT d.suburb_name, d.region, lr.median_weekly_rent, p.ato_median_income, p.seifa_decile
            FROM fact_suburb_profile p
            JOIN dim_suburb d ON d.suburb_key = p.suburb_key
            LEFT JOIN latest_rent lr ON lr.suburb_key = p.suburb_key AND lr.rn = 1
            WHERE p.ato_median_income IS NOT NULL AND lr.median_weekly_rent IS NOT NULL
        """) if "fact_suburb_profile" in tables else pd.DataFrame()
        affordability_scatter = [
            {"suburb": r["suburb_name"], "region": r["region"], "rent": round(float(r["median_weekly_rent"])),
             "income": round(float(r["ato_median_income"])),
             "seifa": int(r["seifa_decile"]) if pd.notna(r["seifa_decile"]) else None}
            for _, r in scatter_df.iterrows()
        ]

        # Crime by type: the chat app only ever shows one rolled-up
        # safety_score. The actual sub-category counts (burglary, vehicle
        # theft, assault, property damage) are real data that's never been
        # surfaced anywhere. Scoped to suburbs with crime data, aggregated
        # by district since the underlying source is district-level
        # (multiple suburbs share a district's numbers).
        crime_df = db.query_df(f"""
            SELECT district, MAX(burglary) as burglary, MAX(vehicle_theft) as vehicle_theft,
                   MAX(assault) as assault, MAX(property_damage) as property_damage,
                   COUNT(DISTINCT a.suburb_key) as suburb_count
            FROM fact_suburb_amenities a JOIN dim_suburb d ON d.suburb_key = a.suburb_key
            WHERE district IS NOT NULL {region_filter_sql}
            GROUP BY district
            ORDER BY (MAX(burglary) + MAX(vehicle_theft) + MAX(assault) + MAX(property_damage)) DESC
        """) if "fact_suburb_amenities" in tables else pd.DataFrame()
        crime_by_district = [
            {"district": r["district"], "suburb_count": int(r["suburb_count"]),
             "burglary": int(r["burglary"]) if pd.notna(r["burglary"]) else 0,
             "vehicle_theft": int(r["vehicle_theft"]) if pd.notna(r["vehicle_theft"]) else 0,
             "assault": int(r["assault"]) if pd.notna(r["assault"]) else 0,
             "property_damage": int(r["property_damage"]) if pd.notna(r["property_damage"]) else 0}
            for _, r in crime_df.iterrows()
        ]

        return {
            "perth_trend": perth_trend,
            "regions": regions,
            "all_regions": all_regions,
            "current_region": region,
            "yoy_pct": yoy_pct,
            "yoy_suburb_count": yoy_suburb_count,
            "distribution": distribution,
            "coverage": coverage,
            "cheapest": cheapest,
            "priciest": priciest,
            "movers": movers,
            "rental_stress": rental_stress,
            "affordability_scatter": affordability_scatter,
            "crime_by_district": crime_by_district,
        }
    except Exception as e:
        print(f"get_dashboard_data error: {e}")
        return {}

def get_all_suburbs_data():
    """Suburb universe = dim_suburb joined to fact_rent_trend / fact_suburb_profile
    / fact_suburb_amenities (Phase 1 warehouse, steps A-E). Replaces the old
    runtime UPPER(TRIM(...)) normalization over rent_trend directly - that
    work now happens once, ahead of time, in build_dim_suburb.py and the
    fact-table build scripts, rather than on every request.

    Coverage (confirmed against the real database, step F):
      1,222 total suburbs | 1,163 with rent history | 26 with full
      affordability profile (median_rent_2br/3br, tenancy/dispute stats) |
      173 with ATO income / SEIFA | 1,129 with school data | 1,055 with train
      proximity | 173 with crime data (district-level - see suburb_crime
      sourcing note in DATA_QUALITY.md).

    Output columns are unchanged from the pre-rewire version, so every
    existing caller (score(), suburb_to_card(), etc.) works without
    modification: suburb, postcode, median_weekly_rent, rent_data_month,
    median_rent_2br, median_rent_3br, total_tenancies, avg_tenancy_years,
    dispute_rate_pct, school_total, primary_schools, secondary_schools,
    nearest_station, distance_km, has_train_1km, has_train_2km, safety_score.
    Two columns are NEW (fact_suburb_amenities has them; the old query never
    selected them, so score()'s "Bus routes" check was always silently
    falling through): bus_stops_1km, has_bus_1km.

    SMALL-AREA-ESTIMATION FALLBACK (avg_tenancy_years, dispute_rate_pct only):
    these two fields feed score()'s normalization, not a number shown to the
    user as "this suburb's tenancy rate" - they're context-tier, not
    decision-tier (unlike median_rent_2br/3br or ato_median_income, which are
    NEVER backfilled and stay NULL when genuinely absent). For the ~1,196
    suburbs outside the 26 with a real value, this falls back to the
    region-wide average (computed from dim_suburb.region) and flags it via
    avg_tenancy_years_is_estimated / dispute_rate_pct_is_estimated, so any
    caller that wants to distinguish measured-from-estimated can.
    """
    if not db: return pd.DataFrame()
    try:
        conn = db.get_connection()
        tables = [t for (t,) in conn.execute("SHOW TABLES").fetchall()]
        if "dim_suburb" not in tables:
            return pd.DataFrame()  # warehouse not built yet - caller sees an empty df, same as before

        has_rent = "fact_rent_trend" in tables
        has_profile = "fact_suburb_profile" in tables
        has_amenities = "fact_suburb_amenities" in tables

        rent_join = "LEFT JOIN latest_rent r ON r.suburb_key=d.suburb_key" if has_rent else ""
        rent_cols = "r.median_weekly_rent, r.rent_data_month," if has_rent else \
            "NULL as median_weekly_rent, NULL as rent_data_month,"

        profile_join = "LEFT JOIN fact_suburb_profile p ON p.suburb_key=d.suburb_key" if has_profile else ""
        profile_cols = ("p.median_rent_2br, p.median_rent_3br, p.total_tenancies, "
                         "p.avg_tenancy_years, p.dispute_rate_pct,") if has_profile else \
            ("NULL as median_rent_2br, NULL as median_rent_3br, NULL as total_tenancies, "
             "NULL as avg_tenancy_years, NULL as dispute_rate_pct,")

        amenities_join = "LEFT JOIN fact_suburb_amenities am ON am.suburb_key=d.suburb_key" if has_amenities else ""
        amenities_cols = ("am.school_total, am.primary_schools, am.secondary_schools, "
                           "am.nearest_station, am.distance_km, am.has_train_1km, am.has_train_2km, "
                           "am.bus_stops_1km, am.has_bus_1km, am.safety_score,") if has_amenities else \
            ("NULL as school_total, NULL as primary_schools, NULL as secondary_schools, "
             "NULL as nearest_station, NULL as distance_km, NULL as has_train_1km, NULL as has_train_2km, "
             "NULL as bus_stops_1km, NULL as has_bus_1km, NULL as safety_score,")

        latest_rent_cte = """
            latest_rent AS (
                SELECT suburb_key, median_weekly_rent, month_key as rent_data_month
                FROM (
                    SELECT suburb_key, median_weekly_rent, month_key,
                           ROW_NUMBER() OVER (PARTITION BY suburb_key ORDER BY month_key DESC) as rn
                    FROM fact_rent_trend
                ) WHERE rn = 1
            )""" if has_rent else ""

        df = db.query_df(f"""
            WITH {latest_rent_cte}
            SELECT
                d.suburb_name as suburb,
                d.postcode,
                d.region,
                d.has_rich_stats,
                {rent_cols}
                {profile_cols}
                {amenities_cols}
                1 as _placeholder
            FROM dim_suburb d
            {rent_join}
            {profile_join}
            {amenities_join}
        """)
        df = df.drop(columns=["_placeholder"])

        # Small-area-estimation fallback for avg_tenancy_years / dispute_rate_pct
        # only - see docstring. Region-wide average; Perth-wide as a further
        # fallback for the small "Unknown" region bucket. Never applied to
        # rent or income fields.
        for col in ["avg_tenancy_years", "dispute_rate_pct"]:
            region_avg = df.groupby("region")[col].transform("mean")
            perth_avg = df[col].mean()
            is_estimated = df[col].isna() & (region_avg.notna() | pd.notna(perth_avg))
            df[f"{col}_is_estimated"] = is_estimated
            df[col] = df[col].fillna(region_avg).fillna(perth_avg)

        return df.drop_duplicates(subset=["suburb"])
    except Exception as e:
        print(f"get_all_suburbs_data error: {e}")
        return pd.DataFrame()

def get_rent_trend_for(suburb_list):
    """Returns monthly rent history for the given canonical suburb names,
    read from fact_rent_trend (already grouped by suburb_key/month_key -
    the casing-variant averaging that used to happen here on every call now
    happens once in build_fact_rent_trend.py)."""
    if not db or not suburb_list: return pd.DataFrame()
    try:
        conn = db.get_connection()
        tables = [t for (t,) in conn.execute("SHOW TABLES").fetchall()]
        if "fact_rent_trend" not in tables or "dim_suburb" not in tables:
            return pd.DataFrame()

        canon = {s.strip().upper(): s for s in suburb_list}
        keys = list(canon.keys())
        safe = ",".join([f"'{k.replace(chr(39),chr(39)*2)}'" for k in keys])
        df = db.query_df(f"""
            SELECT UPPER(TRIM(d.suburb_name)) as suburb_key, f.month_key as month, f.median_weekly_rent
            FROM fact_rent_trend f
            JOIN dim_suburb d ON d.suburb_key = f.suburb_key
            WHERE UPPER(TRIM(d.suburb_name)) IN ({safe}) AND f.month_key >= '2023-01'
        """)
        if df.empty: return df
        df["suburb"] = df["suburb_key"].map(canon)
        agg = df.groupby(["suburb","month"], as_index=False)["median_weekly_rent"].mean()
        return agg.sort_values(["suburb","month"])
    except Exception as e:
        print(f"get_rent_trend_for error: {e}")
        return pd.DataFrame()

def get_trend_signal(suburb, trend_df):
    try:
        s=trend_df[trend_df["suburb"]==suburb].sort_values("month")
        if len(s)<6: return "stable",0
        recent=s.tail(3)["median_weekly_rent"].mean()
        older=s.iloc[-6:-3]["median_weekly_rent"].mean()
        pct=(recent-older)/older*100 if older>0 else 0
        return ("rising",round(pct,1)) if pct>4 else (("easing",round(pct,1)) if pct<-2 else ("stable",round(pct,1)))
    except: return "stable",0

def calc_takehome(annual_salary):
    if annual_salary<=18200: tax=0
    elif annual_salary<=45000: tax=(annual_salary-18200)*0.19
    elif annual_salary<=120000: tax=5092+(annual_salary-45000)*0.325
    elif annual_salary<=180000: tax=29467+(annual_salary-120000)*0.37
    else: tax=51667+(annual_salary-180000)*0.45
    return round((annual_salary-tax-annual_salary*0.02)/52)

LANDMARK_SUBURBS={
    "Near Kings Park":             ["Subiaco","Nedlands","West Perth","Crawley","Shenton Park"],
    "Near Fremantle":              ["Fremantle","North Fremantle","South Fremantle","Hamilton Hill","Palmyra"],
    "Near Cottesloe Beach":        ["Cottesloe","Swanbourne","Mosman Park","Claremont"],
    "Near Perth CBD":              ["Perth","East Perth","West Perth","Northbridge","Leederville","Mount Lawley"],
    "Near Fiona Stanley Hospital": ["Murdoch","Kardinya","Bull Creek","Bibra Lake","Spearwood"],
    "Near Joondalup Hospital":     ["Joondalup","Edgewater","Beldon","Craigie"],
    "Near UWA":                    ["Crawley","Nedlands","Shenton Park","Subiaco"],
    "Near Garden City":            ["Booragoon","Applecross","Ardross","Myaree","Melville"],
}

LANDMARK_KEYWORDS = {
    "fiona stanley": "Near Fiona Stanley Hospital", "fsh": "Near Fiona Stanley Hospital",
    "joondalup hospital": "Near Joondalup Hospital", "joondalup health": "Near Joondalup Hospital",
    "royal perth": "Near Perth CBD", "perth children": "Near UWA",
    "fremantle": "Near Fremantle", "kings park": "Near Kings Park",
    "uwa": "Near UWA", "garden city": "Near Garden City",
    "cottesloe": "Near Cottesloe Beach",
}

SUBURB_INSIGHTS = {
    "Victoria Park": {
        "known_for": "Albany Highway cafe strip, one of Perth's longest stretches of international restaurants, bars and independent shops. Swan River foreshore 10 minutes walk. Boorloo Bridge (opened late 2024) now connects directly to Perth CBD on foot and by bike.",
        "who": "Young professionals, students, couples. Median age 35. Over half of residents rent.",
        "good_for": "People who want inner city energy without paying Subiaco prices. Excellent for people without a car, since it's walkable and well connected.",
        "watch_out": "Albany Highway noise if you are near it. Street parking is competitive. Some blocks are significantly better than others, so visit different streets before committing.",
    },
    "Gosnells": {
        "known_for": "Canning River regional park, Ellis Brook Valley Reserve, Mary Carroll Park. Green and spacious for the price. Direct train to Perth CBD.",
        "who": "Families, tradies, people priced out of inner suburbs. Diverse community with strong neighbourhood ties.",
        "good_for": "Families who need space and a backyard on a budget. People who value green space and a train connection.",
        "watch_out": "Quality varies significantly street by street. Do a drive-around before committing. The district crime figures cover a large area, so specific streets matter.",
    },
    "Armadale": {
        "known_for": "Minnawarra Park, proximity to Perth Hills bushland, Armadale train line to CBD (~45 min). Improving with new infrastructure investment.",
        "who": "Families, first renters, people moving from regional WA.",
        "good_for": "Renters who need a house with a yard on the lowest possible budget. Families who want outdoor space near bushland.",
        "watch_out": "Commute to Perth CBD is long. Not walkable, so a car is essential. Some pockets are higher crime than others.",
    },
    "Fremantle": {
        "known_for": "Fremantle Markets, fishing boat harbour, South Beach, cappuccino strip on South Terrace, live music venues, historic limestone architecture. Home to Notre Dame University.",
        "who": "Artists, students, young professionals, long-term locals. One of Perth's most genuinely mixed communities.",
        "good_for": "People who want cultural richness, walkability, and a sense of place. Students at Notre Dame. Weekend lifestyle is hard to beat.",
        "watch_out": "Fremantle Doctor (strong afternoon sea breeze) makes summer very windy. Parking is a constant challenge. Some areas near the port are noisier.",
    },
    "Joondalup": {
        "known_for": "Lakeside Joondalup shopping centre, Lake Joondalup nature reserve, Joondalup Health Campus, ECU campus. A proper suburban hub with most services locally.",
        "who": "Families, healthcare workers, ECU students, retirees. Well-established northern community.",
        "good_for": "Healthcare workers at Joondalup Health Campus. Families wanting good schools and local services without going too far north.",
        "watch_out": "Car-dependent outside the immediate town centre. 30+ km from Perth CBD, so train is the best option.",
    },
    "East Rockingham": {
        "known_for": "An industrial suburb within the Kwinana Industrial Area, part of the City of Rockingham, and not a typical residential area. Home to two caravan parks and the heritage-listed Bell Cottage ruin (1868). Population around 300.",
        "who": "Very few residential tenants live here, since this is mostly industrial land. Most people here are likely connected to nearby industrial operations or caravan park residents.",
        "good_for": "Genuinely hard to say from available data. This shows up here on price, but it's worth confirming with a real-estate agent or council whether standard residential rental even applies here before treating it as a serious option.",
        "watch_out": "This is industrial land, not a typical suburb. Expect industrial noise, traffic, and a very different day-to-day environment than a normal residential area. Verify zoning and what's actually available before assuming a standard rental.",
    },
    "Jelcobine": {
        "known_for": "A small rural locality in the Shire of Brookton, about 99km southeast of Perth. Population around 140, mostly farmland.",
        "who": "Likely farming families. No detailed demographic data available for a locality this small.",
        "good_for": "People wanting a rural or farming lifestyle well outside the Perth metro area. Not a commuter suburb.",
        "watch_out": "99km from Perth, so this is a genuine country move, not an outer-suburb compromise. Expect very limited local services, schools, and transport. Confirm what's actually available to rent here before planning around it.",
    },
    "Brown Range": {
        "known_for": "A small rural locality near Carnarvon in the Gascoyne region, about 815km north-northwest of Perth. Population around 147.",
        "who": "No detailed demographic data available for a locality this small and remote.",
        "good_for": "Regional WA residents already based in or near Carnarvon. Not realistic as a Perth-area rental option despite appearing in a Perth-focused search.",
        "watch_out": "815km from Perth, so this is a different region of the state entirely, not a Perth suburb. If you're searching for a Perth rental, this is very likely not what you're looking for, even though it matched your price.",
    },
    "Woorree": {
        "known_for": "A locality on the southern bank of the Chapman River, about 7km east-northeast of Geraldton's CBD. Gazetted in 1981.",
        "who": "No detailed demographic data available.",
        "good_for": "People based in or near Geraldton (regional WA, roughly 4-5 hours north of Perth by car). Not a Perth-area option.",
        "watch_out": "This is a Geraldton-area locality, not Perth metro. Make sure that's actually what you're looking for before treating this as a Perth rental result.",
    },
    "Windabout": {
        "known_for": "A small locality in the Shire of Esperance, about 602km southeast of Perth and 5km north of Esperance itself. Population around 124. Adjoins Esperance golf course and Woody Lake Nature Reserve.",
        "who": "No detailed demographic data available for a locality this small.",
        "good_for": "People based in or near Esperance on WA's south coast. Not realistic as a Perth-area option.",
        "watch_out": "602km from Perth, a long way from the Perth metro area this app otherwise focuses on. Confirm this is genuinely the region you're searching in.",
    },
    "Napier": {
        "known_for": "Limited reliable information available for this specific locality. Research turned up the Napier Range, a Kimberley mountain range, which may or may not be related to the rental-data locality of the same name.",
        "who": "Not enough verified information to say.",
        "good_for": "Not enough verified information to say. Recommend confirming this locality's exact location and character directly before relying on this listing.",
        "watch_out": "This profile couldn't be verified with confidence. Treat this result cautiously and check the suburb's real location before making any decisions based on it.",
    },
    "Orange Grove": {
        "known_for": "A small, semi-rural suburb in the City of Gosnells, about 17km southeast of Perth CBD. Bickley Reservoir, Korung National Park and Banyowla Regional Park are all nearby. REIWA describes it as having a remoteness few suburbs this close to Perth still offer. Population around 700-750.",
        "who": "No detailed demographic data available for a suburb this small.",
        "good_for": "People wanting larger blocks, bushland surrounds, and a semi-rural feel while still being within the Perth metro area. Not a suburb with cafes or a town centre of its own.",
        "watch_out": "Genuinely semi-rural despite being inside the metro boundary. Expect to drive for most shopping and services. Bushfire risk is worth checking given the proximity to national park and reserve land.",
    },
    "Meelon": {
        "known_for": "A tiny former saw-milling locality in the Shire of Murray, in the Peel region between Pinjarra and Dwellingup, about 85km south of Perth. Population around 174. Mostly semi-rural and forested surrounds.",
        "who": "No detailed demographic data available for a locality this small.",
        "good_for": "People wanting a genuinely rural, forested lifestyle in the Peel region. Not realistic as a Perth-commute suburb despite appearing in a Perth-focused search.",
        "watch_out": "85km from Perth CBD, a serious commute, not an outer-suburb compromise. Expect very limited local services. Confirm what's actually available to rent here before planning around it.",
    },
    "Daglish": {
        "known_for": "A heritage 'garden suburb' in the City of Subiaco, about 4km west of Perth CBD. Daglish train station, Cliff Sadlier Reserve, and a streetscape of early-1900s character homes. Population around 1,400-1,550.",
        "who": "Families and retirees are common here, including people who first moved for the schools and have stayed on.",
        "good_for": "People who want heritage character and a quiet, established inner-west location with train access to the CBD.",
        "watch_out": "Small suburb with limited rental turnover, since most homes are owner-occupied. Heritage character homes can mean older wiring, insulation and maintenance quirks, worth checking on inspection.",
    },
    "Orelia": {
        "known_for": "A southern suburb in the City of Kwinana, named after a 19th-century settler ship. Kwinana train station nearby. Mixed housing stock, with older established homes in some parts and newer builds in others. Population around 4,500-4,700.",
        "who": "A genuine mix of long-term residents and newer arrivals, reflecting the suburb's mixed older-and-newer housing stock.",
        "good_for": "People wanting an affordable southern suburb with train access, within the Kwinana area.",
        "watch_out": "Housing quality and street character vary noticeably between the older and newer sections, worth a drive-around before committing to a specific street.",
    },
    "North Plantations": {
        "known_for": "A small rural locality in the Carnarvon local government area, about 819km north of Perth in WA's Gascoyne region. Population around 350-380, covering roughly 27 square kilometres.",
        "who": "No detailed demographic data available for a locality this small and remote.",
        "good_for": "People already based in or near Carnarvon. Not realistic as a Perth-area rental option despite appearing in a Perth-focused search.",
        "watch_out": "819km from Perth, a different region of the state entirely. If you're searching for a Perth rental, this is very likely not what you're looking for, even though it matched your price.",
    },
    "Jindong": {
        "known_for": "A locality in WA's South West region, in the City of Busselton, on the Buayanup River about 210km south-southwest of Perth. Population around 68 at the 2021 census. Has roots in the 1920s Group Settlement Scheme and a local motocross track.",
        "who": "No detailed demographic data available for a locality this small.",
        "good_for": "People already based in or near Busselton and the South West wine region. Not realistic as a Perth-area rental option despite appearing in a Perth-focused search.",
        "watch_out": "210km from Perth, the South West region, not Perth metro. Confirm this is genuinely the area you're searching in before treating this as a Perth rental result.",
    },
    "Donnybrook": {
        "known_for": "A real country town 210km south of Perth, known as the centre of WA's apple industry. Australia's largest free-entry playground (Apple Fun Park), heritage sandstone buildings, and an annual Apple Festival. Population around 2,500.",
        "who": "A genuine, functioning rural community: families, farm and orchard workers, and a mix of long-term locals and tree-changers.",
        "good_for": "People wanting a real country-town lifestyle with actual services on the ground, not just a rural address. Has its own hospital, dentist, medical centre, and schools from kindy to year ten.",
        "watch_out": "210km from Perth, a genuine country move, not a commutable outer suburb. The nearest larger centre for extra services or entertainment is Bunbury, about 25-30 minutes away.",
    },
    "Midvale": {
        "known_for": "A genuine Perth eastern-suburb, split between the City of Swan and Shire of Mundaring, about 17km from the CBD. Developed in the 1950s next to the old Helena Vale Racecourse. Close to Midland Gate Shopping Centre and Midland train station. Population around 1,500-2,300.",
        "who": "A mix of long-term residents and younger families, including a significant amount of government-built housing, some of it recently redeveloped.",
        "good_for": "People wanting an affordable, established eastern-suburb option close to Midland's shops, services, and train line, with parks and bushland nearby.",
        "watch_out": "Genuinely affordable relative to much of Perth, which can mean more variable street-to-street character, worth a drive-around to see specific areas before committing.",
    },
    "Derby": {
        "known_for": "A real town, but a long way from Perth: Derby is in the Kimberley region of far-north WA, around 2,400km from Perth (roughly the same as flying to a different state). Population around 3,200. Known for the highest tides in the Southern Hemisphere, boab trees, and as the gateway to the Gibb River Road.",
        "who": "A genuine remote-WA community, with a significant Aboriginal population and strong pastoral and cultural history. Not a Perth commuter town in any sense.",
        "good_for": "People already living in or relocating to the Kimberley region specifically. This is very unlikely to be a realistic option for a Perth-based rental search.",
        "watch_out": "This is roughly 2,400km from Perth, a multi-day drive or a flight away, not a Perth suburb. If this matched your Perth search on price, it's almost certainly not what you're looking for.",
    },
    "Subiaco": {
        "known_for": "Rokeby Road restaurant strip, Kings Park on the doorstep, Hollywood Private Hospital nearby. Mix of heritage federation homes and modern apartments.",
        "who": "Professionals, established families, medical staff from nearby hospitals.",
        "good_for": "People who want inner city convenience with a quieter, more polished feel. Outstanding for Kings Park access and walkability.",
        "watch_out": "Rent is above Perth median and rising. Very few rentals come available, and competition is fierce when they do. Act quickly.",
    },
    "Cottesloe": {
        "known_for": "Cottesloe Beach, one of Perth's most iconic. Napoleon Street cafe strip. Annual Sculpture by the Sea. Direct train to CBD.",
        "who": "Beach lovers, professionals, established families. Quieter atmosphere than Scarborough.",
        "good_for": "Anyone who prioritises beach access above everything else. Morning swims before work is a real thing people do here.",
        "watch_out": "Very low rental volume, so be ready to move fast when something comes up. Salt air means more property maintenance issues.",
    },
    "Scarborough": {
        "known_for": "Scarborough Beach foreshore, recently redeveloped with restaurants and entertainment. Strong cafe culture. Popular weekend destination for all of Perth.",
        "who": "Young professionals, surfers, active lifestyle seekers. More transient than Cottesloe.",
        "good_for": "Coastal lifestyle at a lower price point than Cottesloe or City Beach. Good for active people who want the beach without the price.",
        "watch_out": "Traffic on West Coast Highway on weekends. Some older apartment blocks have poor insulation.",
    },
    "Baldivis": {
        "known_for": "Spacious new housing estates, family parks, 10 minutes from Rockingham coastline, growing local amenities.",
        "who": "Young families, first renters, people who need space on a budget. Fast-growing population.",
        "good_for": "Families who need a 4-bedroom house on a budget and are happy to drive rather than train.",
        "watch_out": "No train station, so it's fully car-dependent. Freeway to Perth CBD congests. Some estates feel very uniform with limited character.",
    },
    "Rockingham": {
        "known_for": "Rockingham Beach, dolphin watching, Secret Harbour nearby. Relaxed community feel with a genuine local identity. About 47km south of Perth CBD.",
        "who": "Families, retirees, FIFO workers, people seeking affordable coastal lifestyle.",
        "good_for": "People who work locally or from home. Retirees. Anyone who values beach access and space over CBD proximity.",
        "watch_out": "Commute to Perth is 45-60 minutes by car or train. Not suited for people who need to be in the city frequently.",
    },
    "Edgewater": {
        "known_for": "Lake Edgewater, Edgewater train station, walking distance to Joondalup Health Campus and ECU. Quiet, established streets.",
        "who": "Families, healthcare workers, people who work in the Joondalup area.",
        "good_for": "Healthcare workers at Joondalup Health Campus. Families wanting green space and good schools in a quiet setting.",
        "watch_out": "Limited nightlife or culture nearby. Most shopping and entertainment requires driving to Joondalup.",
    },
    "Mount Lawley": {
        "known_for": "Beaufort Street, one of Perth's best restaurant and bar strips. Hyde Park nearby. Beautiful character homes. ECU campus close by.",
        "who": "Young professionals, artists, students. One of Perth's most coveted inner suburbs.",
        "good_for": "People who want character, culture and walkability near the CBD. Excellent for nightlife without the noise of Northbridge.",
        "watch_out": "Beaufort Street noise if you live near it. Rents are high and competition is fierce.",
    },
    "Leederville": {
        "known_for": "Oxford Street cafe and restaurant strip. Lake Monger 10 minutes walk. Leederville train station. Independent cinema. Genuine village feel near the CBD.",
        "who": "Young professionals, couples. Very low turnover, since people stay once they get in.",
        "good_for": "People who want walkable inner city lifestyle within minutes of Perth CBD.",
        "watch_out": "Very low rental supply. Expect strong competition for any listing that comes up.",
    },
    "Midland": {
        "known_for": "Midland Gate shopping centre, Swan Valley wine region 15 minutes away, Midland train station. Helena River parklands.",
        "who": "Families, tradespeople, people who work in the eastern suburbs or Hills.",
        "good_for": "People working in the eastern suburbs or Hills, and anyone wanting more space for the price.",
        "watch_out": "Some parts have higher crime, so research specific streets. CBD commute is 30-40 minutes by train.",
    },
    "Bull Creek": {
        "known_for": "Quiet, established suburban streets. Close to Murdoch train station and Fiona Stanley Hospital. Garden City shopping centre nearby.",
        "who": "Families, healthcare and university workers, people who want a quiet suburb with good access.",
        "good_for": "Healthcare workers at Fiona Stanley Hospital or Murdoch University. Families who want a quiet, safe suburb with good transport.",
        "watch_out": "Not much character or nightlife, purely residential. You will drive to Garden City or Fremantle for most entertainment.",
    },
    "Murdoch": {
        "known_for": "Murdoch University, Fiona Stanley Hospital, St John of God Murdoch Hospital. Murdoch train station. Primarily a health and education precinct suburb.",
        "who": "University students, healthcare workers, academics. Transient population due to the university.",
        "good_for": "Students at Murdoch University. Anyone working at the health campus, since you can walk to work.",
        "watch_out": "Limited local character outside the university and hospital precinct. Can feel institutional. High student turnover in share houses.",
    },
    "Kardinya": {
        "known_for": "Quiet residential suburb adjacent to Kardinya Park shopping centre. Close to Murdoch cluster (hospital and university). Garden City nearby.",
        "who": "Families, healthcare workers, people who want affordable near Fremantle.",
        "good_for": "Good value alternative to more expensive nearby suburbs. Quiet streets, good for families.",
        "watch_out": "No train station. Limited walkability. Needs a car for most activities.",
    },
    "Belmont": {
        "known_for": "Close to Perth Airport, Belmont Forum shopping centre, Belmont racecourse. Practical rather than pretty, but improving steadily with urban renewal.",
        "who": "FIFO workers, airport and aviation staff, practical renters who want proximity to the city without the premium.",
        "good_for": "FIFO workers who want easy airport access. People who need to be near the CBD on a budget. Good public transport links.",
        "watch_out": "Aircraft noise depending on flight paths. Flooding risk in some low-lying streets, so check before you commit. Not a lifestyle suburb.",
    },
    "Cannington": {
        "known_for": "Westfield Carousel, one of Perth's largest shopping centres. Cannington racecourse. Well-connected by train on the Armadale line. Lots of commercial activity.",
        "who": "Families, working professionals, people who prioritise convenience and value.",
        "good_for": "People who want everything within reach (major shopping, train, services) on a budget. Good for families who do not need to commute to the CBD.",
        "watch_out": "Commercial strip character means it can feel busy and noisy. Not a quiet residential feel. Some older housing stock with limited natural light.",
    },
    "Bentley": {
        "known_for": "Curtin University on the doorstep. Bentley Hospital. South Metropolitan TAFE nearby. Mix of student housing and family homes.",
        "who": "Curtin University students, healthcare workers, budget-conscious young professionals.",
        "good_for": "Students at Curtin, with some of the shortest possible commutes. Healthcare workers at Bentley Hospital.",
        "watch_out": "High student population means some streets have high turnover and share house culture. Quality varies significantly, so inspect carefully.",
    },
    "Bayswater": {
        "known_for": "Heritage character homes, Bayswater train station (major interchange for Airport and Midland lines), Beaufort Street extension. Swan River nearby. Rapidly gentrifying.",
        "who": "Young professionals, couples, people who want inner north character without Mount Lawley prices.",
        "good_for": "People who love character homes and want inner city access. Great train connectivity, since Bayswater is a major interchange.",
        "watch_out": "Gentrification is pushing rents up fast. Some streets are still transitioning, so the gap between the best and worst streets is wide.",
    },
    "Maylands": {
        "known_for": "Eighth Avenue cafe strip, a growing foodie scene with independent cafes and restaurants. Swan River foreshore. 5km from CBD. Maylands station on the Midland line.",
        "who": "Young professionals, creatives, people who want inner north lifestyle at lower prices than Mount Lawley or Leederville.",
        "good_for": "People who want café culture and walkability without paying Leederville prices. Growing arts and food scene.",
        "watch_out": "Some parts of Maylands near the main roads are noisy. The suburb is large, so northern and southern parts feel quite different.",
    },
    "Inglewood": {
        "known_for": "Beaufort Street cafe and dining strip shared with Mount Lawley. Quiet residential streets behind the strip. Good schools. 6km from CBD.",
        "who": "Young families, professionals. Similar demographic to Mount Lawley but slightly more affordable.",
        "good_for": "Families who want good schools and café culture without Mount Lawley prices. Quieter streets while still being well connected.",
        "watch_out": "Limited direct train access, so bus dependent or need to drive to Bayswater station. Beaufort Street noise near the strip.",
    },
    "Ellenbrook": {
        "known_for": "Major planned suburb 26km northeast of CBD. New train connection (Ellenbrook line opened late 2024). Family-oriented with parks, good schools and shopping.",
        "who": "Young families, first renters, people who want space and new infrastructure at affordable prices.",
        "good_for": "Families who need space and good schools. Now has a train connection to the CBD, a major improvement.",
        "watch_out": "Still developing, so some amenities are limited. The train line is new so commute patterns are still settling. Can feel isolated in outer sections.",
    },
    "Clarkson": {
        "known_for": "Coastal suburb on the Yanchep line, 40km north of CBD. Ocean Keys shopping centre. Access to northern beaches. Growing community.",
        "who": "Families, first renters, people moving north for affordability. Growing northern corridor population.",
        "good_for": "Families who want coastal proximity and space on a budget. Good train connection to CBD on the Yanchep line.",
        "watch_out": "Long commute to CBD, around 45 to 60 minutes by train. Limited nightlife and dining options locally.",
    },
    "Wanneroo": {
        "known_for": "Wanneroo Town Centre, Wanneroo Botanic Gardens, nearby lakes and parks. Family suburb in the northern corridor. 30km from CBD.",
        "who": "Families, tradies, people working in the northern suburbs. Strong community feel.",
        "good_for": "Families who want space and community on a budget. Good for people who work locally in the north.",
        "watch_out": "Car-dependent. Limited public transport. Long freeway commute to Perth CBD in peak hour.",
    },
    "Hamilton Hill": {
        "known_for": "Close to Fremantle, Cockburn Central and South Beach. Coogee Beach 10 minutes away. Affordable alternative to Fremantle.",
        "who": "Families, people who want Fremantle proximity without Fremantle prices.",
        "good_for": "Renters who love the southern lifestyle but cannot afford Fremantle or South Fremantle. Good access to beaches.",
        "watch_out": "No train station. Car needed for most activities. Some streets feel disconnected from the suburb centres.",
    },
    "Spearwood": {
        "known_for": "South of Fremantle, close to Cockburn Central train station. Coogee Beach 10 minutes. Mix of old industrial and new residential.",
        "who": "Families, young professionals who want southern lifestyle access.",
        "good_for": "Affordable access to southern beaches and Fremantle. Good train connection via Cockburn Central.",
        "watch_out": "Mixed neighbourhood character, with industrial areas sitting next to residential. Research specific streets carefully.",
    },
    "Bibra Lake": {
        "known_for": "Bibra Lake regional park, with wetlands and wildlife. Discovery Parks. Close to Fiona Stanley Hospital and Murdoch cluster. Quiet residential.",
        "who": "Families, healthcare workers, people who value natural surrounds.",
        "good_for": "Families who want large blocks and natural surrounds near the southern health precinct.",
        "watch_out": "Car-dependent. No train. Limited local amenities, so you will drive to Cockburn Central or Garden City for most things.",
    },
    "Kenwick": {
        "known_for": "Affordable outer eastern suburb. Kenwick station on the Thornlie-Cockburn line. Close to Westfield Carousel. Industrial area nearby.",
        "who": "Families, people who want maximum space for their budget in the eastern suburbs.",
        "good_for": "Maximum space per dollar in the eastern suburbs. Good for families who work locally.",
        "watch_out": "Adjacent to industrial areas which affects character. Some roads and footpaths are in poor condition. Research the specific street.",
    },
    "Thornlie": {
        "known_for": "Thornlie station on the new Thornlie-Cockburn link line (opened 2023). Affordable family suburb in the southeast. Close to Westfield Carousel.",
        "who": "Families, tradies, people who want a house with a yard at an affordable price.",
        "good_for": "People who want a house with a yard at an affordable price. Now has better train access with the Thornlie-Cockburn line.",
        "watch_out": "Lacks character compared to inner suburbs. Car still useful even with the train. Some streets are poorly maintained.",
    },
    "Mandurah": {
        "known_for": "Coastal city 75km south of Perth. Mandurah Estuary, dolphin watching, relaxed waterfront lifestyle. Own CBD and amenities. Mandurah train to Perth CBD.",
        "who": "Retirees, FIFO workers, families who want coastal lifestyle and maximum space for money.",
        "good_for": "People who work from home or locally. Retirees. Anyone who wants waterfront lifestyle at genuinely affordable prices.",
        "watch_out": "75km from Perth CBD, where the train takes about 75 minutes. Not suitable for people who need to be in Perth frequently. Some tourist areas are busy in summer.",
    },
    "Palmyra": {
        "known_for": "Close to Fremantle, South Fremantle and East Fremantle. Quiet residential streets. Melville Council. Canning Highway nearby.",
        "who": "Young families, couples who want Fremantle access without Fremantle prices.",
        "good_for": "Renters who want to be within 10 minutes of Fremantle on a tighter budget. Quiet streets.",
        "watch_out": "No direct train, so bus to Fremantle or drive. Canning Highway is a busy road.",
    },
    "Mosman Park": {
        "known_for": "Prestigious riverside suburb between Fremantle and Cottesloe. Peppermint Grove border. Scotch College nearby. Mosman Park and North Fremantle stations.",
        "who": "Professionals, established families.",
        "good_for": "People who want an exclusive address between the beach and the river. Strong school options nearby.",
        "watch_out": "Expensive. Very few rentals come available. Properties vary widely, with some streets exceptional and others ordinary.",
    },
    "South Perth": {
        "known_for": "Swan River foreshore, Perth Zoo, direct ferry to Perth CBD. One of Perth's most scenic suburbs. Old South Perth shopping strip.",
        "who": "Professionals, families who can afford it. Mix of established locals and renters in apartments.",
        "good_for": "People who prioritise parks, river access and the Perth Zoo. The ferry to CBD is a genuine commuting option.",
        "watch_out": "Expensive relative to amenity. Apartments vary widely in quality. Limited train access, so bus or ferry dependent.",
    },
    "Como": {
        "known_for": "Canning Highway restaurant strip. Swan River access. Close to Curtin University. Preston Street cafe scene.",
        "who": "Young professionals, Curtin students, couples. Growing popularity with the inner south crowd.",
        "good_for": "People who want river access and a cafe strip on a smaller budget than South Perth or Applecross.",
        "watch_out": "Canning Highway is very busy, with noise and traffic depending on how close you are. Some areas far from the strip feel disconnected.",
    },
    "Applecross": {
        "known_for": "Upmarket riverside suburb. Canning Highway dining, Swan River views, Heathcote Reserve. One of Perth's most desirable southern suburbs.",
        "who": "Professionals, established families.",
        "good_for": "River lifestyle, excellent schools nearby, prestige address in the southern suburbs.",
        "watch_out": "Expensive. Few rentals available. Very car-dependent despite the lifestyle.",
    },
    "Winthrop": {
        "known_for": "Quiet, established southern suburb. Close to Murdoch University and Fiona Stanley Hospital. Kardinya Park nearby.",
        "who": "Families, university staff, healthcare professionals. Quieter demographic.",
        "good_for": "Families who want a safe, established suburb close to the southern health and education precinct.",
        "watch_out": "Car-dependent. No train. Can feel isolated from the rest of Perth. Limited local character.",
    },
    "Willagee": {
        "known_for": "Affordable inner south suburb close to Fremantle and Garden City. Melville Council area. Quiet streets.",
        "who": "Families, young couples who want southern lifestyle access at lower prices.",
        "good_for": "Good value alternative to nearby Palmyra or Melville. Reasonable Fremantle access.",
        "watch_out": "No train. Limited local dining and nightlife. You will drive to Fremantle or Garden City for most things.",
    },
    "Melville": {
        "known_for": "Garden City shopping centre. Close to Fremantle and Swan River. Established family suburb with good schools.",
        "who": "Families, couples, established professionals.",
        "good_for": "Families who want good schools, Garden City access, and proximity to Fremantle without Fremantle prices.",
        "watch_out": "Car-dependent. No direct train. Some roads carry significant traffic.",
    },
    "Shenton Park": {
        "known_for": "Leafy, quiet suburb between Subiaco and Nedlands. Lake Jualbup. Close to Kings Park. Strong school zone.",
        "who": "Families, professionals who want inner west lifestyle. Tends toward owner-occupiers, so few rentals.",
        "good_for": "Families who want exceptional schools and parkland in a quiet, established setting.",
        "watch_out": "Very few rentals available. When they come up competition is strong. Expect to pay a premium.",
    },
    "Nedlands": {
        "known_for": "UWA campus on the doorstep. Swan River access, Dalkeith Road. Close to Kings Park. Prestigious inner western suburb.",
        "who": "UWA academics and students, medical professionals (Royal Perth Hospital and QEII Medical Centre nearby), established families.",
        "good_for": "UWA staff and postgraduate students. People working at QEII Medical Centre who want to walk or cycle to work.",
        "watch_out": "Expensive even for rentals. Most of the suburb is owner-occupied, so rental supply is very limited.",
    },
    "Crawley": {
        "known_for": "UWA campus suburb. Swan River, Matilda Bay restaurant, cycling paths. Student-dominated.",
        "who": "UWA students and staff almost exclusively. Very transient population.",
        "good_for": "UWA students who want to walk to lectures. Excellent riverside lifestyle.",
        "watch_out": "Very few private rentals, since most accommodation is university-managed. Share houses dominate. Not suitable for families.",
    },
    "North Fremantle": {
        "known_for": "Artisan food scene along Queen Victoria Street. Close to Fremantle Bridge, Port Beach. Character workers cottages. Small and quiet.",
        "who": "Professionals, creatives, people who want Fremantle lifestyle with less noise.",
        "good_for": "People who love Fremantle but want a quieter, more residential feel. Excellent cafe options locally.",
        "watch_out": "Very few rentals available. Freight train line runs through, so it can be noisy near the tracks.",
    },
    "East Perth": {
        "known_for": "Claisebrook Cove, WACA ground, direct access to Perth CBD on foot. Mostly apartments. Nelson Crescent foreshore.",
        "who": "Young professionals, CBD workers who want to walk to work.",
        "good_for": "People who work in the CBD and want to walk. Waterfront lifestyle at city fringe prices.",
        "watch_out": "Mostly high-rise apartments, not suitable for families needing space. Body corporate fees can be high. Stadium events cause significant traffic and noise.",
    },
}

# Case-insensitive index, built once at import time, so a lookup like
# SUBURB_INSIGHTS.get("DAGLISH") and get_suburb_insight("Daglish") both find
# the same entry. This matters because suburb names arriving from the
# database may not always be in the same casing the dict keys were written
# in -- e.g. before a warehouse rebuild picks up a casing-normalization fix,
# or if a future data source introduces its own inconsistency again. A
# plain dict.get() would silently return None and show "not yet researched"
# even when a real, written profile exists, exactly as happened with
# "DAGLISH" not matching the "Daglish" key.
_SUBURB_INSIGHTS_LOWER = {k.lower(): v for k, v in SUBURB_INSIGHTS.items()}

def _build_fallback_insight(row):
    """Builds an honest, auto-generated profile from real database fields
    ONLY -- no invented landmarks, no invented character description, no
    invented demographics. Used when a suburb has no hand-researched
    SUBURB_INSIGHTS entry (currently true for the large majority of the
    ~1,000 suburbs in the warehouse, since manually researching all of them
    isn't realistic). Every fact used here is the same verified data already
    shown elsewhere on the card -- this function just restates it in the
    known_for/who/good_for/watch_out shape so the insight panel never shows
    a bare "not yet researched" dead end.
    """
    facts = []
    postcode = row.get("postcode")
    if _truthy(postcode):
        facts.append(f"Postcode {postcode}.")
    region = row.get("region")
    if _truthy(region) and str(region).strip():
        facts.append(f"{region}.")

    primary = row.get("primary_schools")
    secondary = row.get("secondary_schools")
    if _truthy(primary) or _truthy(secondary):
        try:
            p, s = int(primary or 0), int(secondary or 0)
            if p or s:
                facts.append(f"{p} primary and {s} secondary school(s) in the area.")
        except (ValueError, TypeError):
            pass

    nearest = row.get("nearest_station")
    dist = row.get("distance_km")
    # Same 15km sanity cutoff used elsewhere in this file (suburb_to_card,
    # suburb_deep_dive) -- nearest_station is "closest in the WHOLE
    # dataset", which for remote suburbs can be 60-100+ km away. Showing
    # that as if it were a meaningful nearby-transport fact would be
    # misleading, not honest -- e.g. "Ellenbrook Stn is 68.5km away" reads
    # like a real amenity when it's really just confirming how remote the
    # suburb is.
    if _truthy(nearest) and _truthy(dist):
        try:
            if float(dist) <= 15:
                facts.append(f"{nearest} is {float(dist):.1f}km away.")
        except (ValueError, TypeError):
            pass

    bond_rate = row.get("dispute_rate_pct")
    bond_rate_is_real = _truthy(bond_rate) and not row.get("dispute_rate_pct_is_estimated", False)
    if bond_rate_is_real:
        try:
            facts.append(f"{float(bond_rate):.0f}% of tenancies here had the bond returned in full.")
        except (ValueError, TypeError):
            pass

    tenure = row.get("avg_tenancy_years")
    tenure_is_real = _truthy(tenure) and not row.get("avg_tenancy_years_is_estimated", False)
    if tenure_is_real:
        try:
            facts.append(f"Average tenancy length is {float(tenure):.1f} years.")
        except (ValueError, TypeError):
            pass

    safety = row.get("safety_score")
    if _truthy(safety) and str(safety) not in ["", "None", "nan"]:
        try:
            facts.append(f"Safety score {float(safety):.1f}/10, based on WA Police district crime data.")
        except (ValueError, TypeError):
            pass

    known_for = (" ".join(facts) if facts else "Limited data available for this suburb in our dataset.") + \
        " (Auto-generated from real bond, school and transport data, no written research available yet for this suburb.)"

    return {
        "known_for": known_for,
        "who": "No demographic profile has been researched for this suburb yet. The figures above are the only verified facts we have.",
        "good_for": "Not enough research available to say with confidence, but every figure above comes from real bond, school or crime data, not an estimate.",
        "watch_out": "This is an automatic data summary, not a researched profile. Treat it as a starting point, not a full picture of what the suburb is actually like to live in.",
        "is_auto_generated": True,
    }

def get_suburb_insight(name, row=None):
    if not name:
        return None
    found = _SUBURB_INSIGHTS_LOWER.get(str(name).strip().lower())
    if found:
        return found
    if row is not None:
        return _build_fallback_insight(row)
    return None

def match_suburbs(min_r, max_r, freetext="", amenities=None, exact_target=None, sort_mode="default", region_filter=""):
    amenities = amenities or []
    df = cached("suburbs", get_all_suburbs_data, 600)
    if df is None or df.empty: return [], []
    df = df.copy()

    # Apply region filter from area step
    if region_filter:
        region_mask = df["region"].str.lower().str.contains(region_filter.lower(), na=False)
        filtered = df[region_mask]
        if len(filtered) >= 5:
            df = filtered

    if exact_target:
        # User gave one specific number with no range/ceiling language
        # ("$300 a week", not "$300-400" or "under $300"). Rank by closeness
        # to that exact figure rather than treating it as a padded range -
        # a $440/wk suburb is NOT a match for "$300/wk" even though it might
        # fall inside a widened band, and showing it as "within budget"
        # would be actively misleading.
        df["_distance"] = (df["median_weekly_rent"] - exact_target).abs()
        in_budget = df[df["_distance"] <= 60].sort_values("_distance").copy()
        # also_pool starts where in_budget's $60 window ends, so that
        # "also worth considering" naturally continues outward from the
        # primary matches rather than overlapping with them. (Previously
        # this was the ONLY source for alternatives, which created a real
        # gap: if in_budget had more than 3 suburbs - e.g. several all
        # within $0-60 of target - anything past the top 3 was silently
        # dropped entirely, since also_pool only started at +$60. Suburbs
        # like a $320/wk option, closer to target than the $360+
        # alternatives shown, never appeared anywhere. Fixed below by
        # having the also-consider section pull from the leftover
        # in_budget rows first.)
        also_pool = df[(df["_distance"] > 60) & (df["_distance"] <= 120)].sort_values("_distance").copy()
        if in_budget.empty:
            in_budget = df.sort_values("_distance").head(5).copy()
    else:
        # PRIMARY matches must be genuinely inside the range the person
        # actually typed. Earlier this used a padded window here (e.g.
        # max_r*1.15) for "in_budget" itself, which meant a suburb $50+
        # over the stated max could still rank as a "Best/Second/Third
        # match" purely on amenity score, since the score function has no
        # rent-fit term at all. That's the bug: Peron at $500/wk showing as
        # a primary match for a $400-450/wk search, labelled "over budget"
        # almost as an afterthought. Fixed: in_budget is now the literal
        # range, so only genuine matches ever become primary cards.
        in_budget = df[df["median_weekly_rent"].between(min_r, max_r)].copy()
        # The padded window is now used ONLY to build a wider pool of
        # "also worth considering" alternatives when genuine matches are
        # thin -- it never feeds primary ranking, so it can't misrepresent
        # an out-of-range suburb as a true match.
        also_pool = df[
            df["median_weekly_rent"].between(max(min_r*0.75,50), max_r*1.25) &
            ~df["suburb"].isin(in_budget["suburb"])
        ].copy()
        # Distance from the stated range, used to sort "also worth
        # considering" by closeness rather than amenity score (see below).
        # This branch never had a distance column before -- only the
        # exact_target branch did -- so it has to be computed here.
        if not also_pool.empty:
            also_pool["_distance"] = (
                (also_pool["median_weekly_rent"] - max_r).clip(lower=0) +
                (min_r - also_pool["median_weekly_rent"]).clip(lower=0)
            )

    priority_suburbs = set()
    for am in amenities:
        if am in LANDMARK_SUBURBS: priority_suburbs.update(LANDMARK_SUBURBS[am])
    ftl = freetext.lower()
    for kw, lm in LANDMARK_KEYWORDS.items():
        if kw in ftl and lm in LANDMARK_SUBURBS:
            priority_suburbs.update(LANDMARK_SUBURBS[lm])

    # Detect amenity preferences directly in free text, not just survey
    # checkboxes. Previously someone typing "near a train station" in chat
    # got NOTHING from it -- the scoring boost a few lines below only fires
    # when the literal string "Train station" is in `amenities`, which the
    # chat workflow never populates (only the survey UI's checkboxes do).
    # That meant an explicit, specific request was silently ignored, and
    # remote regional suburbs with zero train data could still outrank a
    # real train-connected suburb on other factors. This makes the chat
    # free-text path and the survey checkbox path converge on the exact
    # same scoring logic below, instead of being two different systems.
    amenities = list(amenities)  # don't mutate the caller's list
    _FREETEXT_AMENITY_PHRASES = {
        "Train station": ["train station", "near a train", "near train", "close to a train",
                           "close to train", "train access", "rail", "near the train"],
        "Bus routes": ["bus route", "bus stop", "near a bus", "near bus", "bus access"],
        "Primary school": ["primary school"],
        "High school": ["high school", "secondary school"],
        "Hospital": ["hospital", "near a hospital"],
        "Near the beach": ["near the beach", "near a beach", "beach access", "close to the beach"],
    }
    for amenity_label, phrases in _FREETEXT_AMENITY_PHRASES.items():
        if amenity_label not in amenities and any(p in ftl for p in phrases):
            amenities.append(amenity_label)

    max_ten = df["total_tenancies"].max() or 1

    def score(row):
        s = 0
        try:
            dr = float(row.get("dispute_rate_pct", 82))
            if pd.notna(dr): s += min((dr-60)/40*30, 30)
        except: s += 8
        try:
            t = float(row.get("avg_tenancy_years", 1.5))
            if pd.notna(t): s += min(t*8, 20)
        except: s += 8
        try: s += (float(row.get("total_tenancies",100))/max_ten)*10
        except: pass
        t1 = row.get("has_train_1km"); t2 = row.get("has_train_2km")
        has_train_near = _truthy(t1) and str(t1).upper() not in ["FALSE","NONE","0",""]
        has_train_2 = _truthy(t2) and str(t2).upper() not in ["FALSE","NONE","0",""]
        if has_train_near: s += 10
        elif has_train_2: s += 5
        try: s += min(int(row.get("school_total",0)),5)
        except: pass
        if row.get("suburb") in priority_suburbs: s += 40
        words = [w.lower().strip() for w in (freetext or "").replace(","," ").split() if len(w)>2]
        if any(w in str(row.get("suburb","")).lower() for w in words): s += 30
        ss = row.get("safety_score")
        if _truthy(ss) and str(ss) not in ["","None","nan"]:
            try: s += float(ss) * 1.5
            except: pass

        # Extra weight for amenity preferences with real backing data
        if "Train station" in amenities and has_train_near:
            s += 25
        if "Bus routes" in amenities:
            bs = row.get("bus_stops_1km")
            if _truthy(bs):
                try:
                    if float(bs) > 0: s += 15
                except: pass
        if "Primary school" in amenities:
            pv = row.get("primary_schools")
            if _truthy(pv):
                try:
                    if int(pv) > 0: s += 15
                except: pass
        if "High school" in amenities:
            sv = row.get("secondary_schools")
            if _truthy(sv):
                try:
                    if int(sv) > 0: s += 15
                except: pass
        if "Hospital" in amenities and row.get("suburb") in HOSPITAL_SUBURBS:
            s += 20
        if "Near the beach" in amenities and row.get("suburb") in COASTAL_SUBURBS:
            s += 25

        return round(s, 1)

    in_budget["score"] = in_budget.apply(score, axis=1)
    also_pool["score"] = also_pool.apply(score, axis=1)

    if exact_target:
        # Closeness to the exact number the user asked for must dominate -
        # amenity score only breaks ties among suburbs that are essentially
        # equally close, it must never push a suburb that's further from
        # the target above one that's closer. A $25 band was originally
        # used here, but that's too wide: it let a $312/wk suburb (12 off
        # target) outrank a suburb sitting exactly on $300 (0 off target),
        # since both fell in the same "0-24" band and amenity score broke
        # the tie. Narrowed to a $5 band so only genuinely-tied distances
        # (e.g. two suburbs both $2 off target) get reordered by amenities;
        # anything more than a few dollars apart sorts strictly by distance.
        in_budget["_dist_band"] = (in_budget["_distance"] // 5).astype(int)
        also_pool["_dist_band"] = (also_pool["_distance"] // 5).astype(int) if not also_pool.empty else also_pool.get("_dist_band", [])
        ranked = in_budget.sort_values(["_dist_band","score"], ascending=[True,False]).drop_duplicates(subset=["suburb"])
        # Anything in ranked beyond the top 3 (which become the primary
        # "Best/Second/Third match" cards) is still genuinely close to the
        # target and should appear in "also worth considering" rather than
        # being silently dropped - that was the actual bug: a suburb at,
        # say, $320/wk (rank 4, still within the $0-60 window) never
        # appeared anywhere, while only the $360+ also_pool alternatives
        # showed, leaving a visible gap in the results.
        leftover_in_budget = ranked.iloc[3:].copy()
        far_alternatives = also_pool.sort_values(["_dist_band","score"], ascending=[True,False]).drop_duplicates(subset=["suburb"]) if not also_pool.empty else also_pool
        also = pd.concat([leftover_in_budget, far_alternatives], ignore_index=True) if not leftover_in_budget.empty else far_alternatives
    else:
        ranked = in_budget.sort_values("score", ascending=False).drop_duplicates(subset=["suburb"])
        # Sort by closeness to budget alone -- pure rent-distance, no
        # amenity-score tiebreaker. This list answers one question ("how
        # close is this suburb's RENT to what I asked for"), so a suburb's
        # school count or train access shouldn't be able to reorder two
        # suburbs that are equally far from the range on price -- that was
        # invisible and confusing when it happened (e.g. Derby and Midvale
        # both $7 from the range, but Midvale shown first purely because it
        # scored higher on amenities, which a person scanning a price-based
        # list has no way to know is happening).
        also = (
            also_pool.sort_values(["_distance","median_weekly_rent"], ascending=[True,True]).drop_duplicates(subset=["suburb"])
            if not also_pool.empty else also_pool
        )

    # If a landmark was detected (e.g. "near Fiona Stanley Hospital"), always show
    # those suburbs as the primary results - even if they're above budget - and
    # be honest about the budget fit via the rent_status field added below.
    if priority_suburbs:
        landmark_rows = df[df["suburb"].isin(priority_suburbs)].copy()
        if not landmark_rows.empty:
            landmark_rows["score"] = landmark_rows.apply(score, axis=1)
            landmark_rows = landmark_rows.sort_values("score", ascending=False).drop_duplicates(subset=["suburb"])
            primary = landmark_rows.head(3)
            # "Also consider" becomes genuinely-affordable alternatives elsewhere,
            # excluding the landmark suburbs themselves
            alt = ranked[~ranked["suburb"].isin(primary["suburb"])]
            if alt.empty:
                alt = also[~also["suburb"].isin(primary["suburb"])]
            if sort_mode == "rent_asc":
                primary = primary.sort_values("median_weekly_rent", ascending=True)
                alt = alt.sort_values("median_weekly_rent", ascending=True)
            return primary.head(3).to_dict("records"), alt.head(3).to_dict("records")

    if sort_mode == "rent_asc":
        # Pure ascending-rent override, applied as a final pass on top of
        # whatever in_budget/also_pool sets were already correctly computed
        # above -- does not change WHICH suburbs qualify, only the order
        # they're shown in. This is for explicit follow-ups like "sort by
        # rent", where the person genuinely wants cheapest-first regardless
        # of amenity score or closeness-to-target ranking.
        ranked = ranked.sort_values("median_weekly_rent", ascending=True)
        also = also.sort_values("median_weekly_rent", ascending=True)

    # Apply final sort override before returning
    if sort_mode == "rent_asc":
        ranked = ranked.sort_values("median_weekly_rent", ascending=True)
        also = also.sort_values("median_weekly_rent", ascending=True)

    return ranked.head(3).to_dict("records"), also.head(3).to_dict("records")

def suburb_to_card(row, rank_lbl, trend_df, min_r=None, max_r=None, exact_target=None):
    name = row["suburb"]
    rent = float(row["median_weekly_rent"])
    signal, pct = get_trend_signal(name, trend_df)
    bond_rate = row.get("dispute_rate_pct")
    tenure = row.get("avg_tenancy_years")
    # These two fields can be a region/Perth-wide small-area-estimation
    # fallback (see get_all_suburbs_data) rather than this suburb's own
    # measured statistic. Never present a fallback as if it were measured -
    # only use it in the card's notes if it's real, and label it as a
    # regional estimate otherwise.
    bond_rate_is_real = _truthy(bond_rate) and not row.get("dispute_rate_pct_is_estimated", False)
    tenure_is_real = _truthy(tenure) and not row.get("avg_tenancy_years_is_estimated", False)
    nearest = row.get("nearest_station")
    nearest = nearest if _truthy(nearest) else ""
    dist = row.get("distance_km")
    school_total = row.get("school_total")
    primary = row.get("primary_schools")
    secondary = row.get("secondary_schools")
    safety = row.get("safety_score")

    # Build chips
    chips = []
    # Same 15km sanity cutoff as suburb_deep_dive: nearest_station is
    # "closest in the dataset", which for remote/regional suburbs can be
    # 100s of km away (e.g. North Yunderup -> Mandurah, 15.6km) - don't show
    # it as if it were a normal nearby-amenity chip beyond a sensible radius.
    if _truthy(nearest) and pd.notna(dist) and float(dist) <= 15:
        df2 = float(dist)
        tl = "Walking distance" if df2 <= 0.8 else f"{df2:.1f}km"
        tc = "green" if df2 <= 1.5 else "amber"
        stn = nearest.replace(" Stn","").replace(" Station","")
        chips.append({"icon":"train","text":f"{stn} · {tl}","color":tc})
    if _truthy(school_total) and int(school_total) > 0:
        parts = []
        if _truthy(primary) and int(primary) > 0:
            parts.append(f"{int(primary)}P")
        if _truthy(secondary) and int(secondary) > 0:
            parts.append(f"{int(secondary)}S")
        if parts:
            chips.append({"icon":"school","text":f"{'+'.join(parts)} schools","color":"blue"})
    if _truthy(safety) and str(safety) not in ["","None","nan"]:
        try:
            sf = float(safety)
            sl = "Very low crime" if sf>=8 else ("Low crime" if sf>=6 else ("Average" if sf>=4 else "Above avg"))
            sc = "green" if sf>=6 else "amber"
            chips.append({"icon":"shield","text":sl,"color":sc})
        except: pass
    trend_label = {"rising":f"↑ Rent rising {abs(pct):.0f}%","easing":f"↓ Rent easing {abs(pct):.0f}%","stable":"→ Rent stable"}.get(signal,"")
    trend_color = {"rising":"red","easing":"green","stable":"amber"}.get(signal,"gray")
    chips.append({"icon":"trend","text":trend_label,"color":trend_color})

    # Budget fit - honest indicator of how this suburb compares to the user's
    # budget. When the user gave one exact number ("$300/wk", no range or
    # ceiling language), compare against THAT figure, not max_r - max_r in
    # this case is just an internal search-window boundary (e.g. b+30),
    # never something the user actually said, and showing "within budget"
    # against it was the literal bug being fixed here.
    budget_fit = None
    target_for_display = exact_target if exact_target else max_r
    if target_for_display:
        if exact_target:
            diff = rent - exact_target
            if abs(diff) <= 15:
                budget_fit = {"text": "Matches your budget", "color": "green"}
            elif diff < 0:
                budget_fit = {"text": f"${abs(diff):.0f}/wk under your target", "color": "green"}
            elif diff <= 60:
                budget_fit = {"text": f"${diff:.0f}/wk over your target", "color": "amber"}
            else:
                budget_fit = {"text": f"${diff:.0f}/wk over your target", "color": "red"}
        elif min_r and rent < min_r * 0.98:
            # Below the stated minimum is just as much "outside the range"
            # as being above the maximum -- previously only the max_r side
            # was checked here, so a suburb like $375/wk against a stated
            # $400-450/wk range showed the chip as "Within budget", which
            # is simply wrong: $375 is below what was asked for, not within it.
            under = min_r - rent
            if under <= max_r * 0.13:
                budget_fit = {"text": f"${under:.0f}/wk under your minimum", "color": "amber"}
            else:
                budget_fit = {"text": f"${under:.0f}/wk under your minimum", "color": "red"}
        elif rent <= max_r * 1.02:
            budget_fit = {"text": "Within budget", "color": "green"}
        elif rent <= max_r * 1.15:
            budget_fit = {"text": f"${rent-max_r:.0f}/wk over budget", "color": "amber"}
        else:
            budget_fit = {"text": f"${rent-max_r:.0f}/wk over budget", "color": "red"}
        chips.insert(0, {"icon":"dollar","text":budget_fit["text"],"color":budget_fit["color"]})

    # Bond/tenure note - only the suburb's OWN measured value, never the
    # region/Perth-wide fallback presented as if it were specific to this suburb
    notes = []
    if bond_rate_is_real:
        notes.append(f"{int(bond_rate)}% bond return")
    if tenure_is_real:
        notes.append(f"{float(tenure):.1f} yrs avg stay")

    # Description
    desc_parts = []
    if _truthy(primary) and int(primary) > 0:
        desc_parts.append(f"{int(primary)} primary schools nearby")
    if _truthy(nearest) and pd.notna(dist) and float(dist) <= 15:
        df2 = float(dist)
        if df2 <= 1: desc_parts.append(f"{nearest.replace(' Stn','').replace(' Station','')} station walking distance")
        else: desc_parts.append(f"{nearest.replace(' Stn','').replace(' Station','')} station {df2:.1f}km away")
    if bond_rate_is_real and int(bond_rate) >= 88:
        desc_parts.append("landlords tend to be fair")
    if tenure_is_real and float(tenure) >= 2.0:
        desc_parts.append(f"people stay {float(tenure):.1f} years on average, a settled community")

    # Why this suburb ranked where it did - surfaced so the ordering isn't
    # opaque, especially when several suburbs tie on rent (e.g. all exactly
    # $300/wk) and the only thing actually differentiating them is amenity/
    # reliability data. Built from the same real signals the scoring
    # function (score(), above) weighs most heavily: train access, school
    # count, safety, and - when present - tenant outcomes. Only mentions
    # factors that are genuinely present for THIS suburb; never invents a
    # reason or implies data that isn't there.
    reason_parts = []
    if _truthy(nearest) and pd.notna(dist) and float(dist) <= 15:
        reason_parts.append("train access")
    if _truthy(safety):
        try:
            if float(safety) >= 6:
                reason_parts.append("good safety rating")
        except: pass
    if bond_rate_is_real and int(bond_rate) >= 88:
        reason_parts.append("low rental disputes")
    if tenure_is_real and float(tenure) >= 2.0:
        reason_parts.append("longer average tenancies")
    if _truthy(school_total) and int(school_total) >= 5:
        reason_parts.append("more schools nearby")
    rank_reason = "Ranked higher for: " + ", ".join(reason_parts) if reason_parts else "Limited amenity data available for this suburb"

    return {
        "name": name,
        "postcode": str(row.get("postcode","")),
        "rent": rent,
        "rent2": float(row["median_rent_2br"]) if _truthy(row.get("median_rent_2br")) else None,
        "rent3": float(row["median_rent_3br"]) if _truthy(row.get("median_rent_3br")) else None,
        "rank": rank_lbl,
        "rank_reason": rank_reason,
        "signal": signal,
        "trend_pct": pct,
        "chips": chips,
        "notes": " · ".join(notes),
        "desc": ". ".join(desc_parts) + "." if desc_parts else "",
        "reiwa_url": f"https://reiwa.com.au/rental-properties/{name.lower().replace(' ','-')}/",
        "insight": get_suburb_insight(name, row),
        "tenure": float(tenure) if tenure_is_real else None,
        "bond_rate": int(bond_rate) if bond_rate_is_real else None,
    }

def suburb_deep_dive(name):
    df = cached("suburbs", get_all_suburbs_data, 600)
    if df is None or df.empty: return None
    row_df = df[df["suburb"].str.upper()==name.upper()]
    if row_df.empty: return None
    r = row_df.iloc[0]
    trend_df = get_rent_trend_for([name])
    signal, pct = get_trend_signal(name, trend_df)

    # Rent history
    hist_note = ""
    if not trend_df.empty:
        s = trend_df[trend_df["suburb"]==r["suburb"]].sort_values("month")
        if len(s) >= 4:
            first_r = float(s.iloc[0]["median_weekly_rent"])
            first_m = s.iloc[0]["month"]
            hist_note = f"Up from ${first_r:.0f}/wk in {first_m}"

    # Trend
    trend_txt = {"rising":f"↑ Rent rising {abs(pct):.0f}%","easing":f"↓ Rent easing {abs(pct):.0f}%","stable":"→ Rent stable"}.get(signal,"Stable")
    trend_note = {"rising":"act sooner rather than later","easing":"good time to negotiate","stable":"less pressure to rush"}.get(signal,"")
    trend_color = {"rising":"#E05252","easing":"#0D7C66","stable":"#B45309"}.get(signal,"#B45309")

    # Bond - never present a region/Perth-wide fallback as this suburb's own
    # measured bond-return rate (same is_estimated guard as suburb_to_card)
    bond_rate = r.get("dispute_rate_pct")
    bond_rate_is_real = _truthy(bond_rate) and not r.get("dispute_rate_pct_is_estimated", False)
    br = int(bond_rate) if bond_rate_is_real else None
    br_label = ("Fair landlords" if br and br>=90 else ("Average" if br and br>=80 else "Ask questions")) if br else "No data"
    br_color = "#0D7C66" if br and br>=90 else ("#B45309" if br and br>=80 else "#E05252") if br else "#888"

    # Safety
    safety = r.get("safety_score")
    sc_label, sc_color = "Check police.wa.gov.au", "#888"
    if _truthy(safety) and str(safety) not in ["","None","nan"]:
        try:
            sf = float(safety)
            if sf>=8: sc_label,sc_color="Very low crime","#0D7C66"
            elif sf>=6: sc_label,sc_color="Low crime","#0D7C66"
            elif sf>=4: sc_label,sc_color="Average for Perth","#B45309"
            else: sc_label,sc_color="Above average","#E05252"
        except: pass

    # Train
    nearest = r.get("nearest_station")
    nearest = nearest if _truthy(nearest) else ""
    dist = r.get("distance_km")
    train_text, train_color = "", "#888"
    # Only treat this as a real "nearby train" amenity within a sensible
    # radius - fact_suburb_amenities' nearest_station is "closest in the
    # dataset", which for remote regional suburbs can be 100s of km away.
    # 15km is generous (well beyond walkable, but still "in the area"
    # rather than a different region's station entirely).
    if nearest and pd.notna(dist) and float(dist) <= 15:
        df2 = float(dist)
        tl = "Walking distance" if df2<=0.8 else f"{df2:.1f}km away"
        train_text = f"{nearest.replace(' Stn','').replace(' Station','')} Station · {tl}"
        train_color = "#0D7C66" if df2<=1.5 else "#B45309"

    # Schools
    school_total = r.get("school_total"); primary = r.get("primary_schools"); secondary = r.get("secondary_schools")
    school_text = ""
    if _truthy(school_total) and int(school_total)>0:
        parts = []
        if _truthy(primary) and int(primary)>0: parts.append(f"{int(primary)} primary")
        if _truthy(secondary) and int(secondary)>0: parts.append(f"{int(secondary)} secondary")
        school_text = " and ".join(parts) + " schools in this postcode" if parts else ""

    tenure = r.get("avg_tenancy_years")
    tenure_is_real = _truthy(tenure) and not r.get("avg_tenancy_years_is_estimated", False)
    ten_str = f"{float(tenure):.1f} years" if tenure_is_real else None

    return {
        "name": r["suburb"],
        "postcode": str(r.get("postcode","")),
        "rent": float(r["median_weekly_rent"]),
        "rent2": float(r["median_rent_2br"]) if _truthy(r.get("median_rent_2br")) else None,
        "rent3": float(r["median_rent_3br"]) if _truthy(r.get("median_rent_3br")) else None,
        "hist_note": hist_note,
        "trend_txt": trend_txt,
        "trend_note": trend_note,
        "trend_color": trend_color,
        "br": br,
        "br_label": br_label,
        "br_color": br_color,
        "tenure": ten_str,
        "train_text": train_text,
        "train_color": train_color,
        "school_text": school_text,
        "sc_label": sc_label,
        "sc_color": sc_color,
    }

# ── DETECT WORKFLOW ────────────────────────────────────────────────────────────
def _truthy(val):
    """Safe truthiness check for values that may be None/NaN/pd.NA, which can
    come from LEFT JOINs that didn't match. Unlike `bool(pd.NA)` (which raises
    TypeError), this returns False for any of None/NaN/pd.NA."""
    if val is None:
        return False
    try:
        if pd.isna(val):
            return False
    except (TypeError, ValueError):
        pass
    return bool(val)

def find_suburb_mentions(text, subs, limit=None):
    """Find suburb names mentioned in text. Two-pass: full-name matches are
    strong evidence and always preferred; the first-word fallback (for names
    stored with a state/postcode suffix, e.g. 'Maylands WA') is weak evidence
    and only used for suburbs with no full match.

    This two-pass order matters: 'Cannington' contains 'canning', so without
    it, a fallback match on 'Canning Vale' (first word 'canning' is a
    substring of 'Cannington') could be found before or instead of the
    correct full match on 'Cannington' itself, depending on subs order.
    Sorting full matches by length (longest first) additionally protects
    against one real suburb name being a substring of another."""
    tl = text.lower()
    full_matches = []
    fallback_matches = []
    for s in subs:
        s_lower = s.lower()
        if s_lower in tl:
            full_matches.append(s)
        elif s_lower.split():
            first = re.sub(r"[^a-z]", "", s_lower.split()[0])
            if len(first) > 3 and first in tl:
                fallback_matches.append(s)

    full_matches.sort(key=len, reverse=True)
    found = full_matches + fallback_matches
    if limit:
        found = found[:limit]
    return found

def detect_workflow(msg):
    m = msg.lower()
    if any(w in m for w in ["should i take","should i rent","inspected","inspection","mould","mold","bond is","weeks bond","agent said","property at"]):
        return "property_advisor"
    if any(w in m for w in ["compare","vs","versus"]) and any(w in m for w in ["suburb","gosnells","armadale","joondalup","fremantle","victoria park","subiaco","rockingham","scarborough","baldivis","midland","maylands"]):
        return "compare"
    if any(w in m for w in ["negotiate","negotiating","call about","about to call","asking too much","reduce rent","lower rent"]):
        return "negotiate"
    if any(w in m for w in ["review my application","cover note","cover letter","my application"]):
        return "application_review"
    if any(w in m for w in ["tell me everything","everything about","tell me about","more about","deep dive","all about","full picture"]):
        return "deep_dive"
    if any(w in m for w in ["where should i","find me","looking for","which suburb","best suburb","affordable","cheap","what suburb","suburbs for","under $","for $","budget","near","nurse","teacher","doctor","work in","work near","i work","primary school","backyard","dog","pet","family","per week","a week","/wk","pw","fiona stanley","joondalup","hospital"]):
        return "search"
    return "general"

# ── API ENDPOINTS ──────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(content=INDEX_HTML)

@app.get("/healthz")
async def healthz():
    """Minimal health check for uptime monitoring (e.g. UptimeRobot keep-alive
    pings on Render's free tier). Deliberately does not touch the database -
    a ping every few minutes should be as cheap as possible."""
    return {"status": "ok"}

@app.get("/test")
async def test():
    return JSONResponse({"status": "ok", "db": db is not None})

@app.get("/api/perth-stats")
async def perth_stats():
    s = cached("perth_stats", get_perth_stats, 3600)
    now = _dt.date.today()
    cheap = ["June","July","August"]
    is_cheap = now.strftime("%B") in cheap
    return {
        "lr": s.get("lr", 700),
        "pct": s.get("pct", 37),
        "total_bonds": s.get("total_bonds", 470254),
        "current_month": now.strftime("%B"),
        "is_cheap": is_cheap,
    }

def get_suburbs_in_bucket(bucket, region=None):
    """Real suburb list for one rent bucket (used by the dashboard
    histogram's click-to-drill-down interaction). bucket must be one of the
    exact labels in RENT_BUCKETS; anything else returns an empty result
    rather than guessing or erroring, since this is reached from a query
    string parameter."""
    if not db: return {"suburbs": [], "bucket": bucket}
    valid_labels = {label for label, lo, hi in RENT_BUCKETS}
    if bucket not in valid_labels:
        return {"suburbs": [], "bucket": bucket}
    lo, hi = next((lo, hi) for label, lo, hi in RENT_BUCKETS if label == bucket)
    try:
        all_regions_df = db.query_df("SELECT DISTINCT region FROM dim_suburb WHERE region IS NOT NULL ORDER BY region")
        all_regions = [r["region"] for _, r in all_regions_df.iterrows()]
        if region and region not in all_regions:
            region = None

        def _sql_lit(s):
            return "'" + s.replace("'", "''") + "'"
        region_filter_sql = f"AND d.region = {_sql_lit(region)}" if region else ""
        hi_clause = f"AND lr.median_weekly_rent < {hi}" if hi is not None else ""

        df = db.query_df(f"""
            WITH latest_rent AS (
                SELECT f.suburb_key, f.median_weekly_rent,
                       ROW_NUMBER() OVER (PARTITION BY f.suburb_key ORDER BY f.month_key DESC) as rn
                FROM fact_rent_trend f
                JOIN dim_suburb d ON d.suburb_key = f.suburb_key
                WHERE 1=1 {region_filter_sql}
            )
            SELECT d.suburb_name, d.region, lr.median_weekly_rent
            FROM latest_rent lr JOIN dim_suburb d ON d.suburb_key = lr.suburb_key
            WHERE lr.rn = 1 AND lr.median_weekly_rent >= {lo} {hi_clause}
            ORDER BY lr.median_weekly_rent ASC
        """)
        suburbs = [{"suburb": r["suburb_name"], "region": r["region"], "rent": round(float(r["median_weekly_rent"]))}
                   for _, r in df.iterrows()]
        return {"suburbs": suburbs, "bucket": bucket, "count": len(suburbs)}
    except Exception as e:
        print(f"get_suburbs_in_bucket error: {e}")
        return {"suburbs": [], "bucket": bucket}

@app.get("/api/dashboard")
async def dashboard_data(region: Optional[str] = None):
    if region:
        # Filtered view: query fresh rather than caching per-region, since
        # these aggregate queries are cheap on DuckDB and a multi-key cache
        # isn't worth the complexity for an optional filter most requests
        # won't use.
        return get_dashboard_data(region=region)
    return cached("dashboard", get_dashboard_data, 3600)

@app.get("/api/dashboard/bucket")
async def dashboard_bucket(bucket: str, region: Optional[str] = None):
    return get_suburbs_in_bucket(bucket, region=region)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    return HTMLResponse(content=DASHBOARD_HTML)


@app.post("/api/chat")
async def chat(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        return JSONResponse(
            {"error": "Too many requests. Please wait a bit before trying again."},
            status_code=429,
        )

    body = await request.json()
    msg = body.get("message","")
    history = body.get("history",[])
    min_r = body.get("min_r")
    max_r = body.get("max_r")

    # ── Budget reply continuation ───────────────────────────────────────────
    # Two cases where the user's reply alone isn't enough for workflow detection:
    # 1. A bare number ("400") in reply to "what's your budget?"
    # 2. An affirmative ("yes", "sure") in reply to "around $400-$500/week?"
    # In both cases, combine with the ORIGINAL query (the user message before
    # the assistant's budget question) so search/landmark detection works.
    effective_msg = msg

    # ── Out-of-scope detection - runs before ANY other routing ──────────────────
    _oos_checks = [
        (r"\b(sydney|melbourne|brisbane|adelaide|hobart|darwin|canberra|auckland|bali|london|singapore|new york|dubai)\b",
         "Perth Rental Finder only covers Perth, WA. I don't have data for other cities or countries. For other Australian cities, try domain.com.au or realestate.com.au."),
        (r"\b(airbnb|short.?term|holiday rental|vacation rental|nightly rate)\b",
         "Our data covers long-term residential rentals only (bonds lodged with the WA government). For short-term or holiday rentals, try Airbnb or Stayz."),
        (r"\b(share room|room for rent|room in a share|flatmate wanted|housemate wanted|single room available|renting a room)\b",
         "Our data covers whole-property bonds, not individual rooms. For share rooms, try Flatmates.com.au or Facebook Marketplace."),
        (r"\b(commercial|office space|warehouse|retail space|industrial unit|shop for rent)\b",
         "We only cover residential rentals. For commercial property, try realcommercial.com.au."),
        (r"\b(off.?plan|new development|under construction|house and land package|build to rent)\b",
         "Our data covers existing rental properties with bond records. For new developments, try REIWA.com.au or contact a local developer."),
        (r"\b(\d+\s+\w+\s+(?:street|road|avenue|drive|crescent|place|way|close|court)\s+\w)\b",
         "We work at suburb level. We don't have data on specific streets or addresses. Try reiwa.com.au or domain.com.au for specific property listings."),
    ]
    for _oos_pat, _oos_reply in _oos_checks:
        if re.search(_oos_pat, effective_msg, re.I):
            return JSONResponse({"workflow": "prose", "text": _oos_reply})

    bare_num = re.match(r"^\$?\s*(\d{2,5})\s*(?:/wk|pw|per week|a week)?\s*$", msg.strip(), re.I)
    # Normalise common typing typos like "yess", "yesss", "okkk" by collapsing a
    # run of repeated trailing letters down to one, before matching affirmatives.
    msg_norm = re.sub(r"([a-zA-Z])\1+([.!]*)$", r"\1\2", msg.strip())
    affirm = re.match(r"^(yes|yeah|yep|yup|sure|ok|okay|sounds good|that works|correct|right|that'?s fine|fine|good|perfect)[.!]*$", msg_norm, re.I)

    last_assistant_msg = ""
    if history and history[-1].get("role") == "assistant":
        last_assistant_msg = history[-1].get("content","")
    asked_for_budget = bool(re.search(r"budget|\$\d", last_assistant_msg, re.I)) and "week" in last_assistant_msg.lower()

    if (bare_num or (affirm and asked_for_budget)) and history:
        # The original query is the user message right before the assistant's question
        prev_user = ""
        if len(history) >= 2 and history[-2].get("role") == "user":
            prev_user = history[-2].get("content","")
        elif history[-1].get("role") == "user":
            prev_user = history[-1].get("content","")

        if bare_num:
            budget_str = f"${bare_num.group(1)}/wk"
        else:
            # Extract the budget range/figure the assistant suggested
            range_match = re.search(r"\$(\d{2,5})\s*[\u2013\u2014\-]\s*\$?(\d{2,5})", last_assistant_msg)
            single_match = re.search(r"\$(\d{2,5})", last_assistant_msg)
            if range_match:
                budget_str = f"${range_match.group(1)}-${range_match.group(2)}/wk"
            elif single_match:
                budget_str = f"${single_match.group(1)}/wk"
            else:
                budget_str = ""

        if prev_user and budget_str:
            effective_msg = f"{prev_user}, weekly budget {budget_str}"

    # ── Re-sort / re-filter follow-ups ──────────────────────────────────────
    # A message like "sort the above list by rent" or "order by price" refers
    # to results already shown, not a new request - it has no budget figures
    # of its own, so detect_workflow() would never classify it as "search"
    # and it would otherwise fall through to the free-text general-agent
    # fallback, which has no real suburb data and will confabulate an answer
    # rather than admit it can't see the previous results. Detect this
    # pattern explicitly and re-run the REAL search using the most recent
    # budget actually mentioned anywhere in the conversation history, so the
    # person gets genuinely re-sorted real data, not invented prose.
    sort_mode = "default"
    resort_pattern = re.search(
        r"\b(sort|order|re-?sort|re-?order|rank|arrange)\b.{0,40}\b(rent|price|cost|cheap|budget)\b"
        r"|\b(cheapest|lowest rent|highest rent)\s+first\b",
        effective_msg, re.I,
    )
    if resort_pattern:
        if min_r and max_r:
            # The common case: the frontend already persists min_r/max_r
            # across the whole conversation once a search has happened (see
            # budget = {...} in INDEX_HTML, kept until Clear is clicked), so
            # a "sort by rent" follow-up almost always arrives with a
            # perfectly good budget already attached. Previously this branch
            # required min_r/max_r to be ABSENT before doing anything, which
            # meant it never fired here - the request fell through
            # detect_workflow() (no trigger words match "sort the list by
            # rent") straight to the free-text general-agent fallback, which
            # has no real data and fabricated an entirely invented suburb
            # list instead of admitting it had nothing real to sort.
            effective_msg = f"suburbs for ${min_r}-${max_r}/wk sorted by rent"
            sort_mode = "rent_asc"
        elif not re.search(r"\$\d", effective_msg):
            # Fallback for the rarer case where no budget is attached yet at
            # all (e.g. a fresh page load somehow lost state) - recover the
            # most recent one mentioned anywhere in conversation history.
            found_budget = None
            for h in reversed(history):
                content = h.get("content", "")
                range_match = re.search(r"\$(\d{2,5})\s*[\u2013\u2014\-]\s*\$?(\d{2,5})", content)
                single_match = re.search(r"\$(\d{2,5})\s*(?:/wk|pw|per week|a week)", content, re.I)
                if range_match:
                    found_budget = (int(range_match.group(1)), int(range_match.group(2)))
                    break
                elif single_match:
                    v = int(single_match.group(1))
                    found_budget = (max(v - 50, 150), v + 50)
                    break
            if found_budget:
                min_r, max_r = found_budget
                effective_msg = f"suburbs for ${min_r}-${max_r}/wk sorted by rent"
                sort_mode = "rent_asc"

    # ── Suburb-name correction follow-ups ───────────────────────────────────
    # If the assistant's last turn said it couldn't find a suburb (the
    # honest "doesn't match any suburb" response), a short follow-up like
    # "i meant Mumberkine" or "no, Mumberkine" is almost certainly a
    # correction, not a new unrelated request -- but it has none of
    # detect_workflow's "tell me about" / "everything about" trigger words,
    # so without this it falls straight through to the general-agent
    # fallback and gets answered from the model's own general knowledge
    # instead of the real get_suburb_insight() data (including the
    # auto-generated fallback profile built from real bond/school data).
    last_assistant = next((h.get("content","") for h in reversed(history) if h.get("role")=="assistant"), "")
    looked_like_not_found = bool(re.search(
        r"doesn'?t match any suburb|don'?t have verified (bond )?data for this suburb|"
        r"couldn'?t find (that|this) suburb|misspelled",
        last_assistant, re.I,
    ))
    if looked_like_not_found and len(effective_msg.split()) <= 6 and not re.search(
        r"\b(sort|order|compare|negotiate|application|inspect|mould|bond is)\b", effective_msg, re.I
    ):
        effective_msg = f"tell me everything about {effective_msg}"

    workflow = detect_workflow(effective_msg)

    # Extract budget from effective message
    # exact_target tracks whether the user gave one specific number with no
    # range/ceiling qualifier (e.g. "$300 a week") - in that case we want
    # suburbs close to that number, not a wide band padded on both sides.
    # This was a real bug: a bare number got turned into min_r=b-50,
    # max_r=b+150, and match_suburbs widened that further (*0.85 to *1.15),
    # so "$300/wk" actually searched roughly $212-$517 and labelled results
    # up to $450 as "within budget" - visibly wrong to anyone who asked for
    # a specific figure.
    exact_target = None
    if not min_r or not max_r:
        bnums = [int(x) for x in re.findall(r"\$?(\d{3,5})(?:/wk|pw|per week|a week)?", effective_msg) if 150 < int(x) < 20000]
        has_range_word = any(w in effective_msg.lower() for w in [" to ", "-", "–", "between"])
        if len(bnums) >= 2 and has_range_word:
            min_r, max_r = min(bnums), max(bnums)
        elif len(bnums) >= 1:
            b = bnums[0]
            if any(w in effective_msg.lower() for w in ["under","below","less than","up to","max"]):
                min_r, max_r = max(b-100,150), b
            elif any(w in effective_msg.lower() for w in ["over","above","at least","more than","minimum"]):
                min_r, max_r = b, b+300
            else:
                # Bare number, no qualifier: treat as an exact target, not a
                # padded range. match_suburbs gets told the real number via
                # exact_target so it can rank by closeness instead of
                # widening the window further.
                exact_target = b
                min_r, max_r = max(b-30,150), b+30

    # Build response based on workflow
    if workflow == "search" and min_r and max_r:
        results, also = match_suburbs(min_r, max_r, effective_msg, exact_target=exact_target, sort_mode=sort_mode)
        # Filter remote WA towns from results when budget is very low
        _REMOTE = {"Wonthella","Roebourne","Wubin","Carnarvon","Geraldton","Port Hedland",
                   "Karratha","Broome","Kalgoorlie","Esperance","Albany","Collie","Donnybrook",
                   "Augusta","Busselton","Margaret River","Narrogin","Merredin","Northam",
                   "Wickham","Newman","Tom Price","Paraburdoo","Onslow","Exmouth",
                   "Derby","Fitzroy Crossing","Halls Creek","Kununurra","Wyndham",
                   "Kealy","Mungalup","Jandabup","Kurrawang Community","Ongerup",
                   "West Swan","South Guilford","Whiteman"}
        if min_r and min_r < 450:
            results = [r for r in results if r.get("suburb") not in _REMOTE]
            also = [r for r in also if r.get("suburb") not in _REMOTE]
        trend_df = get_rent_trend_for([r["suburb"] for r in results + also])
        # When the user gave an exact figure, compare each card's rent
        # against THAT number for the "within/over budget" display - not
        # the artificially widened max_r, which is just an internal search
        # window and was never what the user actually asked for.
        display_target = exact_target if exact_target else max_r
        rank_labels = ["Cheapest","Second cheapest","Third cheapest"] if sort_mode == "rent_asc" else ["Best match","Second match","Third match"]
        cards = [suburb_to_card(r, rank_labels[i], trend_df, min_r, max_r, exact_target=exact_target) for i,r in enumerate(results)]
        also_cards = [suburb_to_card(r, "Also consider", trend_df, min_r, max_r, exact_target=exact_target) for r in also]

        # Sharpen rank_reason by actually comparing the primary cards against
        # each other (cheap Haiku call), rather than relying solely on each
        # card's isolated checklist. Only touches `cards`, not `also_cards`,
        # to keep this scoped and cheap -- the secondary list doesn't need
        # the same level of comparative detail. Any failure here is silent
        # and harmless: cards keep their existing rank_reason.
        better_reasons = compare_cards_for_reasons(cards)
        for c in cards:
            if c["name"] in better_reasons:
                c["rank_reason"] = better_reasons[c["name"]]

        # Build a compact data summary for the LLM - no tool calls, no duplication
        def fmt_card(c):
            if exact_target:
                fit = "within budget" if abs(c["rent"]-display_target) <= 30 else f"${c['rent']-display_target:.0f}/wk over budget"
            elif min_r and c["rent"] < min_r * 0.98:
                fit = f"${min_r-c['rent']:.0f}/wk below your minimum"
            elif c["rent"] <= display_target*1.02:
                fit = "within budget"
            else:
                fit = f"${c['rent']-display_target:.0f}/wk over budget"
            return f"{c['name']} (${c['rent']:.0f}/wk, {fit}, {c['notes']})"
        primary_summary = "; ".join(fmt_card(c) for c in cards)
        alt_summary = "; ".join(fmt_card(c) for c in also_cards) if also_cards else ""

        system = (
            "You are a Perth rental assistant. The person's message and budget are below, "
            "along with real suburb data already computed and shown to them as cards. "
            "Do NOT repeat the numbers verbatim, the cards already show rent, trend, schools, transport, crime. "
            "Write a short, honest, warm summary in plain prose (2-4 sentences total, under 100 words). "
            "If suburbs are over budget, acknowledge it honestly and suggest what to do "
            "(stretch budget slightly, widen the search area, or consider the alternatives). "
            "If everything is within budget, just briefly say why these fit well. "
            "STRICT: only describe what the data actually shows (price, trend, amenities). "
            "Do NOT speculate about WHY a suburb is priced the way it is, what it 'signals' about "
            "demand or quality, or any other cause you are not given data for. If a suburb is far "
            "outside budget, just say so plainly rather than theorizing about what that might mean. "
            "No headers, no bullet points, no bold suburb names, use $ signs for any dollar amounts mentioned."
        )
        user_msg = (
            f"User said: \"{msg}\"\n"
            f"Budget: " + (f"${exact_target}/wk (an exact target, not a range)\n" if exact_target else f"${min_r}-${max_r}/wk\n") +
            f"Primary suburbs shown: {primary_summary}\n"
            + (f"Alternatives shown: {alt_summary}\n" if alt_summary else "")
        )
        agent_text = llm_text(system, user_msg, max_tokens=400, model="claude-haiku-4-5-20251001")

        return JSONResponse({
            "workflow": "search",
            "cards": cards,
            "also_cards": also_cards,
            "text": agent_text,
            "min_r": min_r,
            "max_r": max_r,
        })

    elif workflow == "search" and not min_r:
        # Ask for budget - short, direct, no tool calls needed
        system = ("You are a friendly Perth rental assistant. The person has described what they're "
                  "looking for but not given a budget. Ask ONE short, warm question: what is their "
                  "weekly rental budget? Keep it to 1-2 sentences, no emojis. If you suggest an example "
                  "range, format it exactly as \"$400-$500/wk\" (a single dash, no spaces, no \"week\" "
                  "spelled out - use /wk).")
        return JSONResponse({"workflow":"general","text": llm_text(system, msg, max_tokens=150, model="claude-haiku-4-5-20251001")})

    elif workflow == "deep_dive":
        df = cached("suburbs", get_all_suburbs_data, 600)
        subs = df["suburb"].tolist() if df is not None and not df.empty else []
        _found = find_suburb_mentions(effective_msg, subs, limit=1)
        mentioned = _found[0] if _found else None
        card = suburb_deep_dive(mentioned) if mentioned else None
        # Looked up BEFORE the prompt is built (previously this ran after,
        # meaning the AI's free-text description never saw it at all and
        # would confidently invent its own character description from
        # training knowledge -- e.g. claiming "young professionals" and
        # specific parks for a suburb our own research says is mostly
        # families and retirees near a different reserve. That produced two
        # contradictory descriptions of the same suburb on one screen.)
        insight = None
        if mentioned:
            _row = None
            if df is not None and not df.empty:
                _rdf = df[df["suburb"].str.upper() == mentioned.upper()]
                if not _rdf.empty:
                    _row = _rdf.iloc[0]
            insight = get_suburb_insight(mentioned, _row)

        if card and insight and not insight.get("is_auto_generated"):
            # We have BOTH real bond data and a hand-researched written
            # profile -- the strongest case. The AI must work only from
            # these facts, not add anything from its own general knowledge.
            system = (
                "You are a Perth rental expert. A data card is already shown to the person with the "
                "exact figures given to you below - do NOT restate, round, or rephrase ANY of those "
                "numbers, and do NOT introduce any other dollar figures, percentages, or rent ranges "
                "of your own. You are also given a verified, researched profile of this suburb below. "
                "Write 2-3 sentences of character description using ONLY the facts in that researched "
                "profile, in your own natural phrasing. Do NOT add any fact, landmark, park, street, or "
                "claim about who lives there that isn't present in the profile given to you, even if you "
                "believe you know more about this suburb. If the profile is thin, keep your description "
                "correspondingly brief rather than filling the gap with your own knowledge. Plain prose, "
                "no headers, no bullet points, under 80 words, no numbers at all."
            )
            user_msg = (
                f"{msg}\n\n"
                f"[The card already shown states: median rent ${card['rent']:.0f}/wk"
                + (f", 2-bed ${card['rent2']:.0f}/wk" if card.get('rent2') else "")
                + (f", 3-bed ${card['rent3']:.0f}/wk" if card.get('rent3') else "")
                + f"; rent trend {card['trend_txt']}; bond return rate {card['br']}% ({card['br_label']}); "
                + f"average tenancy {card['tenure']}; {card['train_text']}; {card['school_text']}. "
                + "Do not restate any of this.]\n\n"
                + f"[Verified researched profile: known for: {insight['known_for']} "
                + f"Who lives here: {insight['who']} Good for: {insight['good_for']} "
                + f"Watch out: {insight['watch_out']}]"
            )
        elif card and insight and insight.get("is_auto_generated"):
            # Real bond data, and an auto-generated data summary (not a
            # hand-researched profile) -- the AI must be told plainly that
            # this is a data summary, not verified research, so it doesn't
            # imply more confidence than the source actually has.
            system = (
                "You are a Perth rental expert. A data card is already shown to the person with the "
                "exact figures given to you below - do NOT restate, round, or rephrase ANY of those "
                "numbers, and do NOT introduce any other dollar figures, percentages, or rent ranges "
                "of your own. We have NOT done written research on this suburb's character, lifestyle, "
                "or demographics -- only the auto-generated data summary below, built from real database "
                "fields. Write 1-2 sentences acknowledging that briefly and honestly (e.g. \"There isn't "
                "a detailed written profile for this suburb yet, but here's what the data shows\"), then "
                "restate the auto-generated facts in natural prose. Do NOT add any landmark, park, street, "
                "or character claim that isn't in the summary, even if you believe you know more about "
                "this suburb. Plain prose, no headers, no bullet points, under 80 words, no numbers at all "
                "beyond what's already in the summary."
            )
            user_msg = (
                f"{msg}\n\n"
                f"[The card already shown states: median rent ${card['rent']:.0f}/wk"
                + (f", 2-bed ${card['rent2']:.0f}/wk" if card.get('rent2') else "")
                + (f", 3-bed ${card['rent3']:.0f}/wk" if card.get('rent3') else "")
                + f"; rent trend {card['trend_txt']}; bond return rate {card['br']}% ({card['br_label']}); "
                + f"average tenancy {card['tenure']}; {card['train_text']}; {card['school_text']}. "
                + "Do not restate any of this.]\n\n"
                + f"[Auto-generated data summary (not written research): {insight['known_for']}]"
            )
        elif card:
            # Real bond data, but no written profile yet for this suburb.
            # Keep the previous behavior here (general character description
            # from the model's own knowledge), but be honest that it's not
            # verified the way the numeric card data is.
            system = (
                "You are a Perth rental expert. A data card is already shown to the person with the "
                "exact figures given to you below - do NOT restate, round, or rephrase ANY of those "
                "numbers, and do NOT introduce any other dollar figures, percentages, or rent ranges "
                "of your own. We do not have a verified written profile for this suburb yet, so write "
                "2-3 sentences of general character description from your own knowledge, but make clear "
                "this part is general knowledge rather than verified research (e.g. 'generally known for' "
                "rather than stating it as fact). Plain prose, no headers, no bullet points, under 80 "
                "words, no numbers at all."
            )
            user_msg = (
                f"{msg}\n\n"
                f"[The card already shown states: median rent ${card['rent']:.0f}/wk"
                + (f", 2-bed ${card['rent2']:.0f}/wk" if card.get('rent2') else "")
                + (f", 3-bed ${card['rent3']:.0f}/wk" if card.get('rent3') else "")
                + f"; rent trend {card['trend_txt']}; bond return rate {card['br']}% ({card['br_label']}); "
                + f"average tenancy {card['tenure']}; {card['train_text']}; {card['school_text']}. "
                + "Do not restate any of this - just describe the character of the area.]"
            )
        else:
            system = (
                "You are a Perth rental expert. This suburb was not found in our 470,000-record WA "
                "bond dataset - it may be too small, too new, or grouped under a different name. "
                "Be upfront about that in your FIRST sentence (e.g. \"I don't have verified bond data "
                "for this suburb\"). Then give 2-3 sentences of general character description from your "
                "own knowledge, clearly as general knowledge rather than data - and do NOT state "
                "specific rent figures or percentages as if they were measured. Suggest a well-known "
                "nearby suburb they could ask about instead. Plain prose, no headers, under 90 words."
            )
            user_msg = msg
        agent_text = llm_text(system, user_msg, max_tokens=300)
        return JSONResponse({"workflow":"deep_dive","card":card,"text":agent_text,"insight":insight})

    elif workflow == "property_advisor":
        system = ("You are a WA renter advisor. Respond with ONLY valid JSON, no markdown fences, "
                  "no commentary before or after - just the JSON object. Structure:\n"
                  '{"verdict": "proceed" | "caution" | "walk_away", '
                  '"verdict_text": "one sentence summary of your overall take", '
                  '"illegal": ["each issue that breaches WA law, with the section number, as its own string"], '
                  '"watch_out": ["each concern worth raising, as its own string"], '
                  '"good_signs": ["each positive sign, as its own string"], '
                  '"script": "exact words the renter could say to the agent, written as a direct quote"}\n'
                  "Reference WA law where relevant: bond max 4 weeks (s.32 RTA 1987), rent increases once "
                  "per 12 months with 60 days notice (s.30, amended July 2024), application fees are illegal, "
                  "urgent repairs within 24hrs (s.43), mould is a landlord obligation. "
                  "illegal/watch_out/good_signs can be empty arrays if none apply. Use $ signs for dollar amounts. "
                  "Keep each list item to one sentence.")
        raw = llm_text(system, msg, max_tokens=900)
        advisor = None
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```[a-zA-Z]*\n?|```$", "", cleaned.strip(), flags=re.M).strip()
            advisor = json.loads(cleaned)
        except Exception:
            advisor = None
        if advisor:
            return JSONResponse({"workflow":"property_advisor","advisor":advisor})
        # Fallback: if the model didn't return valid JSON, show the raw text
        return JSONResponse({"workflow":"property_advisor","text": raw})

    elif workflow == "compare":
        df = cached("suburbs", get_all_suburbs_data, 600)
        subs = df["suburb"].tolist() if df is not None and not df.empty else []
        mentioned = find_suburb_mentions(effective_msg, subs, limit=2)

        cards = []
        comparison_data = ""
        if mentioned:
            trend_df = get_rent_trend_for(mentioned)
            for sub in mentioned:
                row_df = df[df["suburb"]==sub]
                if not row_df.empty:
                    row = row_df.iloc[0]
                    card = suburb_to_card(row, "", trend_df)
                    cards.append(card)
                    comparison_data += f"{sub}: ${card['rent']:.0f}/wk, {card['notes']}. "

        if len(cards) >= 2:
            system = ("You are a Perth rental advisor. Real data cards comparing these suburbs are "
                      "already shown to the person - do NOT repeat the numbers verbatim. "
                      "Write a short recommendation (2-4 sentences, under 90 words): who this suits "
                      "and why, based on what the person said matters to them. No headers, no bullet "
                      "points, no bold suburb names. Use $ signs only if you mention a number not "
                      "already on the cards. "
                      f"Real data for reference: {comparison_data}")
        else:
            missing_note = "Neither suburb was" if not cards else "One of the suburbs was"
            system = (f"You are a Perth rental advisor. {missing_note} found in our 470,000-record "
                      "WA bond dataset - they may be too small, too new, or grouped under a different "
                      "name. Be upfront about that in your first sentence. Then give 2-3 sentences of "
                      "general comparison from your own knowledge, clearly framed as general knowledge "
                      "rather than data - do NOT state specific rent figures or percentages as if "
                      "measured. Suggest two well-known nearby suburbs they could compare instead. "
                      "Plain prose, no headers, no bullet points, under 90 words. "
                      f"Real data we do have: {comparison_data if comparison_data else '(none)'}")
        text = llm_text(system, msg, max_tokens=300)
        return JSONResponse({"workflow":"compare","cards":cards,"text":text})

    elif workflow == "negotiate":
        df = cached("suburbs", get_all_suburbs_data, 600)
        subs = df["suburb"].tolist() if df is not None and not df.empty else []
        _found = find_suburb_mentions(effective_msg, subs, limit=1)
        mentioned = _found[0] if _found else None
        market = ""
        if mentioned and df is not None:
            row = df[df["suburb"]==mentioned]
            if not row.empty:
                r = row.iloc[0]
                trend_df = get_rent_trend_for([mentioned])
                sig, pct = get_trend_signal(mentioned, trend_df)
                market = f"Real data: {mentioned} typical rent ${r['median_weekly_rent']:.0f}/wk, trend {sig} {abs(pct):.0f}%."
        system = (f"You are a Perth rental negotiation coach. State the position (strong/moderate/weak). "
                  f"Give exact words to say and a fallback if refused. Plain prose. Use $ signs. {market}")
        return JSONResponse({"workflow":"negotiate","text": llm_text(system, msg, max_tokens=600)})

    elif workflow == "application_review":
        system = ("Review the rental application cover note. "
                  "Structure with bold headings: **Problems**, **What to add**, **Improved version**. "
                  "Plain prose under each heading. No bullet points. Be direct and honest.")
        return JSONResponse({"workflow":"application_review","text": llm_text(system, msg, max_tokens=700)})

    else:
        return JSONResponse({"workflow":"general","text": get_agent_text(effective_msg, history)})

_STYLE_GUIDE = (
    "\n\nPunctuation: do not use em-dashes (\u2014) as a sentence connector or for dramatic "
    "pauses. Use a full stop, comma, colon, or separate sentence instead. A hyphen is fine for "
    "a genuine number range (like $400-$500/wk) or a compound word (like 2-bedroom)."
)

def llm_text(system, user_msg, max_tokens=700, model="claude-sonnet-4-6"):
    """Single direct Claude call, no tools. Used when main.py already has real data.
    model defaults to Sonnet (current behavior unchanged for existing callers);
    pass model="claude-haiku-4-5-20251001" for simpler, cheaper tasks like
    comparing a short candidate list, where Sonnet-level reasoning isn't needed."""
    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system + _STYLE_GUIDE,
            messages=[{"role":"user","content":user_msg}],
        )
        return "".join(b.text for b in response.content if b.type == "text")
    except Exception as e:
        return f"Error: {e}"

def compare_cards_for_reasons(cards):
    """Looks at the shortlisted suburbs TOGETHER and asks Haiku what genuinely
    differentiates them, e.g. "all three are within $10/wk, but only X has
    measured tenancy data" -- a comparative judgment the per-suburb checklist
    in suburb_to_card() can't make, since that function scores each suburb in
    isolation and never sees the others. Returns a dict {suburb_name: reason}
    on success. On ANY failure (API error, bad JSON, missing key, timeout) it
    returns an empty dict, and the caller keeps each card's existing
    checklist-based rank_reason untouched -- this step can only improve the
    text, never break or blank it out.
    """
    if not cards or len(cards) < 2:
        return {}  # nothing to compare with fewer than 2 candidates
    try:
        facts = "\n".join(
            f"- {c['name']}: ${c['rent']:.0f}/wk, {c.get('notes','no notes')}, "
            f"{c.get('desc','no further data')}"
            for c in cards
        )
        system = (
            "You compare a short list of Perth suburbs and identify what genuinely "
            "differentiates each one from the others in this specific list -- not generic "
            "praise. If two suburbs are nearly identical on price, say what actually "
            "separates them (e.g. one has real tenancy data and the other doesn't). "
            "If rent is exactly tied between suburbs, look for ANY other real factual "
            "difference given to you below -- even a small one like a different school "
            "count or different transport access counts as a genuine differentiator, and "
            "is more useful than saying there is none. Only fall back to stating there is "
            "no real differentiator if the suburbs are ALSO identical on every other fact "
            "you were given, and if so use this exact phrasing every time for consistency: "
            "\"Same rent and amenities as the others, no further data available.\" "
            "STRICT: only state facts given to you below. Do NOT speculate about WHY a suburb "
            "is priced a certain way or what it might signal about an area. "
            "Reply with ONLY a JSON object, no other text: "
            '{"Suburb Name": "short reason (under 12 words)", ...} for every suburb listed below.'
        )
        user_msg = f"Compare these suburbs:\n{facts}"
        raw = llm_text(system, user_msg, max_tokens=300, model="claude-haiku-4-5-20251001")
        if raw.startswith("Error:"):
            return {}
        # Strip markdown code fences if the model added them despite instructions
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        result = json.loads(cleaned.strip())
        if not isinstance(result, dict):
            return {}
        return {k: v for k, v in result.items() if isinstance(v, str) and v.strip()}
    except Exception:
        # Any parsing/API failure here is non-fatal -- the search already
        # has a working, honest rank_reason from the checklist logic.
        return {}

def get_agent_text(msg, history, system_extra=""):
    try:
        import agent as ai_agent
        fmt = "\n\n[Formatting: plain prose only. No bullet points. No asterisks. Use $ for dollar amounts. Bold only for section headings.]"
        if system_extra:
            msg = msg + f"\n\n[Instructions: {system_extra}]"
        msg = msg + fmt
        full = ""
        if ai_agent is None:
            return "I can answer general questions about renting in Perth. Try asking about a specific suburb, comparing two areas, or your lease rights."
        for chunk in ai_agent.run_agent(msg, list(history)):
            full += chunk
        return full
    except ImportError as e:
        return "I can answer general questions about renting in Perth. Try asking about a specific suburb, comparing two areas, or your lease rights."
    except Exception as e:
        return f"Agent error: {e}"

@app.get("/api/suburb/{name}")
async def get_suburb(name: str):
    card = suburb_deep_dive(name)
    if not card:
        return JSONResponse({"error": "Suburb not found"}, status_code=404)
    return JSONResponse(card)

@app.get("/api/suburb-count")
async def suburb_count(min_r: int, max_r: int):
    df = cached("suburbs", get_all_suburbs_data, 600)
    if df is None or df.empty:
        return JSONResponse({"count": 0})
    n = df[df["median_weekly_rent"].between(max(min_r*0.85,50), max_r*1.15)]["suburb"].nunique()
    return JSONResponse({"count": int(n)})

# Amenity groups for the step-by-step survey "what matters to you" step
LANDMARK_OPTIONS = list(LANDMARK_SUBURBS.keys())

AMENITY_GROUPS = {
    "🏫 Schools":        ["Primary school", "High school", "University or TAFE", "Childcare centre"],
    "🚆 Transport":      ["Train station", "Bus routes", "Freeway access", "Cycling paths"],
    "🛒 Shopping":       ["Shopping centre", "Supermarket", "Pharmacy"],
    "🌳 Lifestyle":      ["Parks and green space", "Near the beach", "Cafes and restaurants", "Gym or fitness centre", "Dog-friendly areas"],
    "🏥 Healthcare":     ["Hospital", "GP / medical centre"],
    "📍 Near a landmark": LANDMARK_OPTIONS,
}

# Suburbs used to score amenity preferences that have real backing data
COASTAL_SUBURBS = {"Cottesloe","Swanbourne","Mosman Park","Claremont","Scarborough",
                    "Fremantle","North Fremantle","South Fremantle","Mandurah",
                    "Rockingham","Hillarys","Sorrento"}
HOSPITAL_SUBURBS = set(LANDMARK_SUBURBS["Near Fiona Stanley Hospital"]) | set(LANDMARK_SUBURBS["Near Joondalup Hospital"])

@app.get("/api/landmark-options")
async def landmark_options():
    return JSONResponse({"options": LANDMARK_OPTIONS})

@app.get("/api/amenity-groups")
async def amenity_groups():
    return JSONResponse({"groups": AMENITY_GROUPS})

@app.post("/api/survey-search")
async def survey_search(request: Request):
    body = await request.json()
    min_r = body.get("min_r", 400)
    max_r = body.get("max_r", 700)
    amenities = body.get("amenities", [])
    freetext = body.get("freetext", "")

    region_filter = body.get("region_filter", "")
    results, also = match_suburbs(min_r, max_r, freetext, amenities, region_filter=region_filter, sort_mode="rent_asc")
    # Filter out obviously remote/non-Perth results when budget is very low
    # These are real WA bond records but not useful Perth rental options
    REMOTE_TOWNS = {"Wonthella","Roebourne","Wubin","Carnarvon","Geraldton","Port Hedland",
                    "Karratha","Broome","Kalgoorlie","Esperance","Albany","Bunbury","Mandurah",
                    "Collie","Donnybrook","Augusta","Busselton","Margaret River","Narrogin",
                    "Merredin","Northam","York","Toodyay","Gingin","Dandaragan","Jurien Bay",
                    "Lancelin","Bindoon","Chittering","Boyup Brook","Bridgetown","Manjimup",
                    "Pemberton","Walpole","Denmark","Mount Barker","Katanning","Wagin","Narrogin",
                    "Wickham","Newman","Tom Price","Paraburdoo","Onslow","Exmouth","Shark Bay",
                    "Derby","Fitzroy Crossing","Halls Creek","Kununurra","Wyndham","Jandabup",
                    "Kealy","Treendale","Mungalup","Serpentine","Dwellingup","Jarrahdale"}
    if min_r < 450:
        results = [r for r in results if r.get("suburb") not in REMOTE_TOWNS]
        also = [r for r in also if r.get("suburb") not in REMOTE_TOWNS]
    if not results:
        if max_r < 380:
            hint = f"The most affordable Perth suburbs start around $380–$420/wk. Try widening your budget upward."
        elif min_r > 1200:
            hint = f"Our data tops out at $1,274/wk. At this budget, REIWA.com.au or a specialist agent like Acton or Abode Property would be better placed to help."
        else:
            hint = f"Try widening your range, e.g. ${max(100, min_r-100)}–${max_r+150}/wk, or selecting 'No preference' for area to see more options."
        return JSONResponse({"cards": [], "also_cards": [], "text": f"No suburbs found between ${min_r}–${max_r}/wk with those filters. {hint} Based on 470,254 real WA bond records."})

    trend_df = get_rent_trend_for([r["suburb"] for r in results + also])
    labels = ["Lowest rent","Second lowest","Third lowest"]
    cards = [suburb_to_card(r, labels[i], trend_df, min_r, max_r) for i,r in enumerate(results)]
    also_cards = [suburb_to_card(r, "Also consider", trend_df, min_r, max_r) for r in also]

    def fmt_card(c):
        if c["rent"] < min_r * 0.98:
            fit = f"${min_r-c['rent']:.0f}/wk below your minimum"
        elif c["rent"] <= max_r*1.02:
            fit = "within budget"
        else:
            fit = f"${c['rent']-max_r:.0f}/wk over budget"
        return f"{c['name']} (${c['rent']:.0f}/wk, {fit}, {c['notes']})"
    primary_summary = "; ".join(fmt_card(c) for c in cards)
    alt_summary = "; ".join(fmt_card(c) for c in also_cards) if also_cards else ""

    system = (
        "You are a Perth rental assistant. Real suburb data is already shown to the person as cards. "
        "Do NOT repeat the numbers verbatim. Write a short, warm summary in plain prose "
        "(2-3 sentences, under 80 words) introducing these matches based on their stated budget "
        "and preferences. STRICT: only describe what the data actually shows. Do NOT speculate "
        "about WHY a suburb is priced the way it is or what that might signal about demand or "
        "quality. No headers, no bullet points, no bold suburb names. Use $ signs."
    )
    user_msg = (
        f"Budget: ${min_r}-${max_r}/wk\n"
        f"Preferences: {', '.join(amenities) if amenities else 'none specified'}. {freetext}\n"
        f"Primary suburbs shown: {primary_summary}\n"
        + (f"Alternatives shown: {alt_summary}\n" if alt_summary else "")
    )
    text = llm_text(system, user_msg, max_tokens=300)

    return JSONResponse({"cards": cards, "also_cards": also_cards, "text": text, "min_r": min_r, "max_r": max_r})
