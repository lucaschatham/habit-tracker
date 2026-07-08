const fs = require("fs");
const vm = require("vm");

const html = fs.readFileSync("index.html", "utf8");
const scriptMatch = html.match(/<script>([\s\S]*)<\/script>/);
if (!scriptMatch) throw new Error("index.html script block not found");
if (/\blive\b/i.test(html)) throw new Error("live language must not be present");

function makeElement(id) {
  return {
    id,
    children: [],
    dataset: {},
    style: {},
    textContent: "",
    innerHTML: "",
    className: "",
    classList: {
      add() {},
      remove() {},
      toggle() {},
    },
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    addEventListener(_event, handler) {
      this._handler = handler;
    },
  };
}

const ids = [
  "rate",
  "best",
  "hcount",
  "winlbl",
  "freshlbl",
  "lhead",
  "list",
  "lg-excused",
  "keyax-excused",
];
const elements = Object.fromEntries(ids.map((id) => [id, makeElement(id)]));

const segButtons = [makeElement("month"), makeElement("full")];
segButtons[0].dataset.w = "28";
segButtons[1].dataset.w = "84";
const chipButtons = [makeElement("all"), makeElement("fire"), makeElement("work")];
chipButtons[0].dataset.f = "all";
chipButtons[1].dataset.f = "fire";
chipButtons[2].dataset.f = "work";

const document = {
  getElementById(id) {
    if (!elements[id]) elements[id] = makeElement(id);
    return elements[id];
  },
  createElement() {
    return makeElement("created");
  },
  querySelectorAll(selector) {
    if (selector === ".seg button") return segButtons;
    if (selector === ".chip") return chipButtons;
    return [];
  },
};

vm.runInNewContext(scriptMatch[1], { document, window: {}, console });

if (!elements.freshlbl.textContent.startsWith("through ")) {
  throw new Error(`expected finalized label, got ${elements.freshlbl.textContent}`);
}
if (elements.winlbl.textContent !== "30 days") {
  throw new Error(`expected month window, got ${elements.winlbl.textContent}`);
}
if (!elements.list.children.length) {
  throw new Error("expected rendered habit rows");
}

segButtons[1]._handler();
if (elements.winlbl.textContent !== "full") {
  throw new Error(`full toggle did not update MODE, got ${elements.winlbl.textContent}`);
}

console.log("ok index smoke");
