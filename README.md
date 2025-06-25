# Opening Range Breakout Bot

This project implements a **production-ready trading algorithm** based on the **Opening Range Breakout** strategy for futures markets (e.g., MNQ), incorporating dynamic contract sizing, real-time order management via IBKR, and full performance tracking.

> ⚠️ **Disclaimer**: This repository is for educational purposes only. It contains code that interacts with live trading systems. Do not use in a live environment without understanding the risks and thoroughly testing in simulation.

---

## Overview

The Opening Range Breakout Bot enters trades based on the high/low of the 7:30–7:35am candle (MST) using 5-minute bars. It manages risk using bracket orders (stop loss and take profit) and scales position size based on cumulative net profits.

### Key Features
- 5-minute bar breakout detection
- Bracket OCO order placement (entry, stop, target)
- Dynamic position sizing based on net P&L
- Re-entry if the first trade hits the stop loss
- Cancels orders after 1:30pm if not triggered
- PostgreSQL-based performance tracking
- Clean modular structure (via internal `RiverRose` package)

---

## Project Structure

| File/Notebook | Description |
|---------------|-------------|
| `Opening_Range_Breakout_Bot.py` | The main trading bot that runs live in production (connects to IBKR and PostgreSQL) |
| `Notebook 1 - Backtesting Opening Range Strategy.ipynb` | Historical performance of the ORB strategy using CSV data |
| `Notebook 2 - Machine Learning on Model.ipynb` | Applies ML to improve entry quality or filter conditions |
| `Notebook 3 - Algorithm Performance Tracking.ipynb` | Visualizes realized trades and performance metrics |
| `mnq_backtesting_data.csv` | Historical price data used in notebooks |
| (Private) `RiverRose` Module | Internal utilities for IBKR interaction, database management, and strategy logic |

---

## Private Module Handling

This project imports a local module named `RiverRose`, which includes sensitive logic and credentials. You **will not be able to run** `Opening_Range_Breakout_Bot.py` or some notebooks unless you replicate or mock:

- `TradingApp` (extends `EWrapper`, `EClient`)
- Order management functions like `place_oca_bracket`, `usFut`, etc.
- Historical data access via IBKR API

> All private credentials (e.g., account numbers, passwords) are prompted interactively via `input()` — these are **not stored in code** or shared publicly.

---

## How to Use (Notebooks)

1. **Clone this repository**
2. **Open notebooks 1–3** in Jupyter, VSCode, or another interface
3. Ensure you have the dependencies:
```bash
pip install pandas numpy matplotlib scikit-learn sqlalchemy
```
4. For backtesting, notebooks run entirely offline using `mnq_backtesting_data.csv`.

---

## 🚧 Live Trading Caution

To run `Opening_Range_Breakout_Bot.py`, you must:
- Have **Interactive Brokers** installed and configured (TWS or Gateway)
- Have **PostgreSQL** running and configured (local or remote)
- Have access to the **`RiverRose` module**, which contains bot’s infrastructure

> This script is run as a **long-running process**, checking trading conditions every 3 seconds from 7:33am to 2:00pm MST.

---

## Author

**Thomas MacPherson**  
Quantitative Finance & Algorithmic Trading  
📬 [LinkedIn](https://www.linkedin.com/in/thomasmacpherson/)