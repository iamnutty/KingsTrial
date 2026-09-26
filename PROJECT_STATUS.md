# Kings Trial - Project Status & Pre-Refactor Roadmap

> **Snapshot Date:** September 2026  
> **Repository Baseline:** Pygame Desktop Engine (`v1.0.0-legacy-pygame`)

---

## 📌 Executive Summary

This document serves as an authoritative reference for future developers and AI context (LLMs) reviewing the legacy Pygame codebase before and during the major web-enabled refactor.

---

## 🎮 Current State & Core Strengths

- **Gameplay Core:** Gameplay mechanics are fully functional and verified bug-free.
- **Visuals & Audio:** UI layout, sprite graphics, color themes, sound effects, and music are fully implemented, responsive, and provide a strong baseline player experience.
- **AI Integration:** Stockfish engine is integrated and operational for local single-player against AI.

---

## ⚠️ Known Issues & Technical Debt

1. **macOS Build Bugs:**
   - Distribution builds on macOS still exhibit execution bugs and Gatekeeper/quarantine issues during runtime.
2. **Online Multiplayer Disconnect Edge Cases:**
   - Over-the-internet multiplayer (`network/` & `server/`) requires robust reconnection logic, timeouts, and state recovery when either player disconnects unexpectedly.
3. **AI Tuning (Stockfish):**
   - While Stockfish functions well, its position evaluation heuristics need further tuning/customization to account for King's Trial custom mechanics (shrinking board zones, piece evolution/upgrades, neutral piece tactics).
4. **Codebase Architecture ("Vibe Coded" Legacy):**
   - The original Pygame version was rapidly developed ("vibe coded"). Game state, rendering, input handling, and socket network logic are tightly coupled in places (`game_state.py`, `app.py`). A strong cleanup and separation of concerns is needed.

---

## 💡 Gameplay & UX Enhancement Backlog

- **Haptics & Immediate Feedback:** Add tactile/haptic feedback (for mobile/controllers) and immediate visual/audio reward cues on captures, promotions, and survival moves to make gameplay feel punchier.

---

## 🚀 Major Overhaul Goals (Web-Enabled Transition)

1. **Platform Agnostic / Web Enabled:**
   - Transition the game from Pygame (desktop-only) to a web engine (HTML5 Canvas / TypeScript / JS framework like Phaser, PixiJS, or React/Vue) to run seamlessly on browsers, iOS, Android, macOS, and Windows without platform packaging bugs.
2. **Web-Compatible Engine & Stockfish:**
   - Leverage Stockfish compiled to WebAssembly (Stockfish.js / WASM) or a lightweight web-compatible chess engine.
   - Retain full Stockfish evaluation power while running client-side in browser or mobile webview.
3. **Decoupled Game Engine Core:**
   - Extract game rules, board logic, shrink mechanics, and move validation into a pure, headless JavaScript/TypeScript module free of DOM/rendering dependencies.

---

## 🛠️ Repository Branching & Tagging Reference

- **Pre-Refactor Tag:** `v1.0.0-pre-refactor`
- **Refactor Branch:** `refactor/web-migration`
- **Legacy Pygame Branch:** `main` (or `legacy/pygame-v1`)
