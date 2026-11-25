# ShopApp — Online Store inside Telegram (Mini App)

[Русская версия](README.ru.md) · **Live demo: [@shopnordicbot](https://t.me/shopnordicbot)**

A complete online store that opens right inside Telegram: catalog, cart, checkout and card payments — nothing to install. The owner receives orders in a chat and updates their status with buttons, and edits prices and stock in the store's **Admin** tab.

The demo is built for a fictional home goods store, **Nordic Home**. The catalog lives in `catalog.json`.

## Features

**Customer**
- Opens the store from a button in the chat or the blue **Shop** button next to the input field.
- Browses a catalog with categories and search; a product card shows the full description.
- The cart is kept even if the store is closed.
- Chooses delivery: courier, parcel locker or pickup. Free delivery from €50 is applied automatically, with a hint like "add €18 more for free delivery".
- Name and phone are remembered for the next order.
- Pays **by card inside Telegram** (when payments are connected) or **on pickup**.
- Sees their orders and statuses in "My orders"; status changes also arrive in the chat.
- The UI follows the user's Telegram light / dark theme.

**Owner**
- Gets every order in the chat: items, total, contacts and address.
- **📦 Mark shipped**, **✅ Mark delivered** and **❌ Cancel** buttons change the status, and the customer is notified instantly.
- `/admin` shows sales for today and the last 7 days, plus open orders.
- The **Admin** tab in the store edits prices and stock; customers see changes immediately.

**Security**
- Every request from the store is signed by Telegram, and the server verifies the signature with the bot key — users and orders can't be forged.
- **Prices are calculated on the server.** A price sent by the browser is ignored, so "buy for €0.01" doesn't work.
- Before charging, the bot re-checks the order and the amount (pre-checkout). An order can't be paid twice.
- Notifications are sent in the background, so checkout never waits for Telegram.

## Demo mode

With `DEMO_MODE=true` anyone can send `/admin` and see the owner side, but **only with their own** test orders. After ordering, the visitor gets an owner-style order card with working status buttons. The Admin tab is shown read-only.

## Card payments

Telegram Stars are only allowed for digital goods; physical goods are paid through a payment provider such as Stripe.

1. In @BotFather choose the bot → **Payments** → **Stripe** → **Connect Stripe TEST**.
2. Copy the token into `PAYMENT_PROVIDER_TOKEN` in `.env`.
3. Test with card `4242 4242 4242 4242`, any future expiry date and any CVC — no money is charged.

Without a token the store works in "pay on pickup" mode.

## Run locally

### Preview the store in a browser (no Telegram)

```powershell
.venv\Scripts\python dev_server.py
```

Open http://localhost:8080/app/. You are logged in as the owner, Telegram messages are skipped, and data goes to a separate `dev.db`. Handy for design work.

### Full run with the bot

Telegram opens Mini Apps **over HTTPS only**, so the full store works once it's deployed to a server.

1. Create a new bot in @BotFather.
2. In PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

3. Fill in `BOT_TOKEN`, `ADMIN_IDS` and `WEBAPP_URL` (a public URL like `https://your-domain/app/`) in `.env`.
4. Start:

```powershell
.venv\Scripts\python -m bot
```

One process runs both the bot and the web server on port 8080. The server (VPS, Railway, Render) must expose port 8080 over HTTPS.

> `DEV_MODE=true` is for local testing only. On a server it must be `false`, otherwise Telegram signature checks are skipped for local requests.

## Tests

```powershell
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```

24 tests covering:
- order totals and free delivery, rejecting client-side prices, stock and quantity checks;
- the API with real Telegram signatures: forged, expired or modified signatures are rejected;
- pay-on-pickup and card orders, the correct invoice amount;
- pre-checkout validation and double-payment protection;
- status changes and notifications, owner and demo-visitor access.

## Project structure

```
bot/
  __main__.py      runs the bot and the web server together
  config.py        settings from .env
  db.py            tables: products, orders, order_items
  repo.py          database queries, catalog.json loading
  pricing.py       order calculation (pure logic)
  web.py           store API + Telegram signature verification
  notify.py        messages to the customer and the owner
  texts.py         texts
  keyboards.py     buttons
  handlers/
    shop.py        /start, /orders, payments
    owner.py       /admin, order statuses
webapp/            store page: index.html, styles.css, app.js (no build step)
catalog.json       products, categories, delivery options
dev_server.py      browser preview without Telegram
tests/
```

## Tech stack

Python, aiogram 3, aiohttp, Telegram Mini Apps (WebApp API), Telegram Payments, SQLAlchemy 2, vanilla JavaScript, Docker, pytest.

## License

[MIT](LICENSE)
