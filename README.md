<div align="center">
  <h1>📰 NEXUS HN CLASSIC</h1>
  <p><strong>Hacker News, but in pure Python. Zero dependencies. GitHub-style UI.</strong></p>
  
  [![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](#)
  [![Dependencies](https://img.shields.io/badge/Dependencies-0-00ff9d?style=for-the-badge)](#)
  [![HN API](https://img.shields.io/badge/API-Hacker_News-FF6600?style=for-the-badge&logo=ycombinator&logoColor=white)](#)
  [![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](#)
</div>

---

## 🧬 Overview

**Nexus HN Classic** is a minimalist, zero-dependency Hacker News reader. 

While everyone builds heavy React/Next.js clients with 50MB of `node_modules`, this tool uses **Python's standard library** and a single file. It fetches live data from the official HN Firebase API, caches it smartly, and displays it in a clean, GitHub-inspired interface.

**The Rule:** *If you can build it in a single `.py` file, don't build it with a framework.*

---

## ⚙️ Features

- **Live Data:** Fetches top/new/best stories from the official HN API.
- **Zero Dependencies:** Uses only `urllib`, `json`, `http.server`, and `threading`.
- **Smart Caching:** Thread-safe LRU cache with TTL to avoid API rate limits.
- **Parallel Fetching:** Multi-threaded batch requests for blazing-fast loading.
- **GitHub-Classic UI:** Light/Dark theme, dense typography, 3-column layout.
- **Keyboard Shortcuts:** `/` to search, `r` to refresh, `t` to toggle theme.
- **Mobile-Ready:** Responsive layout for iPhone and Android.

---

## 🚀 Installation & Usage

### Prerequisites
- Python 3.10+ (already installed on Linux/macOS).

### Run
```bash
git clone https://github.com/Aissamohammedi88/nexus-hn-classic.git
cd nexus-hn-classic
python3 nexus-hn-classic.py
