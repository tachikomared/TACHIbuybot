# 🦀 TACHI Buy Tracker Bot

A high-performance Telegram buy tracker built for the Base Network, optimized for Uniswap V4. It monitors your token transfers in real-time, filters them for actual buy trades, and posts formatted alerts with dynamic crab-based 🦀 visuals.

## Features
- **Real-time Monitoring:** Tracks all transfers on Base network.
- **Aggressive Buy Filtering:** Filters out internal pool rebalances, showing only true user buys.
- **Dynamic Visuals:** Shows buy size with 🦀 emojis.
- **Interactive:** Telegram command support (`/min0` to `/min500` thresholds, `/status`).
- **Media Ready:** Automatically posts your custom TACHI logo with every buy alert.

## Prerequisites
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather)).
- A Telegram Group ID (e.g., `-100123456789`).
- A Base RPC URL (Alchemy, QuickNode, or Infura).

## Deployment (Railway)

1. **Deploy to Railway:** Click the deploy button (if your repo is connected).
2. **Environment Variables:** Set the following in your service's **Variables** tab:

| Variable | Description | Example |
| :--- | :--- | :--- |
| `BOT_TOKEN` | Your Telegram Bot Token | `8713131183:AAFv...` |
| `CHAT_ID` | Your Group numeric ID | `-1002381931352` |
| `BASE_RPC` | Full HTTPS URL from Node Provider | `https://base-mainnet.g.alchemy.com/v2/...` |
| `TOKEN_CA` | Token Contract Address | `0x39B4B879b8521d6A8C3a87cda64b969327b7fbA3` |
| `MIN_BUY_USD` | Minimum USD value to post | `1.0` |

3. **Telegram Setup:** 
   - Add the bot to your Telegram group.
   - **Crucial:** Promote the bot to **Administrator** so it has permission to send messages and photos.

## Commands

| Command | Action |
| :--- | :--- |
| `/status` | View bot uptime, price, and stats. |
| `/min[0/5/10/50/100/500]` | Set the minimum USD value to trigger an alert. |
| `/help` | Display command list. |

---

## Customization
- **Images:** Replace `media/tachi.jpg` in the repository to update your bot's alert image.
- **Logic:** The `is_likely_buy` function in `bot.py` is configured for aggressive detection; adjust `SKIP_ADDRESSES` if you need to filter specific smart contracts.
