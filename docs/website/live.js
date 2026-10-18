const { P, CAP, LANES, POCKETS, QUEUE, OPEN_LANE, GATE_X, MOUTH_X, TOKEN, SLUICE_LIFT, LEVER_TRAVEL, LOOP, TOKENS } = DATA;

const KINDS = {
  a: { limit: POCKETS.length, seconds: 4.2 },
  b: { limit: Infinity, seconds: 1.8 },
};
const FAIL_AT = 0.45;
const DROP = 34;
const RISE = 11;
const SPEED = 120;
const TOP = TOKEN.z + TOKEN.h;
const FALLBACK = {
  "ro.open": "open",
  "ro.closed": "closed",
  "ro.running": "running",
  "ro.waiting": "waiting",
  "ro.done": "done",
  "ro.failed": "failed",
  "ro.left": "still running in errand.db",
  "ro.refused": "closed · submit raises RuntimeError",
  "ro.full": "drawer full · close the lever, then R",
  "ro.fresh": "fresh errand.db",
  "ro.busy": "close the queue before a fresh file",
};

const stage = document.querySelector(".iso-stage");
const svg = stage.querySelector("svg");
const readout = document.querySelector("[data-readout]");
const status = stage.querySelector("[data-status]");
const still = matchMedia("(prefers-reduced-motion: reduce)");
const layers = Object.fromEntries([...svg.querySelectorAll("[data-layer]")].map((el) => [el.dataset.layer, el]));
const cards = [...svg.querySelectorAll("[data-card]")].sort((a, b) => a.dataset.card - b.dataset.card);
const sluice = svg.querySelector('[data-part="sluice"]');
const lamps = [...svg.querySelectorAll("[data-lamp] .iso-solid")];
const lever = svg.querySelector('[data-part="lever"]');
const powerLamp = svg.querySelector('[data-part="power-lamp"] .iso-solid');
const spokes = svg.querySelector('[data-part="spokes"]');

const t = (key) => (typeof window.errandText === "function" && window.errandText(key)) || FALLBACK[key] || key;

let jobs = [];
let tokens = [];
let open = true;
let order = 0;
let notice = null;
let clearing = 0;
let sluiceAt = SLUICE_LIFT;
let leverAt = 0;
const wheel = { angle: 0, speed: 0 };

let frame = 0;
let last = 0;
let now = 0;
let visible = false;
let touring = !still.matches;
let clock = -0.4;
let step = 0;
let idleAt = null;
let quietSince = 0;
let lastText = "";

function say(text) {
  if (status.textContent !== text) status.textContent = text;
}

function warn(key) {
  notice = { key, until: now + 2.2 };
  say(t(key));
}

function submit(kind, fail = false) {
  if (!open) return warn("ro.refused");
  if (jobs.length >= CAP || clearing) return warn("ro.full");
  const card = cards[jobs.length];
  const job = { index: jobs.length, kind, fail, status: "running", z: still.matches ? 0 : DROP, v: 0, landed: false, flag: 1, mark: 0, token: null, card };
  card.style.display = "";
  card.style.opacity = "";
  jobs.push(job);
  if (still.matches) land(job);
  run();
}

function land(job) {
  job.z = 0;
  job.v = 0;
  job.landed = true;
  if (open && !job.token) spawn(job, 0);
}

function spawn(job, delay) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", "g");
  el.setAttribute("class", "ed-token");
  el.innerHTML = TOKENS[job.kind];
  el.style.opacity = "0";
  const token = {
    job,
    kind: job.kind,
    el,
    solid: el.querySelector(".iso-solid"),
    ptr: el.querySelector("[data-ptr]"),
    x: MOUTH_X - 2,
    z: 0,
    alpha: 0,
    delay,
    state: "live",
    holding: false,
    progress: 0,
    order: order++,
    target: MOUTH_X - 2,
  };
  job.token = token;
  (job.kind === "a" ? layers["a-queue"] : layers.b).appendChild(el);
  tokens.push(token);
}

function setOpen(next) {
  if (next === open) return;
  open = next;
  notice = null;
  if (!open) {
    for (const token of tokens) {
      if (token.state !== "live") continue;
      token.state = "cancel";
      token.holding = false;
      token.job.token = null;
    }
    say(t("ro.closed"));
  } else {
    jobs
      .filter((job) => job.status === "running" && job.landed && !job.token)
      .forEach((job, index) => spawn(job, still.matches ? 0 : index * 0.22));
    say(t("ro.open"));
  }
  run();
}

function reset() {
  if (tokens.some((token) => token.state === "live")) return warn("ro.busy");
  if (!jobs.length) return warn("ro.fresh");
  clearing = still.matches ? 1 : 0.0001;
  run();
}

const live = (kind) => tokens.filter((token) => token.kind === kind && token.state === "live" && token.delay <= 0).sort((a, b) => a.order - b.order);

function schedule() {
  for (const kind of ["a", "b"]) {
    const list = live(kind);
    let held = list.filter((token) => token.holding).length;
    for (const token of list) {
      if (!token.holding && held < KINDS[kind].limit && open) {
        token.holding = true;
        held++;
      }
    }
    const holders = list.filter((token) => token.holding);
    const waiters = list.filter((token) => !token.holding);
    if (kind === "a") {
      holders.forEach((token, index) => (token.target = POCKETS[Math.min(index, POCKETS.length - 1)]));
      waiters.forEach((token, index) => (token.target = QUEUE[Math.min(index, QUEUE.length - 1)]));
    } else {
      holders.forEach((token, index) => (token.target = OPEN_LANE[Math.min(index, OPEN_LANE.length - 1)]));
    }
  }
}

function pointerAt(progress, c) {
  const angle = progress * Math.PI * 2;
  const r = TOKEN.r - 2.4;
  return lineOnTop([0, c], [Math.sin(angle) * r, c - Math.cos(angle) * r], TOP + 0.05, P);
}

function moveTokens(dt, calm) {
  for (const token of tokens) {
    if (token.delay > 0) {
      token.delay -= dt;
      continue;
    }
    if (token.state === "live") {
      token.alpha = calm ? 1 : Math.min(1, token.alpha + dt / 0.3);
      const gap = token.target - token.x;
      const move = calm ? gap : Math.max(-SPEED * dt, Math.min(SPEED * dt, gap * (1 - Math.exp(-dt / 0.2))));
      token.x = Math.abs(gap - move) < 0.02 ? token.target : token.x + move;
      if (token.holding && open) {
        token.progress += dt / KINDS[token.kind].seconds;
        const job = token.job;
        if (job.fail && token.progress >= FAIL_AT) {
          job.status = "failed";
          token.state = "fail";
          token.holding = false;
          job.token = null;
        } else if (token.progress >= 1) {
          token.progress = 1;
          job.status = "done";
          token.state = "lift";
          token.holding = false;
          job.token = null;
        }
      }
    } else if (token.state === "lift") {
      token.z += dt * 26;
      token.alpha -= calm ? 1 : dt / 0.55;
    } else if (token.state === "fail") {
      token.alpha -= calm ? 1 : dt / 0.7;
      token.x += Math.sin(now * 60) * 0.35;
    } else if (token.state === "cancel") {
      token.alpha -= calm ? 1 : dt / 0.4;
      token.z -= dt * 5;
    }
  }
  tokens = tokens.filter((token) => {
    if (token.alpha > 0 || token.state === "live") return true;
    token.el.remove();
    return false;
  });
}

function placeTokens() {
  const groups = { "a-queue": [], "a-run": [], b: [] };
  for (const token of tokens) {
    const name = token.kind === "b" ? "b" : token.x > GATE_X + 7 ? "a-run" : "a-queue";
    groups[name].push(token);
    token.el.setAttribute("transform", translateAlong(P, [token.x, 0, token.z]));
    token.el.style.opacity = Math.max(0, Math.min(1, token.alpha)).toFixed(3);
    const lit = token.holding && token.state === "live";
    token.solid.toggleAttribute("data-lit", lit);
    token.ptr.setAttribute("data-tone", lit ? "lit" : "mid");
    token.ptr.setAttribute("d", pointerAt(token.progress, LANES[token.kind]));
  }
  for (const [name, list] of Object.entries(groups)) {
    list.sort((a, b) => a.x - b.x || a.order - b.order);
    const host = layers[name];
    const current = [...host.children];
    if (list.length === current.length && list.every((token, index) => token.el === current[index])) continue;
    const fragment = document.createDocumentFragment();
    list.forEach((token) => fragment.appendChild(token.el));
    host.appendChild(fragment);
  }
}

function moveCards(dt, calm) {
  let busy = false;
  for (const job of jobs) {
    if (!job.landed) {
      job.v += 340 * dt;
      job.z -= job.v * dt;
      if (job.z <= 0) land(job);
      busy = true;
    }
    const flag = job.status === "running" ? 1 : 0;
    const mark = job.status === "failed" ? 1 : 0;
    job.flag = calm ? flag : job.flag + (flag - job.flag) * (1 - Math.exp(-dt / 0.16));
    job.mark = calm ? mark : job.mark + (mark - job.mark) * (1 - Math.exp(-dt / 0.2));
    if (Math.abs(job.flag - flag) < 0.003) job.flag = flag;
    if (Math.abs(job.mark - mark) < 0.003) job.mark = mark;
    if (job.flag !== flag || job.mark !== mark) busy = true;
    const lift = clearing ? clearing * 30 : 0;
    job.card.setAttribute("transform", translateAlong(P, [0, 0, job.z + lift]));
    if (clearing) job.card.style.opacity = String(Math.max(0, 1 - clearing).toFixed(3));
    const flagEl = job.card.querySelector("[data-flag]");
    flagEl.setAttribute("transform", translateAlong(P, [0, 0, -(1 - job.flag) * RISE]));
    flagEl.style.opacity = job.flag.toFixed(3);
    job.card.querySelector("[data-fail]").style.opacity = job.mark.toFixed(3);
  }
  if (clearing) {
    clearing = Math.min(1, clearing + (calm ? 1 : dt / 0.5));
    busy = true;
    if (clearing >= 1) {
      for (const job of jobs) {
        job.card.style.display = "none";
        job.card.removeAttribute("transform");
        job.card.style.opacity = "";
      }
      jobs = [];
      clearing = 0;
      notice = { key: "ro.fresh", until: now + 1.6 };
    }
  }
  return busy;
}

function follow(value, target, dt, seconds, calm) {
  if (calm) return target;
  const next = value + (target - value) * (1 - Math.exp(-dt / seconds));
  return Math.abs(next - target) < 0.01 ? target : next;
}

function moveMachine(dt, calm) {
  const holders = live("a").filter((token) => token.holding).length;
  const closed = open && holders >= POCKETS.length;
  sluiceAt = follow(sluiceAt, closed ? 0 : SLUICE_LIFT, dt, 0.16, calm);
  sluice.setAttribute("transform", translateAlong(P, [0, 0, sluiceAt]));
  lamps.forEach((lamp, index) => lamp.toggleAttribute("data-lit", open && holders > index));
  leverAt = follow(leverAt, open ? 0 : LEVER_TRAVEL, dt, 0.14, calm);
  lever.setAttribute("transform", translateAlong(P, [leverAt, 0, 0]));
  powerLamp.toggleAttribute("data-lit", open);
  const speed = open && !calm ? 0.45 : 0;
  wheel.speed = follow(wheel.speed, speed, dt, open ? 0.5 : 0.9, calm);
  if (wheel.speed < 0.002 && !open) wheel.speed = 0;
  wheel.angle += wheel.speed * Math.PI * 2 * dt;
  const d = [0, 1, 2]
    .map((index) => {
      const angle = wheel.angle + (index * Math.PI * 2) / 3;
      const from = [LOOP.x + Math.sin(angle) * 2, LOOP.y - Math.cos(angle) * 2];
      const to = [LOOP.x + Math.sin(angle) * (LOOP.r - 2), LOOP.y - Math.cos(angle) * (LOOP.r - 2)];
      return lineOnTop(from, to, 12, P);
    })
    .join("");
  spokes.setAttribute("d", d);
  return sluiceAt !== (closed ? 0 : SLUICE_LIFT) || leverAt !== (open ? 0 : LEVER_TRAVEL) || wheel.speed > 0;
}

function readoutText() {
  if (notice && now < notice.until) return t(notice.key);
  notice = null;
  const running = jobs.filter((job) => job.status === "running").length;
  const done = jobs.filter((job) => job.status === "done").length;
  const failed = jobs.filter((job) => job.status === "failed").length;
  if (!open) return `${t("ro.closed")} · ${running} ${t("ro.left")}`;
  const waiting = live("a").filter((token) => !token.holding).length;
  const wait = waiting ? ` (${waiting} ${t("ro.waiting")})` : "";
  return `${t("ro.open")} · ${running} ${t("ro.running")}${wait} · ${done} ${t("ro.done")} · ${failed} ${t("ro.failed")}`;
}

const TOUR = [
  [0.6, () => submit("a")],
  [1.3, () => submit("a")],
  [2.0, () => submit("a")],
  [2.6, () => submit("b")],
  [3.2, () => submit("b", true)],
  [3.9, () => submit("a")],
  [4.6, () => submit("b")],
  [6.8, () => submit("a")],
  [8.4, () => setOpen(false)],
  [10.8, () => setOpen(true)],
];

const settled = () => !tokens.length && jobs.every((job) => job.landed && job.status !== "running");

function tour(dt) {
  clock += dt;
  while (step < TOUR.length && clock >= TOUR[step][0]) TOUR[step++][1]();
  if (step < TOUR.length) return;
  if (!settled() || clearing) {
    idleAt = null;
    return;
  }
  if (!jobs.length) {
    clock = -0.4;
    step = 0;
    return;
  }
  idleAt ??= clock;
  if (clock - idleAt > 2.6) {
    reset();
    idleAt = null;
  }
}

function restartTour() {
  touring = true;
  clock = -0.4;
  step = 0;
  idleAt = null;
  if (jobs.length) reset();
}

function tick(stamp) {
  const dt = last ? Math.min((stamp - last) / 1000, 1 / 30) : 1 / 60;
  last = stamp;
  now += dt;
  const calm = still.matches;
  if (touring) tour(dt);
  else if (!calm && open && settled() && now - quietSince > 12) restartTour();
  schedule();
  moveTokens(dt, calm);
  placeTokens();
  const cardsBusy = moveCards(dt, calm);
  const machineBusy = moveMachine(dt, calm);
  const text = readoutText();
  if (text !== lastText) {
    readout.textContent = text;
    lastText = text;
  }
  const busy = touring || tokens.length || cardsBusy || machineBusy || notice || (!calm && open);
  frame = visible && busy ? requestAnimationFrame(tick) : 0;
}

function run() {
  if (!frame && visible) {
    last = 0;
    frame = requestAnimationFrame(tick);
  }
}

function takeOver() {
  touring = false;
  idleAt = null;
  quietSince = now;
}

new IntersectionObserver(
  (entries) => {
    visible = entries[entries.length - 1].isIntersecting;
    if (visible) run();
  },
  { rootMargin: "120px 0px" },
).observe(stage);

svg.addEventListener("click", (event) => {
  const hit = event.target.closest("[data-hit]")?.dataset.hit;
  if (!hit || hit === "drawer") return;
  takeOver();
  if (hit === "power") setOpen(!open);
  else submit(hit, event.shiftKey);
  stage.focus({ preventScroll: true });
});

stage.addEventListener("keydown", (event) => {
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  const key = event.key.toLowerCase();
  const actions = {
    1: () => submit("a"),
    a: () => submit("a"),
    2: () => submit("b"),
    b: () => submit("b"),
    f: () => submit("b", true),
    " ": () => setOpen(!open),
    enter: () => setOpen(!open),
    escape: () => setOpen(!open),
    r: () => (open ? warn("ro.busy") : reset()),
  };
  if (!actions[key]) return;
  event.preventDefault();
  takeOver();
  actions[key]();
  run();
});

document.addEventListener("errand:lang", () => {
  lastText = "";
  readout.textContent = readoutText();
});

if (still.matches) touring = false;
readout.textContent = readoutText();
placeTokens();
moveMachine(0, true);
