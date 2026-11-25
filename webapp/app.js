/* Nordic Home — Telegram Mini App. Plain JavaScript, no build step. */
(() => {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp;
  const inTelegram = Boolean(tg && tg.initData);
  if (inTelegram) {
    document.documentElement.classList.add("tg");
    tg.ready();
    tg.expand();
  }

  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (cents) => "€" + (cents / 100).toFixed(2);
  const haptic = (kind) => { try { kind === "success" || kind === "error"
    ? tg.HapticFeedback.notificationOccurred(kind) : tg.HapticFeedback.impactOccurred("light"); } catch (e) { /* not in Telegram */ } };

  const store = {
    get(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (e) { return fallback; } },
    set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* private mode */ } },
  };

  const state = {
    data: null,
    byId: new Map(),
    cart: store.get("cart", {}),        // { productId: qty }
    category: "all",
    query: "",
    view: "shop",
    delivery: null,
    payment: "later",
    busy: false,
  };

  // ---------- API ----------
  async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json" };
    if (inTelegram) headers.Authorization = "tma " + tg.initData;
    const res = await fetch(path, { ...options, headers });
    let body = {};
    try { body = await res.json(); } catch (e) { /* empty body */ }
    if (!res.ok) throw new Error(body.error || `Error ${res.status}`);
    return body;
  }

  // ---------- main button (Telegram's native one, or a page button in a normal browser) ----------
  let mainHandler = null;
  const fab = $("#fab");
  fab.addEventListener("click", () => mainHandler && mainHandler());

  function setMain(text, handler, { progress = false } = {}) {
    if (inTelegram) {
      const mb = tg.MainButton;
      if (mainHandler) mb.offClick(mainHandler);
      mainHandler = handler;
      mb.setText(text);
      mb.onClick(handler);
      progress ? (mb.showProgress(), mb.disable()) : (mb.hideProgress(), mb.enable());
      mb.show();
    } else {
      mainHandler = handler;
      fab.textContent = progress ? "Please wait…" : text;
      fab.disabled = progress;
      fab.hidden = false;
    }
  }

  function hideMain() {
    if (inTelegram) {
      if (mainHandler) tg.MainButton.offClick(mainHandler);
      tg.MainButton.hide();
    } else {
      fab.hidden = true;
    }
    mainHandler = null;
  }

  function setBack(visible) {
    if (!inTelegram) return;
    visible ? tg.BackButton.show() : tg.BackButton.hide();
  }
  if (inTelegram) tg.BackButton.onClick(() => show("shop"));

  function toast(text) {
    const t = $("#toast");
    t.textContent = text;
    t.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { t.hidden = true; }, 2600);
  }

  // ---------- cart ----------
  function qty(id) { return state.cart[id] || 0; }

  function setQty(id, n) {
    const p = state.byId.get(id);
    if (!p) return;
    n = Math.max(0, Math.min(20, n));
    if (n === 0) delete state.cart[id]; else state.cart[id] = n;
    store.set("cart", state.cart);
    haptic();
    renderGrid();
    if (state.view === "cart") renderCart();
    if (!$("#sheet").hidden && Number($("#sheetCard").dataset.id) === id) openSheet(id);
    updateMain();
  }

  function cartLines() {
    return Object.entries(state.cart)
      .map(([id, n]) => ({ p: state.byId.get(Number(id)), qty: n }))
      .filter((l) => l.p && l.p.in_stock);
  }
  const itemsTotal = () => cartLines().reduce((s, l) => s + l.p.price * l.qty, 0);
  const itemsCount = () => cartLines().reduce((s, l) => s + l.qty, 0);
  const deliveryOf = () => state.data.deliveries.find((d) => d.id === state.delivery);
  const deliveryCost = (d, items) => (d.free_from && items >= d.free_from ? 0 : d.price);

  function stepper(id) {
    return `<div class="stepper"><button data-dec="${id}" aria-label="Less">−</button>` +
      `<span>${qty(id)}</span><button data-inc="${id}" aria-label="More">+</button></div>`;
  }
  const tint = (p) => `background: color-mix(in srgb, ${esc(p.color)} 45%, var(--bg))`;

  // ---------- shop ----------
  function renderChips() {
    const cats = [{ id: "all", name: "All" }, ...state.data.categories];
    $("#chips").innerHTML = cats.map((c) =>
      `<button class="chip ${c.id === state.category ? "active" : ""}" data-cat="${esc(c.id)}">${esc(c.name)}</button>`).join("");
  }

  function renderGrid() {
    const q = state.query.trim().toLowerCase();
    const items = state.data.products.filter((p) =>
      (state.category === "all" || p.category === state.category) &&
      (!q || p.name.toLowerCase().includes(q) || p.description.toLowerCase().includes(q)));
    $("#grid").innerHTML = items.map((p) => `
      <div class="card ${p.in_stock ? "" : "out"}">
        <button class="tile" style="${tint(p)}" data-open="${p.id}" aria-label="${esc(p.name)}">${esc(p.emoji)}</button>
        <div class="card-body">
          <div class="card-name">${esc(p.name)}</div>
          <div class="card-row">
            <span class="price">${money(p.price)}</span>
            ${!p.in_stock ? '<span class="out-label">Out of stock</span>'
              : qty(p.id) ? stepper(p.id) : `<button class="add" data-inc="${p.id}" aria-label="Add">+</button>`}
          </div>
        </div>
      </div>`).join("") || '<p class="state">Nothing found.</p>';
  }

  function openSheet(id) {
    const p = state.byId.get(id);
    const card = $("#sheetCard");
    card.dataset.id = id;
    card.innerHTML = `
      <div class="tile" style="${tint(p)}">${esc(p.emoji)}</div>
      <div class="sheet-body">
        <h2>${esc(p.name)}</h2>
        <p>${esc(p.description)}</p>
        <div class="sheet-row">
          <span class="price" style="font-size:20px">${money(p.price)}</span>
          ${!p.in_stock ? '<span class="out-label">Out of stock</span>'
            : qty(id) ? stepper(id) : `<button class="btn" style="margin:0" data-inc="${id}">Add to cart</button>`}
        </div>
      </div>`;
    $("#sheet").hidden = false;
  }

  // ---------- cart & checkout ----------
  function renderCart() {
    const lines = cartLines();
    const items = itemsTotal();
    if (!lines.length) {
      $("#cartLines").innerHTML = '<p class="state">Your cart is empty.</p>';
    } else {
      $("#cartLines").innerHTML = lines.map(({ p }) => `
        <div class="line">
          <div class="mini" style="${tint(p)}">${esc(p.emoji)}</div>
          <div class="info"><div>${esc(p.name)}</div><small class="hint">${money(p.price)}</small></div>
          ${stepper(p.id)}
        </div>`).join("");
    }

    $("#deliveries").innerHTML = state.data.deliveries.map((d) => {
      const cost = deliveryCost(d, items);
      const label = cost ? money(cost) : '<span class="free">Free</span>';
      const more = d.free_from && cost ? `<small>Free from ${money(d.free_from)} — add ${money(d.free_from - items)} more</small>` : "";
      return `<button class="option ${d.id === state.delivery ? "active" : ""}" data-delivery="${esc(d.id)}">
        <div class="grow">${esc(d.name)}<small>${esc(d.eta)}</small>${more}</div><div>${label}</div></button>`;
    }).join("");

    const pays = state.data.payments_enabled
      ? [["card", "💳 Pay now by card", "Secure payment inside Telegram"], ["later", "💶 Pay on pickup / delivery", "Cash or card"]]
      : [["later", "💶 Pay on pickup / delivery", "Cash or card"]];
    if (!state.data.payments_enabled) state.payment = "later";
    $("#payments").innerHTML = pays.map(([id, title, sub]) =>
      `<button class="option ${id === state.payment ? "active" : ""}" data-payment="${id}">
        <div class="grow">${title}<small>${sub}</small></div></button>`).join("");

    const d = deliveryOf();
    const dCost = deliveryCost(d, items);
    $("#totals").innerHTML = `
      <div><span>Items</span><span>${money(items)}</span></div>
      <div><span>Delivery</span><span>${dCost ? money(dCost) : '<span class="free">Free</span>'}</span></div>
      <div class="sum"><span>Total</span><span>${money(items + dCost)}</span></div>`;
    $("#addressField").hidden = d.id === "pickup";
  }

  function formValues() {
    const f = $("#form");
    return Object.fromEntries(["name", "phone", "address", "comment"].map((k) => [k, f.elements[k].value.trim()]));
  }

  function showError(msg) {
    const e = $("#error");
    e.textContent = msg;
    e.hidden = !msg;
    if (msg) { e.scrollIntoView({ behavior: "smooth", block: "center" }); haptic("error"); }
  }

  function validate(v) {
    const f = $("#form");
    const needAddress = state.delivery !== "pickup";
    const bad = {
      name: !v.name,
      phone: !/^\+?[0-9 ()-]{5,20}$/.test(v.phone),
      address: needAddress && !v.address,
    };
    for (const [k, isBad] of Object.entries(bad)) f.elements[k].classList.toggle("invalid", isBad);
    if (bad.name) return "Please enter your name.";
    if (bad.phone) return "Please enter a valid phone number.";
    if (bad.address) return "Please enter the delivery address.";
    return "";
  }

  async function checkout() {
    if (state.busy) return;
    const v = formValues();
    const problem = validate(v);
    if (problem) return showError(problem);
    showError("");
    state.busy = true;
    updateMain();
    try {
      const res = await api("/api/orders", {
        method: "POST",
        body: JSON.stringify({
          items: cartLines().map((l) => ({ id: l.p.id, qty: l.qty })),
          delivery: state.delivery, payment: state.payment, ...v,
        }),
      });
      if (res.invoice_url) {
        if (!inTelegram) { toast("Card payment works only inside Telegram"); return; }
        tg.openInvoice(res.invoice_url, (status) => {
          if (status === "paid") done(res.order_id, true);
          else if (status === "failed") showError("The payment failed. Please try again or choose pay on pickup.");
          else toast("Payment cancelled");
        });
      } else {
        done(res.order_id, false);
      }
    } catch (err) {
      showError(err.message);
    } finally {
      state.busy = false;
      updateMain();
    }
  }

  function done(orderId, paid) {
    state.cart = {};
    store.set("cart", state.cart);
    store.set("contact", formValues());
    $("#doneTitle").textContent = paid ? `Order #${orderId} is paid!` : `Order #${orderId} placed!`;
    haptic("success");
    renderGrid();
    show("done");
  }

  // ---------- orders ----------
  const STATUS = { new: "New", paid: "Paid", shipped: "Shipped", done: "Delivered", cancelled: "Cancelled" };

  async function renderOrders() {
    const list = $("#ordersList");
    list.innerHTML = '<p class="state">Loading…</p>';
    try {
      const { orders } = await api("/api/orders");
      list.innerHTML = orders.map((o) => `
        <div class="order">
          <div class="order-head"><b>Order #${o.id}</b><span class="status ${o.status}">${STATUS[o.status] || o.status}</span></div>
          <div>${o.items.map((i) => `${esc(i.emoji)} ${esc(i.name)} × ${i.qty}`).join("<br>")}</div>
          <small>${esc(o.created_at)} · ${esc(o.delivery)} · <b>${money(o.total)}</b></small>
        </div>`).join("") || '<p class="state">No orders yet.</p>';
    } catch (err) {
      list.innerHTML = `<p class="state">${esc(err.message)}</p>`;
    }
  }

  // ---------- admin ----------
  function renderAdmin() {
    const canEdit = state.data.is_admin;
    $("#adminNote").textContent = canEdit
      ? "Change a price or stock and tap Save — customers see it immediately."
      : "🧪 Demo: read-only. In a real shop the owner edits prices and stock right here.";
    $("#adminList").innerHTML = state.data.products.map((p) => `
      <div class="arow" data-row="${p.id}">
        <div class="mini" style="${tint(p)}">${esc(p.emoji)}</div>
        <div class="name">${esc(p.name)}</div>
        <input type="number" step="0.01" min="0.01" value="${(p.price / 100).toFixed(2)}" ${canEdit ? "" : "disabled"} aria-label="Price">
        <label><input type="checkbox" ${p.in_stock ? "checked" : ""} ${canEdit ? "" : "disabled"}>in stock</label>
        ${canEdit ? `<button class="save" data-save="${p.id}">Save</button>` : ""}
      </div>`).join("");
  }

  async function saveProduct(id) {
    const row = document.querySelector(`[data-row="${id}"]`);
    const price = Math.round(parseFloat(row.querySelector("input[type=number]").value) * 100);
    const inStock = row.querySelector("input[type=checkbox]").checked;
    if (!Number.isFinite(price) || price < 1) return toast("Enter a valid price");
    try {
      const { product } = await api(`/api/admin/products/${id}`, {
        method: "PATCH", body: JSON.stringify({ price, in_stock: inStock }),
      });
      Object.assign(state.byId.get(id), product);
      haptic("success");
      toast("Saved");
      renderGrid();
    } catch (err) {
      toast(err.message);
    }
  }

  // ---------- navigation ----------
  function updateMain() {
    if (state.view === "cart" && itemsCount()) {
      const total = itemsTotal() + deliveryCost(deliveryOf(), itemsTotal());
      const label = state.payment === "card" ? `Pay ${money(total)}` : `Place order · ${money(total)}`;
      setMain(label, checkout, { progress: state.busy });
    } else if ((state.view === "shop" || state.view === "cart") && itemsCount()) {
      setMain(`View cart · ${itemsCount()} · ${money(itemsTotal())}`, () => show("cart"));
    } else {
      hideMain();
    }
  }

  function show(view) {
    state.view = view;
    for (const s of document.querySelectorAll(".view")) s.hidden = s.id !== `view-${view}`;
    for (const b of document.querySelectorAll("#tabs button")) b.classList.toggle("active", b.dataset.view === view);
    $("#sheet").hidden = true;
    if (view === "cart") renderCart();
    if (view === "orders") renderOrders();
    if (view === "admin") renderAdmin();
    setBack(view === "cart" || view === "done");
    updateMain();
    window.scrollTo(0, 0);
  }

  // ---------- events ----------
  document.addEventListener("click", (e) => {
    const t = e.target.closest("button, [data-close]");
    if (!t) return;
    const d = t.dataset;
    if (d.inc) setQty(Number(d.inc), qty(Number(d.inc)) + 1);
    else if (d.dec) setQty(Number(d.dec), qty(Number(d.dec)) - 1);
    else if (d.open) openSheet(Number(d.open));
    else if (d.cat) { state.category = d.cat; renderChips(); renderGrid(); }
    else if (d.view) show(d.view);
    else if (d.delivery) { state.delivery = d.delivery; haptic(); renderCart(); updateMain(); }
    else if (d.payment) { state.payment = d.payment; haptic(); renderCart(); updateMain(); }
    else if (d.save) saveProduct(Number(d.save));
    else if ("close" in d) $("#sheet").hidden = true;
  });
  $("#search").addEventListener("input", (e) => { state.query = e.target.value; renderGrid(); });
  $("#doneBack").addEventListener("click", () => show("shop"));
  $("#form").addEventListener("input", (e) => {
    e.target.classList.remove("invalid");
    store.set("contact", formValues());
  });

  // ---------- start ----------
  async function start() {
    try {
      state.data = await api("/api/bootstrap");
    } catch (err) {
      $("#state").textContent = err.message;
      return;
    }
    $("#state").hidden = true;
    document.title = state.data.shop;
    state.data.products.forEach((p) => state.byId.set(p.id, p));
    state.delivery = state.data.deliveries[0].id;
    $("#adminTab").hidden = !(state.data.is_admin || state.data.demo);

    const contact = store.get("contact", {});
    const f = $("#form");
    for (const k of ["name", "phone", "address", "comment"]) if (contact[k]) f.elements[k].value = contact[k];
    if (!f.elements.name.value && state.data.user.first_name) f.elements.name.value = state.data.user.first_name;

    renderChips();
    renderGrid();
    show("shop");
  }
  start();
})();
