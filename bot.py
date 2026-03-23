"""
TACHI Buy Tracker Bot — Base Network
- Monitors all buys of TACHI token on Base
- Telegram commands: /min0 /min5 /min10 /min50 /min100 /min500 /status /help
- Uniswap V4 compatible (tracks transfers to real wallets)
- Deploy on Railway: set env vars BOT_TOKEN, CHAT_ID
"""

import asyncio
import logging
import os
import time
import requests
from web3 import Web3
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  CONFIG (set as Railway env variables)
# ─────────────────────────────────────────────
BOT_TOKEN      = os.environ["BOT_TOKEN"]
CHAT_ID        = os.environ["CHAT_ID"]
TOKEN_CA       = os.environ.get("TOKEN_CA",       "0x39B4B879b8521d6A8C3a87cda64b969327b7fbA3")
TOKEN_NAME     = os.environ.get("TOKEN_NAME",     "TACHI")
TOKEN_SYMBOL   = os.environ.get("TOKEN_SYMBOL",   "TACHI")
TOKEN_DECIMALS = int(os.environ.get("TOKEN_DECIMALS", "18"))
BASE_RPC       = os.environ.get("BASE_RPC",       "https://mainnet.base.org")

BUY_LINK   = "https://swap.bankr.bot/?inputToken=ETH&outputToken=0x39b4b879b8521d6a8c3a87cda64b969327b7fba3"
CHART_LINK = "https://dexscreener.com/base/0xeefc0bd924650625a7edfcc64406689335cbabb82504f5d9b028a26754d90985"

state = {
    "min_usd":    float(os.environ.get("MIN_BUY_USD", "1.0")),
    "buys_posted": 0,
    "started_at":  time.time(),
    "last_block":  0,
}

# ─────────────────────────────────────────────
#  Emojis & visual bar
# ─────────────────────────────────────────────
def get_emoji(usd: float) -> str:
    if usd >= 10000: return "🐳🐳🐳"
    if usd >= 1000:  return "🐳🐳"
    if usd >= 500:   return "🐳"
    if usd >= 100:   return "🦈"
    if usd >= 50:    return "🐬"
    if usd >= 10:    return "🐠"
    return "🐟"

def get_bar(usd: float) -> str:
    filled = min(int(usd / 50), 10)
    return "🟢" * filled + "⬜" * (10 - filled)

# ─────────────────────────────────────────────
#  Web3
# ─────────────────────────────────────────────
w3 = Web3(Web3.HTTPProvider(BASE_RPC, request_kwargs={"timeout": 10}))

contract = w3.eth.contract(
    address=Web3.to_checksum_address(TOKEN_CA),
    abi=[{
        "name": "Transfer", "type": "event", "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "from",  "type": "address"},
            {"indexed": True,  "name": "to",    "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
    }],
)

# Uniswap Pair/LP address
LIQUIDITY_POOL = "0xeefc0bd924650625a7edfcc64406689335cbabb82504f5d9b028a26754d90985"

SKIP_ADDRESSES = {
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dEaD",
    "0x498581fF718922c3f8e6A244956aF099B2652b2b",  # Uniswap V4 PoolManager on Base
    "0x39B4B879b8521d6A8C3a87cda64b969327b7fbA3",  # TOKEN_CA
}

# Valid Senders updated based on the log
VALID_SENDERS = {
    "0xeefc0bd924650625a7edfcc64406689335cbabb82504f5d9b028a26754d90985", # The Pair
    "0x498581fF718922c3f8e6A244956aF099B2652b2b", # V4 PoolManager
    "0xdc5d8200a030798bc6227240f68b4dd9542686ef", # The Router
}

# A generic, aggressive buy filter
def is_likely_buy(sender: str, recipient: str) -> bool:
    # 1. Skip system/internal transfers
    is_recipient_skip = recipient.lower() in [s.lower() for s in SKIP_ADDRESSES]
    
    # 2. Aggressive filter: It's a buy if the recipient is NOT a system address.
    # The logs showed Recipient=0x5AaFc... which is a user wallet, 
    # but my filter was somehow returning False.
    is_recipient_valid = not is_recipient_skip
    
    log.info(f"DEBUG: Checking sender={sender} recipient={recipient} Skip={is_recipient_skip} Result={is_recipient_valid}")
    
    return is_recipient_valid

# Price — DexScreener (free, no key needed)
# ─────────────────────────────────────────────
_price_cache = {"price": 0.0, "ts": 0}

def get_price() -> float:
    now = time.time()
    if now - _price_cache["ts"] < 30:
        return _price_cache["price"]
    try:
        # Use a hardcoded full URL if BASE_RPC isn't used here, 
        # or verify the usage of requests here.
        # The crash might be coming from get_price() accessing an invalid URL
        # because I might be using an environment variable somewhere else.
        # Let's ensure this specific request is safe.
        r = requests.get(
            f"https://api.dexscreener.com/latest/dex/tokens/{TOKEN_CA}",
            timeout=5,
        )
        pairs = r.json().get("pairs") or []
        if pairs:
            price = float(pairs[0].get("priceUsd", 0))
            _price_cache.update({"price": price, "ts": now})
            return price
    except Exception as e:
        log.warning(f"Price fetch failed: {e}")
    return _price_cache["price"]

# Use ALCHEMY_RPC if provided, otherwise default to public
# Ensure we have a valid URL schema
BASE_RPC_RAW = os.environ.get("BASE_RPC", "https://mainnet.base.org")

if not BASE_RPC_RAW.startswith("http"):
    RPC_URL = f"https://base-mainnet.g.alchemy.com/v2/{BASE_RPC_RAW}"
else:
    RPC_URL = BASE_RPC_RAW

log.info(f"DEBUG: Using Final RPC_URL: {RPC_URL}")
w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 10}))

# ─────────────────────────────────────────────
#  Message builder
# ─────────────────────────────────────────────
def fmt(n: float) -> str:
    if n >= 1_000_000: return f"{n/1_000_000:.2f}M"
    if n >= 1_000:     return f"{n/1_000:.2f}K"
    return f"{n:,.2f}"

def build_message(event, tx_hash: str, price_usd: float) -> str:
    amount = event["args"]["value"] / (10 ** TOKEN_DECIMALS)
    usd    = amount * price_usd
    buyer  = event["args"]["to"]
    short  = f"{buyer[:6]}...{buyer[-4:]}"

    lines = [
        f"{get_emoji(usd)} *New Buy — {TOKEN_NAME} ${TOKEN_SYMBOL}*",
        "",
        get_bar(usd),
        "",
        f"🪙 Got: `{fmt(amount)} {TOKEN_SYMBOL}`",
        f"💵 Spent: `${fmt(usd)}`",
        f"💲 Price: `${price_usd:.8f}`",
        f"👤 Buyer: `{short}`",
        "",
        f"[🛒 Buy]({BUY_LINK}) | [📊 Chart]({CHART_LINK}) | [🔍 TX](https://basescan.org/tx/{tx_hash})",
    ]
    return "\n".join(lines)

# ─────────────────────────────────────────────
#  Commands
# ─────────────────────────────────────────────
async def set_min(update: Update, amount: float):
    state["min_usd"] = amount
    label = f"${amount:.0f}+" if amount > 0 else "ALL buys"
    await update.message.reply_text(
        f"✅ Min buy set to *{label}*",
        parse_mode=ParseMode.MARKDOWN,
    )

async def cmd_min0(u, c):   await set_min(u, 0)
async def cmd_min5(u, c):   await set_min(u, 5)
async def cmd_min10(u, c):  await set_min(u, 10)
async def cmd_min50(u, c):  await set_min(u, 50)
async def cmd_min100(u, c): await set_min(u, 100)
async def cmd_min500(u, c): await set_min(u, 500)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime_h = (time.time() - state["started_at"]) / 3600
    price = get_price()
    await update.message.reply_text(
        f"📡 *TACHI Bot Status*\n\n"
        f"⏱ Uptime: `{uptime_h:.1f}h`\n"
        f"📦 Last block: `{state['last_block']}`\n"
        f"💲 Price: `${price:.8f}`\n"
        f"🎯 Min buy: `${state['min_usd']:.0f}`\n"
        f"📣 Buys posted: `{state['buys_posted']}`",
        parse_mode=ParseMode.MARKDOWN,
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *TACHI Buy Bot Commands*\n\n"
        "/min0 — show ALL buys\n"
        "/min5 — $5+ only\n"
        "/min10 — $10+ only\n"
        "/min50 — $50+ only\n"
        "/min100 — $100+ only\n"
        "/min500 — $500+ only\n"
        "/status — bot stats\n"
        "/help — this message",
        parse_mode=ParseMode.MARKDOWN,
    )

# ─────────────────────────────────────────────
#  Watcher loop
# ─────────────────────────────────────────────
async def watcher_loop(bot: Bot):
    log.info("Watcher started")
    state["last_block"] = w3.eth.block_number - 1
    seen_txs: set = set()

    while True:
        try:
            current = w3.eth.block_number
            if current <= state["last_block"]:
                await asyncio.sleep(2)
                continue

# DEBUG: Log every transfer we see to verify filtering logic
            log.info(f"Checking blocks {state['last_block'] + 1} to {current}")
            
            try:
                events = contract.events.Transfer.get_logs(
                    fromBlock=state["last_block"] + 1,
                    toBlock=current,
                )
            except Exception as e:
                log.error(f"Error fetching logs: {e}")
                events = []

            if events:
                price = get_price()
                for event in events:
                    # Accessing event args properly depending on Web3 version
                    # If event args fails, log it
                    try:
                        tx_hash   = event["transactionHash"].hex()
                        sender    = event["args"]["from"]
                        recipient = event["args"]["to"]
                        value     = event["args"]["value"]
                    except KeyError as e:
                        log.error(f"KeyError accessing event args: {e}")
                        continue

                    # DEBUG
                    log.info(f"Transfer found: Sender={sender} Recipient={recipient} Val={value}")
                    
                    # LOGGING THE ADDRESSES TO FIND THE MISMATCH
                    log.info(f"LP={LIQUIDITY_POOL.lower()} Sender={sender.lower()} Recipient={recipient.lower()}")
                    log.info(f"Condition: {sender.lower() == LIQUIDITY_POOL.lower()}")

                    if tx_hash in seen_txs:
                        continue
                    if not is_likely_buy(sender, recipient):
                        continue

                    amount = event["args"]["value"] / (10 ** TOKEN_DECIMALS)
                    usd    = amount * price

                    if usd < state["min_usd"]:
                        continue

                    try:
                        await bot.send_message(
                            chat_id=CHAT_ID,
                            text=build_message(event, tx_hash, price),
                            parse_mode=ParseMode.MARKDOWN,
                            disable_web_page_preview=False,
                        )
                        state["buys_posted"] += 1
                        log.info(f"Buy posted ${usd:.2f} | {tx_hash}")
                    except Exception as e:
                        log.error(f"Send failed: {e}")

                    seen_txs.add(tx_hash)

            if len(seen_txs) > 5000:
                seen_txs = set(list(seen_txs)[-2000:])

            state["last_block"] = current

        except Exception as e:
            log.error(f"Watcher error: {e}")

        await asyncio.sleep(3)

# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("min0",   cmd_min0))
    app.add_handler(CommandHandler("min5",   cmd_min5))
    app.add_handler(CommandHandler("min10",  cmd_min10))
    app.add_handler(CommandHandler("min50",  cmd_min50))
    app.add_handler(CommandHandler("min100", cmd_min100))
    app.add_handler(CommandHandler("min500", cmd_min500))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("help",   cmd_help))

    async def post_init(app):
        asyncio.create_task(watcher_loop(app.bot))

    app.post_init = post_init
    log.info("Bot started")
    app.run_polling(allowed_updates=["message"])

if __name__ == "__main__":
    main()
