const pesos = (value) =>
  new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" }).format(Number(value) || 0);

const chatEl = document.querySelector("#chat");
const traceEl = document.querySelector("#trace");
const banner = document.querySelector("#banner");
const followEl = document.querySelector("#followup");
const composer = document.querySelector("#composer");
const sendBtn = document.querySelector("#send-btn");
const disruptEl = document.querySelector("#disrupt");

let source = null;
let runId = null;
let seen = new Set();
let view = null;

function showError(message) {
  banner.hidden = !message;
  banner.textContent = message || "";
}

async function readJson(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `The desk returned ${response.status}.`);
  return data;
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson(response);
}

function selectTab(name) {
  for (const button of document.querySelectorAll("[role=tab]")) {
    const on = button.dataset.tab === name;
    button.setAttribute("aria-selected", String(on));
  }
  for (const panel of document.querySelectorAll("[role=tabpanel]")) {
    panel.hidden = panel.id !== `panel-${name}`;
  }
}

for (const button of document.querySelectorAll("[role=tab]")) {
  button.addEventListener("click", () => selectTab(button.dataset.tab));
}

function bubble(role, text) {
  const item = document.createElement("li");
  item.className = role;
  const who = document.createElement("span");
  who.textContent = role === "user" ? "You" : "Desk";
  const body = document.createElement("p");
  body.textContent = text;
  item.append(who, body);
  chatEl.append(item);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function addMessage(message) {
  if (!message || seen.has(message.id)) return;
  seen.add(message.id);
  const row = document.createElement("li");
  row.className = `tone-${message.tone || "info"}`;
  const who = document.createElement("div");
  who.className = "who";
  const badge = document.createElement("span");
  badge.className = `badge ${message.source || "python"}`;
  badge.textContent = message.source === "llm" ? `LLM · ${message.model || "mock"}` : message.source === "tool" ? "tool" : "python";
  who.textContent = `${message.from_agent} → ${message.to_agent} `;
  who.append(badge);
  const summary = document.createElement("p");
  summary.textContent = message.summary;
  row.append(who, summary);
  traceEl.append(row);
}

function render(next) {
  view = next;
  if (!view) return;
  if (view.error) showError(view.error);
  for (const message of view.agent_messages || []) addMessage(message);
  renderMenu();
  renderShopping();
  renderTimeline();
  renderQuote();
  renderFollowup();
  disruptEl.hidden = !view.pricing || view.status === "awaiting_intake";
}

function renderFollowup() {
  if (!view || view.status !== "awaiting_intake") {
    followEl.hidden = true;
    composer.hidden = false;
    followEl.dataset.key = "";
    return;
  }
  const key = JSON.stringify(view.missing || []);
  if (followEl.dataset.key === key) return;
  followEl.dataset.key = key;
  followEl.replaceChildren();
  followEl.hidden = false;
  composer.hidden = true;
  const note = document.createElement("p");
  note.textContent = (view.questions || []).join(" ");
  followEl.append(note);
  bubble("desk", note.textContent);
  for (const field of view.missing || []) {
    const label = document.createElement("label");
    label.textContent = field.replaceAll("_", " ");
    const input = document.createElement("input");
    input.name = field;
    input.required = true;
    if (field === "guests" || field === "budget_php" || field === "vegetarian_guests") input.type = "number";
    if (field === "event_date") input.type = "date";
    if (field === "event_time") {
      input.type = "time";
      input.value = "12:00";
    }
    if (field === "event_type") {
      const select = document.createElement("select");
      select.name = field;
      for (const option of ["corporate", "debut", "wedding", "fiesta"]) {
        const el = document.createElement("option");
        el.value = option;
        el.textContent = option;
        select.append(el);
      }
      label.append(select);
    } else {
      label.append(input);
    }
    followEl.append(label);
  }
  const button = document.createElement("button");
  button.type = "submit";
  button.className = "primary";
  button.textContent = "Answer";
  followEl.append(button);
}

followEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(followEl).entries());
  if (data.guests) data.guests = Number(data.guests);
  if (data.budget_php) data.budget_php = Number(data.budget_php);
  if (data.vegetarian_guests) data.vegetarian_guests = Number(data.vegetarian_guests);
  bubble("user", Object.entries(data).map(([key, value]) => `${key}: ${value}`).join(", "));
  try {
    await postJson(`/api/runs/${runId}/reply`, { answer: data });
  } catch (error) {
    showError(error.message);
  }
});

function empty(text) {
  const node = document.createElement("p");
  node.className = "empty";
  node.textContent = text;
  return node;
}

function renderMenu() {
  const host = document.querySelector("#menu");
  if (!view?.menu) {
    host.replaceChildren(empty("No menu yet."));
    return;
  }
  const table = document.createElement("table");
  table.innerHTML = "<thead><tr><th>Dish</th><th>Slot</th><th class='num'>Portions</th><th class='num'>Book cost</th></tr></thead>";
  const body = document.createElement("tbody");
  for (const line of view.menu.lines) {
    const row = document.createElement("tr");
    row.innerHTML = `<td></td><td></td><td class="num"></td><td class="num"></td>`;
    row.children[0].textContent = line.name;
    row.children[1].textContent = line.audience === "vegetarian" ? "vegetarian plate" : line.slot;
    row.children[2].textContent = String(line.portions);
    row.children[3].textContent = pesos(line.line_cost_php);
    body.append(row);
  }
  table.append(body);
  const note = document.createElement("p");
  note.className = "meta";
  note.textContent = `${view.menu.service_style} · pass ${view.menu.revision} · book food ${pesos(view.menu.food_cost_php)}`;
  host.replaceChildren(table, note);
}

function renderShopping() {
  const host = document.querySelector("#shopping");
  if (!view?.procurement) {
    host.replaceChildren(empty("No purchase list yet."));
    return;
  }
  const table = document.createElement("table");
  table.innerHTML = "<thead><tr><th>Item</th><th class='num'>Need</th><th class='num'>On hand</th><th class='num'>Order</th><th>Supplier</th></tr></thead>";
  const body = document.createElement("tbody");
  for (const line of view.procurement.lines) {
    const row = document.createElement("tr");
    const cells = ["", "", "", "", ""].map(() => document.createElement("td"));
    cells[1].className = "num";
    cells[2].className = "num";
    cells[3].className = "num";
    cells[0].textContent = line.name;
    cells[1].textContent = `${line.need} ${line.unit}`;
    cells[2].textContent = String(line.on_hand);
    cells[3].textContent = String(line.order_qty);
    cells[4].textContent = line.supplier_name + (line.switched_from ? " · switched" : "") + (line.infeasible ? " · cannot deliver" : "");
    row.append(...cells);
    body.append(row);
  }
  table.append(body);
  host.replaceChildren(table);
}

function renderTimeline() {
  const host = document.querySelector("#timeline");
  if (!view?.logistics) {
    host.replaceChildren(empty("No timeline yet."));
    return;
  }
  const list = document.createElement("ol");
  list.className = "timeline";
  for (const step of view.logistics.timeline) {
    const item = document.createElement("li");
    const when = document.createElement("strong");
    when.textContent = step.at.replace("T", " ");
    const task = document.createElement("span");
    task.textContent = step.task;
    item.append(when, task);
    list.append(item);
  }
  const crew = document.createElement("p");
  crew.className = "meta";
  crew.textContent = view.logistics.crew.map((member) => `${member.count} ${member.role.toLowerCase()}${member.count > 1 ? "s" : ""}`).join(" · ");
  host.replaceChildren(list, crew);
}

function renderQuote() {
  const host = document.querySelector("#quote");
  if (!view?.pricing) {
    host.replaceChildren(empty("No quote yet."));
    return;
  }
  const card = document.createElement("article");
  card.className = "ticket";
  const top = document.createElement("div");
  top.className = "ticket-top";
  const title = document.createElement("h3");
  title.textContent = view.status.replaceAll("_", " ");
  const stamp = document.createElement("span");
  stamp.className = "stamp " + (view.status === "pass" || view.status === "issued" ? "ok" : view.status === "over_budget" || view.status === "issued_over_budget" ? "wait" : "bad");
  stamp.textContent = view.status;
  top.append(title, stamp);
  const total = document.createElement("p");
  total.className = "total";
  total.textContent = `${pesos(view.pricing.quote_php)} · budget ${pesos(view.pricing.budget_php)} · gap ${pesos(view.pricing.gap_php)}`;
  const guidance = document.createElement("p");
  guidance.textContent = (view.pricing.client_summary || view.pricing.guidance) + " " + (view.currency_note || "Synthetic pesos.");
  card.append(top, total, guidance);
  const lines = [
    ["Food (book)", view.pricing.food_php],
    ["Cash to suppliers", view.pricing.purchase_php],
    ["Service", view.pricing.service_php],
    ["Equipment", view.pricing.equipment_php],
    ["Travel", view.pricing.travel_php],
    ["Overhead", view.pricing.overhead_php],
  ];
  const table = document.createElement("table");
  for (const [label, amount] of lines) {
    const row = document.createElement("tr");
    const name = document.createElement("td");
    name.textContent = label;
    const value = document.createElement("td");
    value.className = "num";
    value.textContent = pesos(amount);
    row.append(name, value);
    table.append(row);
  }
  card.append(table);
  if (view.alternatives?.length) {
    const list = document.createElement("ul");
    for (const alternative of view.alternatives) {
      const item = document.createElement("li");
      item.textContent = alternative;
      list.append(item);
    }
    card.append(list);
  }
  if (!view.decision && ["pass", "over_budget"].includes(view.status)) {
    const actions = document.createElement("div");
    actions.className = "actions";
    const issue = document.createElement("button");
    issue.type = "button";
    issue.className = "primary";
    issue.textContent = view.status === "over_budget" ? "Issue over budget" : "Issue quotation";
    issue.addEventListener("click", () => decide("issue"));
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "ghost";
    cancel.textContent = "Cancel";
    cancel.addEventListener("click", () => decide("cancel"));
    actions.append(issue, cancel);
    card.append(actions);
  } else if (view.decision) {
    const done = document.createElement("p");
    done.textContent = `Recorded: ${view.decision.status}. ${view.decision.notes || ""}`;
    card.append(done);
  }
  host.replaceChildren(card);
}

async function decide(action) {
  try {
    render(await postJson(`/api/runs/${runId}/decision`, { action, notes: "" }));
  } catch (error) {
    showError(error.message);
  }
}

for (const button of disruptEl.querySelectorAll("[data-disrupt]")) {
  button.addEventListener("click", async () => {
    showError("");
    try {
      await postJson(`/api/runs/${runId}/disruption`, { kind: button.dataset.disrupt });
      selectTab("trace");
    } catch (error) {
      showError(error.message);
    }
  });
}

composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = new FormData(composer).get("text").trim();
  if (!text) return;
  showError("");
  seen = new Set();
  traceEl.replaceChildren();
  bubble("user", text);
  sendBtn.disabled = true;
  try {
    const started = await postJson("/api/runs", { text });
    runId = started.run_id;
    listen(runId);
    selectTab("trace");
    composer.reset();
  } catch (error) {
    showError(error.message);
  } finally {
    sendBtn.disabled = false;
  }
});

function listen(id) {
  if (source) source.close();
  source = new EventSource(`/api/runs/${id}/events`);
  source.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "message") addMessage(data.message);
    if (data.view) render(data.view);
    if (data.type === "error") showError(data.error);
    if (data.type === "pause") selectTab("intake");
  };
  source.onerror = () => {
    source.close();
    fetch(`/api/runs/${id}`).then(readJson).then(render).catch((error) => showError(error.message));
  };
}

async function boot() {
  try {
    const [health, requests] = await Promise.all([
      fetch("/api/health").then(readJson),
      fetch("/api/requests").then(readJson),
    ]);
    document.querySelector("#health").textContent =
      `${health.provider} · ${health.embeddings} embeddings · ${health.recipes} recipes · ${health.suppliers} suppliers · ${health.documents} binder sections`;
    const samples = document.querySelector("#samples");
    for (const request of requests) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = request.label;
      button.title = request.blurb;
      button.addEventListener("click", () => {
        composer.elements.text.value = request.text;
        composer.elements.text.focus();
      });
      samples.append(button);
    }
  } catch (error) {
    showError(error.message);
  }
  renderMenu();
  renderShopping();
  renderTimeline();
  renderQuote();
}

boot();
