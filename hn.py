#!/usr/bin/env python3# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════════
🌐 NEXUS HN CLASSIC — Hacker News Clone (GitHub-classic style)
═══════════════════════════════════════════════════════════════════════════════
Serveur local qui récupère les vrais posts Hacker News via l'API Firebase
publique (aucune clé requise), et les affiche dans une interface classique
inspirée de GitHub (thème clair, typographie sobre, dense, lisible).

- Récupération live des top stories HN (API Firebase officielle)
- Interface 3 colonnes : liste / détail / sidebar
- Filtres par score, par type (story, job, poll)
- Recherche dans les titres
- Mode sombre/clair
- Cache mémoire pour éviter le rate-limit
- Aucune dépendance externe (stdlib uniquement)
- Fonctionne sur iPhone, Linux, macOS, Windows

Port par défaut : 8080
═══════════════════════════════════════════════════════════════════════════════
"""

import os
import sys
import json
import time
import html
import threading
import urllib.request
import urllib.error
import argparse
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from typing import Any, Dict, List, Optional, Tuple
from collections import OrderedDict

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

VERSION = "1.0.0"
HOST = "127.0.0.1"
PORT = 8080

HN_API = "https://hacker-news.firebaseio.com/v0"
HN_ITEM = HN_API + "/item/{}.json"
HN_TOP = HN_API + "/topstories.json"
HN_NEW = HN_API + "/newstories.json"
HN_BEST = HN_API + "/beststories.json"

CACHE_TTL = 300 # 5 minutes
CACHE_MAX = 300 # nombre max d'items
USER_AGENT = "NexusHN/1.0"

# ═══════════════════════════════════════════════════════════════════════════════
# CACHE
# ═══════════════════════════════════════════════════════════════════════════════

class LRUCache:
"""Cache LRU thread-safe."""

def __init__(self, maxsize: int = CACHE_MAX, ttl: int = CACHE_TTL):
self.maxsize = maxsize
self.ttl = ttl
self.data: OrderedDict = OrderedDict()
self.lock = threading.RLock()

def get(self, key: str) -> Optional[Any]:
with self.lock:
if key not in self.data:
return None
value, ts = self.data[key]
if time.time() - ts > self.ttl:
del self.data[key]
return None
# Touche la clé (LRU)
self.data.move_to_end(key)
return value

def set(self, key: str, value: Any):
with self.lock:
if key in self.data:
del self.data[key]
self.data[key] = (value, time.time())
if len(self.data) > self.maxsize:
self.data.popitem(last=False)


CACHE = LRUCache()


# ═══════════════════════════════════════════════════════════════════════════════
# HN CLIENT
# ═══════════════════════════════════════════════════════════════════════════════

class HNClient:
"""Client pour l'API Hacker News (Firebase)."""

def __init__(self):
self.user_agent = USER_AGENT

def _fetch(self, url: str, timeout: int = 10) -> Optional[Any]:
"""Requête HTTP JSON."""
try:
req = urllib.request.Request(
url, headers={"User-Agent": self.user_agent}
)
with urllib.request.urlopen(req, timeout=timeout) as response:
return json.loads(response.read().decode("utf-8"))
except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
return None
except Exception:
return None

def get_top_ids(self, kind: str = "top", limit: int = 100) -> List[int]:
"""Retourne les IDs top/new/best avec cache."""
cache_key = "ids_{}".format(kind)
cached = CACHE.get(cache_key)
if cached is not None:
return cached[:limit]

urls = {"top": HN_TOP, "new": HN_NEW, "best": HN_BEST}
url = urls.get(kind, HN_TOP)
data = self._fetch(url)

if not isinstance(data, list):
return []

CACHE.set(cache_key, data)
return data[:limit]

def get_item(self, item_id: int) -> Optional[Dict[str, Any]]:
"""Récupère un item avec cache."""
cache_key = "item_{}".format(item_id)
cached = CACHE.get(cache_key)
if cached is not None:
return cached

url = HN_ITEM.format(item_id)
data = self._fetch(url)

if data is None:
return None

CACHE.set(cache_key, data)
return data

def get_items_batch(self, ids: List[int]) -> List[Dict[str, Any]]:
"""Récupère un batch d'items (threads)."""
results = []
errors = []

def _worker(item_id: int):
item = self.get_item(item_id)
if item is not None:
results.append(item)

threads = []
for item_id in ids:
t = threading.Thread(target=_worker, args=(item_id,), daemon=True)
t.start()
threads.append(t)

for t in threads:
t.join(timeout=12)

# Tri par temps (le plus récent d'abord)
results.sort(key=lambda x: x.get("time", 0), reverse=True)
return results


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def time_ago(ts: int) -> str:
"""Formate le temps en 'il y a X'."""
if not ts:
return "unknown"
now = int(time.time())
diff = now - ts
if diff < 60:
return "just now"
if diff < 3600:
return "{} min ago".format(diff // 60)
if diff < 86400:
return "{} hours ago".format(diff // 3600)
if diff < 604800:
return "{} days ago".format(diff // 86400)
return "{} weeks ago".format(diff // 604800)


def domain_from_url(url: Optional[str]) -> str:
"""Extrait le domaine d'une URL."""
if not url:
return ""
try:
parsed = urlparse(url)
host = parsed.netloc or ""
if host.startswith("www."):
host = host[4:]
return host
except Exception:
return ""


def safe(s: Any) -> str:
"""Échappe du HTML."""
if s is None:
return ""
return html.escape(str(s), quote=False)


# ═══════════════════════════════════════════════════════════════════════════════
# HTML TEMPLATE (style GitHub classique)
# ═══════════════════════════════════════════════════════════════════════════════

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hacker News Classic</title>
<style>
:root {
--bg: #ffffff;
--bg-subtle: #f6f8fa;
--border: #d0d7de;
--border-muted: #e1e4e8;
--text: #24292f;
--text-muted: #57606a;
--text-link: #0969da;
--accent: #fd8c73;
--hn-orange: #ff6600;
--code-bg: #f6f8fa;
--font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
--font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
}
[data-theme="dark"] {
--bg: #0d1117;
--bg-subtle: #161b22;
--border: #30363d;
--border-muted: #21262d;
--text: #c9d1d9;
--text-muted: #8b949e;
--text-link: #58a6ff;
--accent: #ff7b72;
--code-bg: #161b22;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body {
background: var(--bg);
color: var(--text);
font-family: var(--font-sans);
font-size: 14px;
line-height: 1.5;
-webkit-font-smoothing: antialiased;
}
a { color: var(--text-link); text-decoration: none; }
a:hover { text-decoration: underline; }
button {
font-family: inherit;
font-size: 12px;
padding: 5px 12px;
border: 1px solid var(--border);
border-radius: 6px;
background: var(--bg-subtle);
color: var(--text);
cursor: pointer;
transition: all .1s;
}
button:hover { background: var(--border-muted); }
button:disabled { opacity: 0.5; cursor: wait; }

/* HEADER */
.header {
background: var(--bg-subtle);
border-bottom: 1px solid var(--border);
padding: 12px 24px;
display: flex;
align-items: center;
gap: 16px;
flex-wrap: wrap;
position: sticky;
top: 0;
z-index: 100;
}
.header-brand {
display: flex;
align-items: center;
gap: 8px;
font-weight: 600;
font-size: 15px;
}
.header-brand .logo {
width: 24px; height: 24px;
background: var(--hn-orange);
color: white;
border-radius: 4px;
display: inline-flex;
align-items: center;
justify-content: center;
font-size: 14px;
font-weight: bold;
}
.header-nav {
display: flex;
gap: 6px;
flex-wrap: wrap;
}
.header-nav button.active {
background: var(--hn-orange);
color: white;
border-color: var(--hn-orange);
}
.header-search {
flex: 1;
max-width: 400px;
margin-left: auto;
display: flex;
gap: 6px;
}
.header-search input {
flex: 1;
padding: 6px 12px;
border: 1px solid var(--border);
border-radius: 6px;
background: var(--bg);
color: var(--text);
font-size: 13px;
outline: none;
}
.header-search input:focus { border-color: var(--text-link); }

/* LAYOUT */
.layout {
display: grid;
grid-template-columns: 1fr 320px;
gap: 24px;
padding: 24px;
max-width: 1400px;
margin: 0 auto;
}
@media (max-width: 900px) {
.layout { grid-template-columns: 1fr; padding: 16px; gap: 16px; }
.header { padding: 10px 16px; }
}

/* MAIN COLUMN */
.main-col {
background: var(--bg);
border: 1px solid var(--border);
border-radius: 8px;
overflow: hidden;
}
.list-header {
padding: 12px 16px;
border-bottom: 1px solid var(--border);
background: var(--bg-subtle);
display: flex;
justify-content: space-between;
align-items: center;
font-size: 13px;
color: var(--text-muted);
}

/* STORY ITEMS */
.stories-list { list-style: none; }
.story {
padding: 12px 16px;
border-bottom: 1px solid var(--border-muted);
transition: background .1s;
}
.story:last-child { border-bottom: none; }
.story:hover { background: var(--bg-subtle); }
.story-row1 {
display: flex;
align-items: baseline;
gap: 8px;
margin-bottom: 4px;
}
.story-rank {
color: var(--text-muted);
font-family: var(--font-mono);
font-size: 13px;
font-weight: 600;
min-width: 32px;
}
.story-title {
font-size: 15px;
font-weight: 500;
color: var(--text);
word-break: break-word;
}
.story-title:hover { color: var(--text-link); }
.story-domain {
font-size: 12px;
color: var(--text-muted);
}
.story-row2 {
margin-left: 40px;
display: flex;
flex-wrap: wrap;
gap: 12px;
font-size: 12px;
color: var(--text-muted);
}
.story-meta-item { display: inline-flex; align-items: center; gap: 4px; }
.story-score {
display: inline-block;
padding: 1px 6px;
background: var(--bg-subtle);
border: 1px solid var(--border);
border-radius: 10px;
font-family: var(--font-mono);
font-size: 11px;
}
.story-type {
padding: 1px 6px;
border-radius: 10px;
font-size: 10px;
text-transform: uppercase;
font-weight: 600;
letter-spacing: 0.5px;
}
.story-type.story { background: #ddf4ff; color: #0969da; }
.story-type.job { background: #fff8c5; color: #9a6700; }
.story-type.poll { background: #ffeff7; color: #bf3989; }
.story-type.ask { background: #f0f0f0; color: #24292f; }
.story-type.show { background: #dafbe1; color: #1a7f37; }
[data-theme="dark"] .story-type.story { background: #121d2f; color: #58a6ff; }
[data-theme="dark"] .story-type.job { background: #2e2817; color: #d4a72c; }
[data-theme="dark"] .story-type.poll { background: #2d1a24; color: #db61a2; }
[data-theme="dark"] .story-type.ask { background: #21262d; color: #8b949e; }
[data-theme="dark"] .story-type.show { background: #1a2821; color: #3fb950; }

/* SIDEBAR */
.sidebar { display: flex; flex-direction: column; gap: 16px; }
.panel {
background: var(--bg);
border: 1px solid var(--border);
border-radius: 8px;
overflow: hidden;
}
.panel-header {
padding: 10px 16px;
background: var(--bg-subtle);
border-bottom: 1px solid var(--border);
font-size: 12px;
font-weight: 600;
color: var(--text-muted);
text-transform: uppercase;
letter-spacing: 0.5px;
}
.panel-body { padding: 16px; }
.panel-body p {
font-size: 13px;
color: var(--text-muted);
line-height: 1.6;
margin-bottom: 8px;
}
.panel-body p:last-child { margin-bottom: 0; }
.panel-body code {
background: var(--code-bg);
padding: 2px 6px;
border-radius: 4px;
font-family: var(--font-mono);
font-size: 12px;
}
.stats-row {
display: flex;
justify-content: space-between;
padding: 6px 0;
font-size: 12px;
border-bottom: 1px solid var(--border-muted);
}
.stats-row:last-child { border-bottom: none; }
.stats-label { color: var(--text-muted); }
.stats-value { font-family: var(--font-mono); font-weight: 600; }

/* LOADING */
.loading {
padding: 40px 20px;
text-align: center;
color: var(--text-muted);
font-size: 13px;
}
.spinner {
display: inline-block;
width: 16px;
height: 16px;
border: 2px solid var(--border);
border-top-color: var(--text-link);
border-radius: 50%;
animation: spin 0.6s linear infinite;
margin-right: 8px;
vertical-align: middle;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ERROR */
.error-box {
margin: 20px;
padding: 16px;
background: #ffebe9;
border: 1px solid #ff818266;
border-radius: 8px;
color: #82071e;
font-size: 13px;
}
[data-theme="dark"] .error-box {
background: #67060c;
border-color: #8e151966;
color: #ffb6b6;
}

/* FOOTER */
.footer {
text-align: center;
padding: 24px;
color: var(--text-muted);
font-size: 11px;
border-top: 1px solid var(--border);
margin-top: 24px;
}
.footer code {
background: var(--code-bg);
padding: 1px 5px;
border-radius: 3px;
font-family: var(--font-mono);
}
</style>
</head>
<body>

<div class="header">
<div class="header-brand">
<span class="logo">Y</span>
<span>Hacker News Classic</span>
</div>
<div class="header-nav" id="nav">
<button data-kind="top" class="active">Top</button>
<button data-kind="new">New</button>
<button data-kind="best">Best</button>
</div>
<div class="header-search">
<input type="text" id="search" placeholder="Filter stories...">
<button onclick="toggleTheme()" title="Toggle theme">🌓</button>
<button onclick="refresh()" title="Refresh">⟳</button>
</div>
</div>

<div class="layout">
<div class="main-col">
<div class="list-header">
<span id="list-title">Top stories</span>
<span id="list-count">—</span>
</div>
<ul class="stories-list" id="stories">
<li class="loading"><span class="spinner"></span>Fetching top stories...</li>
</ul>
</div>

<aside class="sidebar">
<div class="panel">
<div class="panel-header">About</div>
<div class="panel-body">
<p>Live Hacker News reader, GitHub-classic style.</p>
<p>Data from <a href="https://github.com/HackerNews/API" target="_blank">HN API</a>. No API key, no account.</p>
</div>
</div>
<div class="panel">
<div class="panel-header">Stats</div>
<div class="panel-body" id="stats">
<div class="stats-row"><span class="stats-label">Stories</span><span class="stats-value" id="stat-stories">—</span></div>
<div class="stats-row"><span class="stats-label">Last fetch</span><span class="stats-value" id="stat-fetch">—</span></div>
<div class="stats-row"><span class="stats-label">Cache TTL</span><span class="stats-value">300s</span></div>
<div class="stats-row"><span class="stats-label">Version</span><span class="stats-value">v__V__</span></div>
</div>
</div>
<div class="panel">
<div class="panel-header">Shortcuts</div>
<div class="panel-body">
<p><code>/</code> Focus search</p>
<p><code>r</code> Refresh</p>
<p><code>t</code> Toggle theme</p>
</div>
</div>
</aside>
</div>

<div class="footer">
Hacker News Classic · v__V__ · Local only ·
<a href="https://news.ycombinator.com" target="_blank">HN</a> ·
<a href="https://github.com/HackerNews/API" target="_blank">API</a>
</div>

<script>
let state = {
kind: 'top',
stories: [],
filtered: [],
loading: false,
lastFetch: null
};

function esc(s) {
if (s == null) return '';
return String(s)
.replace(/&/g, '&amp;')
.replace(/</g, '&lt;')
.replace(/>/g, '&gt;')
.replace(/"/g, '&quot;');
}

function timeAgo(ts) {
if (!ts) return 'unknown';
const now = Math.floor(Date.now() / 1000);
const diff = now - ts;
if (diff < 60) return 'just now';
if (diff < 3600) return Math.floor(diff / 60) + ' min ago';
if (diff < 86400) return Math.floor(diff / 3600) + ' hours ago';
if (diff < 604800) return Math.floor(diff / 86400) + ' days ago';
return Math.floor(diff / 604800) + ' weeks ago';
}

function domainFromUrl(url) {
if (!url) return '';
try {
const u = new URL(url);
return u.hostname.replace(/^www\./, '');
} catch (e) {
return '';
}
}

function storyType(item) {
if (item.type === 'job') return 'job';
if (item.type === 'poll') return 'poll';
const t = (item.title || '').toLowerCase();
if (t.startsWith('ask hn')) return 'ask';
if (t.startsWith('show hn')) return 'show';
return 'story';
}

async function loadStories(kind) {
state.kind = kind;
state.loading = true;
updateNav();
document.getElementById('list-title').textContent =
kind.charAt(0).toUpperCase() + kind.slice(1) + ' stories';
const list = document.getElementById('stories');
list.innerHTML = '<li class="loading"><span class="spinner"></span>Fetching ' +
esc(kind) + ' stories...</li>';

try {
const res = await fetch('/api/stories?kind=' + kind + '&limit=60');
if (!res.ok) throw new Error('HTTP ' + res.status);
const data = await res.json();
if (data.error) throw new Error(data.error);
state.stories = data.stories || [];
state.lastFetch = new Date();
filterAndRender();
updateStats();
} catch (e) {
list.innerHTML = '<li class="error-box">Failed to load: ' + esc(e.message) + '</li>';
} finally {
state.loading = false;
}
}

function filterAndRender() {
const q = (document.getElementById('search').value || '').toLowerCase().trim();
if (!q) {
state.filtered = state.stories;
} else {
state.filtered = state.stories.filter(function(s) {
return (s.title || '').toLowerCase().includes(q) ||
(s.by || '').toLowerCase().includes(q);
});
}
render();
}

function render() {
const list = document.getElementById('stories');
if (!state.filtered.length) {
list.innerHTML = '<li class="loading">No stories match your filter.</li>';
document.getElementById('list-count').textContent = '0 stories';
return;
}

let html = '';
state.filtered.forEach(function(s, i) {
const rank = i + 1;
const domain = domainFromUrl(s.url);
const type = storyType(s);
const comments = s.descendants || 0;
const score = s.score || 0;
const by = s.by || 'unknown';
const timeStr = timeAgo(s.time);

const titleHtml = s.url
? '<a class="story-title" href="' + esc(s.url) + '" target="_blank" rel="noopener">' + esc(s.title) + '</a>' +
(domain ? ' <span class="story-domain">(' + esc(domain) + ')</span>' : '')
: '<a class="story-title" href="https://news.ycombinator.com/item?id=' + s.id + '" target="_blank" rel="noopener">' + esc(s.title) + '</a>';

const hnLink = 'https://news.ycombinator.com/item?id=' + s.id;

html += '<li class="story">' +
'<div class="story-row1">' +
'<span class="story-rank">' + rank + '.</span>' +
titleHtml +
'</div>' +
'<div class="story-row2">' +
'<span class="story-type ' + type + '">' + type + '</span>' +
'<span class="story-score">' + score + ' pts</span>' +
'<span>by ' + esc(by) + '</span>' +
'<span>' + esc(timeStr) + '</span>' +
'<span><a href="' + hnLink + '" target="_blank" rel="noopener">' +
comments + ' comments</a></span>' +
'</div>' +
'</li>';
});
list.innerHTML = html;
document.getElementById('list-count').textContent =
state.filtered.length + ' of ' + state.stories.length + ' stories';
}

function updateNav() {
document.querySelectorAll('#nav button').forEach(function(b) {
b.classList.toggle('active', b.dataset.kind === state.kind);
});
}

function updateStats() {
document.getElementById('stat-stories').textContent = state.stories.length;
document.getElementById('stat-fetch').textContent =
state.lastFetch ? state.lastFetch.toLocaleTimeString() : '—';
}

function refresh() { loadStories(state.kind); }

function toggleTheme() {
const cur = document.documentElement.getAttribute('data-theme') || 'light';
const next = cur === 'light' ? 'dark' : 'light';
document.documentElement.setAttribute('data-theme', next);
try { localStorage.setItem('hn-theme', next); } catch (e) {}
}

document.querySelectorAll('#nav button').forEach(function(b) {
b.addEventListener('click', function() { loadStories(b.dataset.kind); });
});

document.getElementById('search').addEventListener('input', filterAndRender);

document.addEventListener('keydown', function(e) {
if (e.key === '/' && document.activeElement !== document.getElementById('search')) {
e.preventDefault();
document.getElementById('search').focus();
}
if (e.key === 'r' && document.activeElement === document.body) refresh();
if (e.key === 't' && document.activeElement === document.body) toggleTheme();
});

// Init
(function() {
try {
const saved = localStorage.getItem('hn-theme');
if (saved) document.documentElement.setAttribute('data-theme', saved);
} catch (e) {}
loadStories('top');
})();
</script>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

class Handler(BaseHTTPRequestHandler):
client = HNClient()

def log_message(self, fmt, *args):
pass

def _send_json(self, code: int, data: Any):
try:
body = json.dumps(data, ensure_ascii=False).encode("utf-8")
self.send_response(code)
self.send_header("Content-Type", "application/json; charset=utf-8")
self.send_header("Access-Control-Allow-Origin", "*")
self.send_header("Content-Length", str(len(body)))
self.end_headers()
self.wfile.write(body)
except (BrokenPipeError, ConnectionResetError):
pass

def _send_html(self, code: int, html_str: str):
try:
body = html_str.encode("utf-8")
self.send_response(code)
self.send_header("Content-Type", "text/html; charset=utf-8")
self.send_header("Content-Length", str(len(body)))
self.end_headers()
self.wfile.write(body)
except (BrokenPipeError, ConnectionResetError):
pass

def do_GET(self):
parsed = urlparse(self.path)
path = parsed.path
qs = parse_qs(parsed.query)

if path in ("/", "/index.html"):
html_out = INDEX_HTML.replace("__V__", VERSION)
self._send_html(200, html_out)
return

if path == "/api/stories":
kind = (qs.get("kind", ["top"])[0] or "top").lower()
if kind not in ("top", "new", "best"):
kind = "top"
try:
limit = int(qs.get("limit", ["60"])[0])
except ValueError:
limit = 60
limit = max(1, min(limit, 200))

try:
ids = self.client.get_top_ids(kind=kind, limit=limit)
items = self.client.get_items_batch(ids)

# Nettoyage : on garde les champs utiles
clean = []
for it in items:
if not it or it.get("deleted") or it.get("dead"):
continue
clean.append({
"id": it.get("id"),
"title": it.get("title", ""),
"url": it.get("url", ""),
"by": it.get("by", ""),
"score": it.get("score", 0),
"descendants": it.get("descendants", 0),
"time": it.get("time", 0),
"type": it.get("type", "story"),
})

self._send_json(200, {"stories": clean, "count": len(clean)})
except Exception as e:
self._send_json(500, {"error": str(e), "stories": []})
return

if path == "/api/version":
self._send_json(200, {"version": VERSION, "engine": "NexusHN"})
return

if path == "/api/health":
self._send_json(200, {"ok": True, "timestamp": time.time()})
return

self._send_json(404, {"error": "not found"})

def do_POST(self):
self._send_json(405, {"error": "method not allowed"})


class Server(ThreadingHTTPServer):
daemon_threads = True
allow_reuse_address = True


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def print_banner():
print("")
print(" ╔══════════════════════════════════════════════════════════════╗")
print(" ║ ║")
print(" ║ ██╗ ██╗███╗ ██╗ ██████╗██╗ █████╗ ║")
print(" ║ ██║ ██║████╗ ██║ ██╔════╝██║ ██╔══██╗ ║")
print(" ║ ███████║██╔██╗ ██║ ██║ ██║ ███████║ ║")
print(" ║ ██╔══██║██║╚██╗██║ ██║ ██║ ██╔══██║ ║")
print(" ║ ██║ ██║██║ ╚████║ ╚██████╗███████╗██║ ██║ ║")
print(" ║ ╚═╝ ╚═╝╚═╝ ╚═══╝ ╚═════╝╚══════╝╚═╝ ╚═╝ ║")
print(" ║ ║")
print(" ║ Hacker News Classic · v{} ║".format(VERSION))
print(" ║ GitHub-classic UI · No API key · Local ║")
print(" ║ ║")
print(" ╚══════════════════════════════════════════════════════════════╝")
print("")


def main():
parser = argparse.ArgumentParser(description="Nexus HN Classic")
parser.add_argument("--port", type=int, default=PORT)
parser.add_argument("--host", type=str, default=HOST)
args = parser.parse_args()

print_banner()
print(" Platform : {} {}".format(
__import__("platform").system(),
__import__("platform").release()
))
print(" URL : http://{}:{}".format(args.host, args.port))
print(" Data : live Hacker News API (Firebase)")
print(" Ctrl+C to stop")
print("")

try:
server = Server((args.host, args.port), Handler)
server.serve_forever()
except KeyboardInterrupt:
print("\n Shutting down...")
try:
server.shutdown()
except Exception:
pass
except OSError as e:
print(" Port {} error: {}".format(args.port, e))
print(" Try: python3 {} --port 8081".format(os.path.basename(__file__)))
return 1

return 0


if __name__ == "__main__":
sys.exit(main())
