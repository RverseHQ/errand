import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "./kit/iso-kit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "..", "index.html");

const WIDTH = 640;
const HEIGHT = 380;

const PLATE = { x: -164, y: -78, w: 328, d: 158, r: 8 };
const PLATE_H = 10;
const FOOT_H = 5;

const DRAWER = { x: -150, y: -64, w: 80, d: 120, r: 3 };
const WALL_H = 20;
const FRONT_Y = DRAWER.y + DRAWER.d;
const CARD = { x: -142, w: 64, z: 3, h: 30, d: 1.2 };
const CARD_TOP = CARD.z + CARD.h;
const CAP = 14;
const PITCH = 7.6;
const cardY = (index) => DRAWER.y + 7 + index * PITCH;
const FLAG = { x: CARD.x + CARD.w - 9, w: 5, z: CARD_TOP - 3, h: 13 };

const DISPATCH = { x: -66, y: -50, w: 16, d: 96, r: 2 };
const DISPATCH_H = 18;
const MOUTH_X = DISPATCH.x + DISPATCH.w;

const LANE_FROM = MOUTH_X;
const LANE_TO = 150;
const LANES = { a: -30, b: 22 };
const TOKEN = { r: 6, z: 3, h: 6 };
const RAIL_H = 3;

const GATE_X = 58;
const POCKETS = [104, 78];
const QUEUE = [48, 34, 20, 6, -8, -22, -36];
const OPEN_LANE = [138, 122, 106, 90, 74, 58, 42, 26, 10, -6, -22, -38];
const SLUICE = { z: 3.4, h: 15, lift: 12 };

const LOOP = { x: 106, y: 58, r: 13 };
const LEVER = { block: { x: 20, y: 48, w: 36, d: 16, r: 2 }, h: 9, open: 48, closed: 30, y: 56 };

const P = k.fitProjection(
  [
    ...k.boxCorners(PLATE, -PLATE_H - FOOT_H, 0),
    [DRAWER.x, DRAWER.y, FLAG.z + FLAG.h + 2],
    [GATE_X, LANES.a - 19, 34],
  ],
  WIDTH,
  HEIGHT,
  { pad: 10, azimuth: 50, elevation: 34 },
);

const at = (point) => k.iso(point, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (points, style) => k.dotsSvg(points, style);
const byDepth = (points) => [...points].sort((a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P));
const planeOf = (y) => k.sideMatrix([0, y], 0, P, "left");
const flat = (x0, z0, x1, z1, r, steps = 6) => k.pathOf(k.roundedPlan({ x: x0, y: z0, w: x1 - x0, d: z1 - z0, r }, steps).map(([u, z]) => [u, -z]), true);
const onSideX = (x, y0, z0, y1, z1, r, steps = 6) => k.pathOf(k.roundedPlan({ x: y0, y: z0, w: y1 - y0, d: z1 - z0, r }, steps).map(([y, z]) => at([x, y, z])), true);
const screws = (points, z, size = 0.45) => D(points.map(([x, y]) => at([x, y, z])), { size });

function plate() {
  const out = [`<path class="iso-halo" d="${k.haloOf(PLATE, -PLATE_H - FOOT_H, PLATE_H, P)}"/>`];
  for (const [x, y] of byDepth(k.corners(PLATE, 22))) {
    out.push(S(k.cylinder(x, y, 7, -PLATE_H - FOOT_H, 1.6, P, 28), { tone: "lo" }));
    out.push(S(k.cylinder(x, y, 5.4, -PLATE_H - FOOT_H + 1.6, FOOT_H - 1.6, P, 28), { tone: "mid" }));
  }
  out.push(S(k.slabOf(PLATE, -PLATE_H, PLATE_H, P, 8, 1.6), { tone: "mid", inner: L(k.sideSeam(PLATE, -PLATE_H / 2, P, 8), { tone: "faint" }) }));
  out.push(L(k.planOutline(k.insetPlan(PLATE, 5), 0, P), { tone: "lo" }));
  const corners = k.corners(PLATE, 10);
  out.push(L(corners.map(([x, y]) => k.ring(x, y, 2.2, 0, P, 16)).join(""), { tone: "lo" }));
  out.push(screws(corners, 0, 0.5));
  const strip = { x: -40, y: PLATE.y + 7, w: 186, d: 7, r: 1 };
  out.push(S(k.slabOf(strip, 0, 0.6, P, 3), { tone: "lo", crease: "none" }));
  const ticks = k.topTicks(strip.x + 4, strip.x + strip.w - 4, 4, 5, strip.y + 0.8, 0.6, [2, 3.6], P);
  out.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
  out.push(screws([[strip.x + 2, strip.y + 3.5], [strip.x + strip.w - 2, strip.y + 3.5]], 0.6));
  const label = { x: -150, y: FRONT_Y + 10, w: 46, d: 9, r: 1.2 };
  out.push(S(k.slabOf(label, 0, 0.8, P, 3), { tone: "lo", crease: "none" }));
  out.push(L(k.planOutline(k.insetPlan(label, 1.4), 0.8, P, 3), { tone: "faint" }));
  out.push(L([32, 24, 28].map((w, i) => k.lineOnTop([label.x + 4, label.y + 2.6 + i * 1.9], [label.x + 4 + w, label.y + 2.6 + i * 1.9], 0.8, P)).join(""), { tone: "lo", free: true }));
  out.push(screws([[label.x + label.w - 3, label.y + 3], [label.x + label.w - 3, label.y + label.d - 3]], 0.8));
  return out.join("");
}

function cardSvg(index) {
  const y = cardY(index);
  const plan = { x: CARD.x, y, w: CARD.w, d: CARD.d, r: 0.4 };
  const tab = { x: CARD.x + 3 + (index % 3) * 18, y, w: 15, d: CARD.d, r: 0.4 };
  const flag = { x: FLAG.x, y: y - 0.7, w: FLAG.w, d: CARD.d + 1.4, r: 0.6 };
  const clip = { x: CARD.x + 2, y: y - 0.7, w: 4, d: CARD.d + 1.4, r: 0.6 };
  const out = [
    S(k.slabOf(plan, CARD.z, CARD.h, P, 2), { tone: "hi", crease: "lo" }),
    S(k.slabOf(tab, CARD_TOP, 3.4, P, 2), { tone: "hi", crease: "lo" }),
    `<g data-flag>${S(k.slabOf(flag, FLAG.z, FLAG.h, P, 2, 0.3), { tone: "hi", lit: true })}${D([at([FLAG.x + FLAG.w / 2, y + CARD.d + 0.7, FLAG.z + FLAG.h - 2.4])], { size: 0.45, tone: "lo" })}</g>`,
    `<g data-fail style="opacity:0">${S(k.slabOf(clip, CARD_TOP - 3, 6.4, P, 2, 0.3), { tone: "mid" })}${L(k.segment([clip.x, y + CARD.d + 0.7, CARD_TOP + 1.2], [clip.x + clip.w, y + CARD.d + 0.7, CARD_TOP + 1.2], P), { tone: "lo" })}</g>`,
  ];
  return `<g data-card="${index}" style="display:none">${out.join("")}</g>`;
}

function drawer() {
  const out = [`<path class="iso-halo" d="${k.haloOf(DRAWER, 0, 4, P)}"/>`];
  out.push(S(k.slabOf(DRAWER, 0, 3, P, 4), { tone: "lo" }));
  const inner = k.insetPlan(DRAWER, 3);
  out.push(L(k.planOutline(k.insetPlan(inner, 1), 3, P, 3), { tone: "faint" }));
  out.push(S(k.slabOf({ x: DRAWER.x, y: DRAWER.y, w: DRAWER.w, d: 3, r: 1 }, 3, WALL_H - 3, P, 2, 0.4), { tone: "mid" }));
  out.push(S(k.slabOf({ x: DRAWER.x, y: DRAWER.y, w: 3, d: DRAWER.d, r: 1 }, 3, WALL_H - 3, P, 2, 0.4), { tone: "mid" }));
  out.push(S(k.slabOf({ x: -111.5, y: DRAWER.y + 3, w: 3, d: DRAWER.d - 3, r: 1.4 }, 6, 3, P, 3), { tone: "lo" }));
  for (let index = 0; index < CAP; index++) out.push(cardSvg(index));
  out.push(S(k.slabOf({ x: DRAWER.x + DRAWER.w - 3, y: DRAWER.y, w: 3, d: DRAWER.d, r: 1 }, 3, WALL_H - 3, P, 2, 0.4), { tone: "mid" }));
  out.push(screws([[DRAWER.x + DRAWER.w - 1.5, DRAWER.y + 8], [DRAWER.x + DRAWER.w - 1.5, FRONT_Y - 8]], WALL_H));
  const front = { x: DRAWER.x - 2, y: FRONT_Y, w: DRAWER.w + 4, d: 4, r: 1.5 };
  const face = FRONT_Y + 4;
  out.push(S(k.slabOf(front, 0, 25, P, 3, 0.8), { tone: "mid", inner: L(k.sideSeam(front, 3, P, 3), { tone: "faint" }) }));
  const holder = [DRAWER.x + 6, 13, DRAWER.x + 34, 21];
  out.push(
    `<g transform="${planeOf(face)}">`,
    `<path class="ed-well" d="${flat(holder[0], holder[1], holder[2], holder[3], 1)}"/>`,
    L(flat(holder[0], holder[1], holder[2], holder[3], 1), { tone: "lo" }),
    L(flat(holder[0] + 1.2, holder[1] + 1.2, holder[2] - 1.2, holder[3] - 1.2, 0.6), { tone: "faint" }),
    `<text class="iso-face-text" data-tone="hi" x="${(holder[0] + holder[2]) / 2}" y="${-(holder[1] + 2.9)}" font-size="3.6" text-anchor="middle">errand.db</text>`,
    `</g>`,
  );
  out.push(D([at([holder[0] - 1.8, face, 17]), at([holder[2] + 1.8, face, 17])], { size: 0.45 }));
  const pull = { x0: DRAWER.x + 48, x1: DRAWER.x + 72 };
  out.push(S(k.slabOf({ x: pull.x0, y: face, w: 3, d: 3, r: 1 }, 14, 4, P, 2), { tone: "mid" }));
  out.push(S(k.slabOf({ x: pull.x1 - 3, y: face, w: 3, d: 3, r: 1 }, 14, 4, P, 2), { tone: "mid" }));
  out.push(S(k.slabOf({ x: pull.x0 - 1, y: face + 3, w: pull.x1 - pull.x0 + 2, d: 2.6, r: 1.2 }, 13.4, 5.2, P, 3, 0.4), { tone: "hi", crease: "lo" }));
  out.push(S(k.slabOf({ x: -112.6, y: face, w: 5.2, d: 2.2, r: 2.4 }, 4.6, 5.2, P, 5), { tone: "mid" }));
  out.push(D([at([-110, face + 2.2, 7.2])], { size: 0.55, tone: "hi" }));
  return out.join("");
}

function dispatcher() {
  const out = [`<path class="iso-halo" d="${k.haloOf(DISPATCH, 0, 4, P)}"/>`];
  out.push(S(k.slabOf(k.insetPlan(DISPATCH, -1.5), 0, 3, P, 4), { tone: "lo" }));
  out.push(S(k.slabOf(DISPATCH, 3, DISPATCH_H - 3, P, 4, 0.8), { tone: "mid", inner: L(k.sideSeam(DISPATCH, 9, P, 4), { tone: "faint" }) }));
  out.push(L(k.planOutline(k.insetPlan(DISPATCH, 3), DISPATCH_H, P, 3), { tone: "lo" }));
  const vents = [];
  for (let y = DISPATCH.y + 14; y < DISPATCH.y + DISPATCH.d - 12; y += 4) vents.push(k.planOutline({ x: DISPATCH.x + 5, y, w: 6, d: 1.4, r: 0.7 }, DISPATCH_H, P, 3));
  out.push(L(vents.join(""), { tone: "faint" }));
  out.push(screws(k.corners(DISPATCH, 5.5), DISPATCH_H, 0.5));
  for (const lane of Object.values(LANES)) {
    out.push(`<path class="ed-dark" d="${onSideX(MOUTH_X, lane - 8, 3, lane + 8, 12.5, 3)}"/>`);
    out.push(L(onSideX(MOUTH_X, lane - 8, 3, lane + 8, 12.5, 3), { tone: "lo" }));
    out.push(L(onSideX(MOUTH_X, lane - 6.8, 4.2, lane + 6.8, 11.3, 2.2), { tone: "faint" }));
    out.push(D([at([MOUTH_X, lane, 15])], { size: 0.6, tone: "hi" }));
  }
  return out.join("");
}

function laneBed(key) {
  const c = LANES[key];
  const out = [];
  const bed = { x: LANE_FROM, y: c - 11, w: LANE_TO - LANE_FROM, d: 22, r: 2 };
  out.push(S(k.slabOf(bed, 0, 3, P, 3, 0.4), { tone: "lo" }));
  out.push(L(k.lineOnTop([LANE_FROM, c], [LANE_TO - 5, c], 3, P), { tone: "faint" }));
  for (const y of [c - 11, c + 8]) {
    out.push(S(k.slabOf({ x: LANE_FROM, y, w: LANE_TO - LANE_FROM - 5, d: 3, r: 1 }, 3, RAIL_H, P, 2, 0.4), { tone: "mid" }));
    out.push(screws([LANE_FROM + 8, 20, 70, 120].map((x) => [x, y + 1.5]), 3 + RAIL_H, 0.4));
  }
  const stop = { x: LANE_TO - 5, y: c - 12, w: 5, d: 24, r: 1.2 };
  out.push(S(k.slabOf(stop, 0, 10, P, 3, 0.5), { tone: "mid" }));
  out.push(screws([[stop.x + 2.5, c - 8], [stop.x + 2.5, c + 8]], 10));
  return out.join("");
}

function gateBack() {
  const c = LANES.a;
  const out = [];
  const wall = { x: GATE_X, y: c - 19, w: 64, d: 5, r: 1.2 };
  out.push(S(k.slabOf(wall, 0, 24, P, 3, 0.6), { tone: "mid", inner: L(k.sideSeam(wall, 6, P, 3), { tone: "faint" }) }));
  out.push(screws([[wall.x + 10, wall.y + 2.5], [wall.x + wall.w - 4, wall.y + 2.5]], 24));
  POCKETS.forEach((x, index) => {
    out.push(S(k.cylinder(x, c - 16.5, 3.2, 24, 1.2, P, 20), { tone: "lo" }));
    out.push(`<g data-lamp="${index}">${S(k.cylinder(x, c - 16.5, 2.3, 25.2, 2.4, P, 20, 0.3), { tone: "mid" })}</g>`);
  });
  out.push(S(k.slabOf({ x: GATE_X - 0.5, y: c - 19, w: 6, d: 6, r: 1.2 }, 0, 31, P, 3, 0.4), { tone: "mid" }));
  return out.join("");
}

function pocketSeats() {
  const c = LANES.a;
  return L(POCKETS.map((x) => k.ring(x, c, TOKEN.r + 1.2, 3, P, 32)).join(""), { tone: "faint" });
}

function sluice() {
  const c = LANES.a;
  const plate = { x: GATE_X + 1.5, y: c - 8, w: 2.4, d: 16, r: 0.6 };
  const seams = L([5, 9].map((z) => k.sideSeam(plate, SLUICE.z + z, P, 2)).join(""), { tone: "faint" });
  const out = [S(k.slabOf(plate, SLUICE.z, SLUICE.h, P, 2, 0.3), { tone: "hi", crease: "lo", inner: seams })];
  out.push(screws([[plate.x + plate.w / 2, plate.y + 3], [plate.x + plate.w / 2, plate.y + plate.d - 3]], SLUICE.z + SLUICE.h));
  return out.join("");
}

function gateFront() {
  const c = LANES.a;
  const out = [];
  out.push(S(k.slabOf({ x: GATE_X - 0.5, y: c + 13, w: 6, d: 6, r: 1.2 }, 0, 31, P, 3, 0.4), { tone: "mid" }));
  const bar = { x: GATE_X - 1, y: c - 19.5, w: 7, d: 39, r: 1.4 };
  out.push(S(k.slabOf(bar, 31, 3.4, P, 3, 0.5), { tone: "mid" }));
  out.push(screws([[GATE_X + 2.5, c - 16], [GATE_X + 2.5, c + 16]], 34.4));
  out.push(S(k.slabOf({ x: GATE_X + 1, y: c - 2, w: 3, d: 4, r: 1 }, 34.4, 2, P, 2), { tone: "lo" }));
  return out.join("");
}

function laneLabel(key) {
  const c = LANES[key];
  const plate = { x: -30, y: c + 11.6, w: 26, d: 5.4, r: 0.8 };
  return [
    S(k.slabOf(plate, 0, 0.6, P, 2), { tone: "lo", crease: "none" }),
    L([16, 11].map((w, i) => k.lineOnTop([plate.x + 3, plate.y + 1.8 + i * 1.8], [plate.x + 3 + w, plate.y + 1.8 + i * 1.8], 0.6, P)).join(""), { tone: "lo", free: true }),
    screws([[plate.x + plate.w - 2.4, plate.y + plate.d / 2]], 0.6),
  ].join("");
}

function lever() {
  const { block, h } = LEVER;
  const out = [`<path class="iso-halo" d="${k.haloOf(block, 0, 3, P)}"/>`];
  out.push(S(k.slabOf(block, 0, h, P, 4, 0.8), { tone: "mid", inner: L(k.sideSeam(block, 2.4, P, 4), { tone: "faint" }) }));
  const slot = { x: LEVER.closed - 3, y: LEVER.y - 1.6, w: LEVER.open - LEVER.closed + 6, d: 3.2, r: 1.6 };
  out.push(`<path class="ed-dark" d="${k.planOutline(slot, h, P, 4)}"/>`);
  out.push(L(k.planOutline(slot, h, P, 4), { tone: "lo" }));
  const ticks = k.topTicks(slot.x + 2, slot.x + slot.w - 2, 3, 3, slot.y + slot.d + 0.6, h, [1.2, 2.2], P);
  out.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
  out.push(screws([[block.x + 3, block.y + 3], [block.x + block.w - 3, block.y + 3], [block.x + 3, block.y + block.d - 3], [block.x + block.w - 3, block.y + block.d - 3]], h, 0.5));
  out.push(S(k.cylinder(block.x + block.w - 6, block.y + 4.5, 3, h, 1, P, 20), { tone: "lo" }));
  out.push(`<g data-part="power-lamp">${S(k.cylinder(block.x + block.w - 6, block.y + 4.5, 2.2, h + 1, 2.2, P, 20, 0.3), { tone: "mid", lit: true })}</g>`);
  return out.join("");
}

function leverHandle() {
  const x = LEVER.open;
  const y = LEVER.y;
  const z = LEVER.h;
  return [
    S(k.cylinder(x, y, 2.2, z, 1, P, 16), { tone: "mid" }),
    S(k.cylinder(x, y, 1.2, z + 1, 11, P, 14), { tone: "mid", crease: "none" }),
    S(k.cylinder(x, y, 3.6, z + 12, 5, P, 28, 0.4), { tone: "hi", crease: "lo" }),
    L(k.knurl(x, y, 3.6, z + 12, z + 17, 22, P), { tone: "lo" }),
  ].join("");
}

function flywheel() {
  const { x, y, r } = LOOP;
  const out = [`<path class="iso-halo" d="${k.haloOf({ x: x - r - 2, y: y - r - 2, w: r * 2 + 4, d: r * 2 + 4, r: r + 2 }, 0, 3, P)}"/>`];
  out.push(S(k.cylinder(x, y, r + 3, 0, 3, P, 56), { tone: "lo" }));
  out.push(screws([0, 1, 2, 3].map((i) => [x + Math.cos(i * Math.PI / 2 + 0.6) * (r + 1.6), y + Math.sin(i * Math.PI / 2 + 0.6) * (r + 1.6)]), 3, 0.45));
  out.push(S(k.cylinder(x, y, r + 1, 3, 4, P, 56), { tone: "mid" }));
  out.push(S(k.cylinder(x, y, r, 7, 5, P, 64, 0.6), { tone: "hi", crease: "lo", inner: L(k.sideArc(x, y, r, 9.5, P, 32), { tone: "faint" }) }));
  out.push(L(k.knurl(x, y, r, 9.5, 12, 64, P, 0.3), { tone: "lo" }));
  out.push(L(k.ring(x, y, r - 2, 12, P, 56), { tone: "lo" }));
  const ticks = k.radialTicks(x, y, r - 2, 40, 5, 12, [1, 2], P);
  out.push(L(ticks.minor, { tone: "faint" }), L(ticks.major, { tone: "lo" }));
  out.push(`<path data-part="spokes" class="iso-line" data-tone="hi" d=""/>`);
  out.push(S(k.cylinder(x, y, 2.6, 12, 2, P, 20, 0.3), { tone: "mid" }));
  return out.join("");
}

function wires() {
  const { block } = LEVER;
  const toDispatch = k.wireSvg(at([block.x, block.y + 10, 3]), at([DISPATCH.x + 8, DISPATCH.y + DISPATCH.d, 6]), {
    via: [at([block.x - 6, block.y + 10, 0.6]), at([-40, block.y + 10, 0.6]), at([-52, DISPATCH.y + DISPATCH.d + 8, 0.6]), at([DISPATCH.x + 8, DISPATCH.y + DISPATCH.d + 4, 0.6])],
    tone: "lo",
  });
  const toLoop = k.wireSvg(at([block.x + block.w, block.y + 9, 3]), at([LOOP.x - LOOP.r - 3, LOOP.y, 1.5]), { via: [at([block.x + block.w + 8, block.y + 9, 0.6]), at([LOOP.x - LOOP.r - 9, LOOP.y, 0.6])], tone: "lo" });
  return `<g class="ed-wire">${toDispatch}${toLoop}</g>`;
}

function tokenSvg(key) {
  const c = LANES[key];
  const top = TOKEN.z + TOKEN.h;
  return [
    S(k.cylinder(0, c, TOKEN.r, TOKEN.z, TOKEN.h, P, 36, 0.4), { tone: "hi", crease: "lo", inner: L(k.sideArc(0, c, TOKEN.r, TOKEN.z + 1.6, P, 24), { tone: "faint" }) }),
    L(k.knurl(0, c, TOKEN.r, TOKEN.z + 1.6, top, 30, P, 0.3), { tone: "lo" }),
    L(k.ring(0, c, TOKEN.r - 2, top, P, 32), { tone: "faint" }),
    `<path data-ptr class="iso-line" data-tone="mid" data-free="end" d="" style="stroke-width:1"/>`,
    D([at([0, c, top])], { size: 0.6, tone: "hi" }),
  ].join("");
}

const layer = (name) => `<g data-layer="${name}"></g>`;

const svg = k.figureSvg({
  width: WIDTH,
  height: HEIGHT,
  label:
    "A dispatch desk that stands for errand. A card-file drawer labelled errand.db holds one index card per job, filed in submission order; a raised flag on a card means the job is running. A dispatcher beside the drawer sends a token for each filed card onto one of two lanes: the summarize lane passes a sluice gate with two pockets, the greet lane has no gate. A lever in front opens and closes the queue, and a flywheel turns while the event loop runs.",
  body: [
    plate(),
    `<g data-hit="drawer">${drawer()}</g>`,
    dispatcher(),
    `<g data-hit="a">${gateBack()}${laneBed("a")}${pocketSeats()}${layer("a-queue")}<g data-part="sluice">${sluice()}</g>${gateFront()}${layer("a-run")}${laneLabel("a")}</g>`,
    `<g data-hit="b">${laneBed("b")}${layer("b")}${laneLabel("b")}</g>`,
    wires(),
    `<g data-hit="power">${lever()}<g data-part="lever">${leverHandle()}</g></g>`,
    flywheel(),
  ],
});

const DATA = {
  P,
  CAP,
  LANES,
  POCKETS,
  QUEUE,
  OPEN_LANE,
  GATE_X,
  MOUTH_X,
  TOKEN,
  SLUICE_LIFT: SLUICE.lift,
  LEVER_TRAVEL: LEVER.closed - LEVER.open,
  LOOP,
  TOKENS: { a: tokenSvg("a"), b: tokenSvg("b") },
};

const keys = [
  ["lit", "fig.key.running"],
  ["raised", "fig.key.cards"],
  ["flat", "fig.key.gate"],
  ["dim", "fig.key.lever"],
];

function swatch(mark) {
  if (mark === "raised" || mark === "lit" || mark === "flat") {
    const body = mark === "flat" ? "M2 6.5 8 3.5 14 6.5 8 9.5Z" : "M2 4.5 8 1.5 14 4.5 14 6 8 9 2 6Z";
    const crease = mark === "flat" ? "" : `<path class="iso-swatch-crease" d="M2 4.5 8 7.5 14 4.5"/>`;
    return `<svg class="iso-swatch" data-mark="${mark}" viewBox="0 0 16 10" aria-hidden="true"><path d="${body}"/>${crease}</svg>`;
  }
  return `<svg class="iso-swatch" data-mark="${mark}" viewBox="0 0 16 10" aria-hidden="true"><path d="M1.5 5h13"/></svg>`;
}

const figure = `<figure class="iso-figure iso">
  <div class="iso-plate">
    <div class="iso-plate-corners" aria-hidden="true">
      <span class="iso-plate-corner" data-corner="fig">Fig 1</span>
      <span class="iso-plate-corner" data-corner="title" data-i18n="fig.title">The dispatch desk</span>
      <span class="iso-plate-corner" data-corner="hint" data-i18n="fig.hint">Click a lane · pull the lever</span>
      <span class="iso-plate-corner" data-corner="readout" data-readout>open · 0 running</span>
    </div>
    <div class="iso-stage" tabindex="0" role="group" aria-label="The dispatch desk. Press 1 or A to submit a summarize job, 2 or B for a greet job, F for a greet job that fails, Space to pull the lever, R to start a fresh database while closed." data-i18n-aria="fig.aria">${svg}<span class="ed-sr" role="status" aria-live="polite" data-status></span></div>
  </div>
  <figcaption class="iso-legend">
    <span class="iso-keys">${keys.map(([mark, key]) => `<span class="iso-key">${swatch(mark)}<span data-i18n="${key}"></span></span>`).join("")}</span>
    <span class="iso-caption" data-i18n="fig.caption"></span>
  </figcaption>
</figure>`;

const strip = (source) => source.replace(/^export /gm, "");
const kit = strip(readFileSync(join(HERE, "kit", "iso-kit.mjs"), "utf8"));
const live = readFileSync(join(HERE, "live.js"), "utf8");
const script = `${kit}\nconst DATA = ${JSON.stringify(DATA)};\n${live}`.replace(/<\/(script)/gi, "<\\/$1");
const isoCss = k.ISO_CSS.trim();

const template = readFileSync(join(HERE, "index.html"), "utf8");
const page = template
  .replace("/* {{iso-css}} */", () => isoCss)
  .replace("<!-- {{figure}} -->", () => figure)
  .replace("/* {{i18n}} */", () => readFileSync(join(HERE, "i18n.js"), "utf8").trim())
  .replace("/* {{figure-script}} */", () => script);

writeFileSync(OUT, page);
console.log("wrote", OUT);
