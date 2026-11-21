// Port of src/triage/events.py and src/triage/sanitise.py.
// Python's \w, \d and \b are Unicode-aware; JavaScript's are ASCII-only, so they are spelled
// out with Unicode property classes here. Strings are handled by code point, as in Python.

const W = "[\\p{L}\\p{N}_]";
const B = `(?:(?<!${W})(?=${W})|(?<=${W})(?!${W}))`;
const DIGITS = /\p{Nd}+/gu;
const WORD = /[a-z<>_']+/g;

// (pattern, event name, action label) — same order as Python, first match wins.
const RULES = [
  [/^account has been pulled up/u, "pull_up", "pull-up-account"],
  [/^identity verification in prog/u, "verify", "verify-identity"],
  [/^purchase validation in prog/u, "validate", "validate-purchase"],
  [/^searching the faq pages/u, "search_faq", "search-faq"],
  [/^querying the system for (?<v>.*)/u, "query", null],
  [/^querying the system/u, "query", null],
  [/^agent is looking/u, "looking", null],
  [new RegExp(`^system action: search (?<v>${W}+)`, "u"), "search_topic", null],
  [/^system action: (?<v>.*)/u, "sys", null],
  [/^membership level of ?(?<v>.*?) ?has been noted/u, "membership", "membership"],
  [/^shipping status of ?(?<v>.*?) ?has been noted/u, "shipping", "shipping-status"],
  [/^details of ?(?<v>.*?) ?have been entered/u, "details", "enter-details"],
  [/^a reason of ?(?<v>.*?) ?has been recorded/u, "reason", "record-reason"],
  [/^order has been updated with (?<v>.*)/u, "order_updated", "update-order"],
  [/^account has been updated with (?<v>.*)/u, "account_updated", "update-account"],
  [new RegExp(`^faq answer related to (?<v>${W}+)`, "u"), "faq_selected", "select-faq"],
  [/^a refund has been made/u, "refund", "offer-refund"],
  [/^a promo code has been created/u, "promo", "promo-code"],
  [/^a purchase of ?.*was made/u, "purchase", "make-purchase"],
  [/^a password has been generated/u, "password", "make-password"],
  [/^a link will be sent/u, "link", "send-link"],
  [/team has been notified|department has been notified|has been notified/u, "notified", "notify-team"],
];

const pyStrip = (s) => s.replace(/^\s+|\s+$/gu, "");

export function parseEvent(text) {
  for (const [pattern, name, action] of RULES) {
    const m = pattern.exec(text);
    if (m) {
      let value = pyStrip((m.groups && m.groups.v) || "");
      value = value.replace(DIGITS, "#");
      const words = (value.match(WORD) || []).slice(0, 2);
      return [name, words.length ? words : (value.includes("#") ? ["#"] : []), action];
    }
  }
  const words = (text.replace(DIGITS, "").match(WORD) || []).slice(0, 4);
  return [words.length ? "other_" + words.join("_") : "other", [], null];
}

export function doneActions(turns) {
  const done = new Set();
  for (const t of turns) {
    if (t.speaker === "action") {
      const a = parseEvent(t.text)[2];
      if (a) done.add(a);
    }
  }
  return done;
}

// ------------------------------------------------------------------ sanitise

export const MAX_TURN_CHARS = 20000;
export const MAX_TURN_TOKENS = 80;
export const HEAD_TOKENS = 50;
export const TAIL_TOKENS = MAX_TURN_TOKENS - HEAD_TOKENS;
export const MAX_TOKEN_CHARS = 40;
export const MAX_TURNS = 8;
export const SPEAKERS = ["customer", "agent", "action"];

const INJECTION = new RegExp(
  "ignore (all |any |your |the |previous |prior |above )+(instruction|rule|polic|prompt)" +
  "|disregard (all |any |your |the |previous |prior )+(instruction|rule|polic)" +
  `|${B}new instruction` +
  `|${B}system\\s*:` +
  `|${B}system prompt${B}` +
  `|</?\\s*(context|system|instruction|prompt)${B}` +
  `|${B}needs_human${B}` +
  `|${B}from now on${B}` +
  `|${B}you are now (a|an|in|the|my|acting)${B}` +
  `|${B}override (the |your )?(polic|rule|instruction)` +
  `|${B}developer mode${B}` +
  `|${B}jailbreak${B}`, "u");

const CC = /^\p{Cc}$/u, CF = /^\p{Cf}$/u, BAD = /^[\p{Cs}\p{Co}\p{Cn}]$/u;
const WS = /\s+/gu;
const ALNUM = /[\p{L}\p{N}]/u;

export function looksLikeSystemEvent(text) {
  return text.split(/[.!?]\s+|\.\.\./u).some(
    (part) => pyStrip(part) && !parseEvent(pyStrip(part))[0].startsWith("other"));
}

export function cleanText(raw) {
  const flags = { had_control: false, had_format: false, truncated: false };
  let cps = Array.from(raw);
  if (cps.length > MAX_TURN_CHARS) {
    const half = MAX_TURN_CHARS / 2;
    raw = cps.slice(0, half).join("") + " " + cps.slice(-half).join("");
    flags.truncated = true;
  }
  // Also returned: what was removed, so the site can show it.
  const removed = [];
  const out = [];
  for (const ch of raw.normalize("NFKC")) {
    if ("\n\r\t\v\f".includes(ch)) { out.push(" "); continue; }
    if (CC.test(ch)) { flags.had_control = true; removed.push(ch); continue; }
    if (CF.test(ch)) { flags.had_format = true; removed.push(ch); continue; }
    if (BAD.test(ch)) { flags.had_control = true; removed.push(ch); continue; }
    if (ch === "︎" || ch === "️") continue;
    out.push(ch);
  }
  const text = out.join("").replace(WS, " ").trim().toLowerCase();
  return { text, flags, removed };
}

function capTokens(tokens) {
  tokens = tokens.map((t) => (t.length > MAX_TOKEN_CHARS ? Array.from(t).slice(0, MAX_TOKEN_CHARS).join("") : t));
  if (tokens.length <= MAX_TURN_TOKENS) return [tokens, false];
  return [tokens.slice(0, HEAD_TOKENS).concat(tokens.slice(-TAIL_TOKENS)), true];
}

export function cleanContext(context) {
  const flags = { had_control: false, had_format: false, truncated: false,
                  injection_pattern: false, empty_last_customer: false };
  const turns = [];
  for (const item of context.slice(-MAX_TURNS)) {
    const c = cleanText(item.text);
    for (const k of Object.keys(c.flags)) flags[k] = flags[k] || c.flags[k];
    let text = c.text;
    const [tokens, cut] = capTokens(text ? text.split(" ") : []);
    flags.truncated = flags.truncated || cut;
    if (cut) text = tokens.join(" ");
    let injection = false;
    if (item.speaker === "customer" && (INJECTION.test(text) || looksLikeSystemEvent(text))) {
      flags.injection_pattern = true;
      injection = true;
    }
    turns.push({ speaker: item.speaker, text, tokens, raw: item.text, removed: c.removed, injection });
  }
  const customer = turns.filter((t) => t.speaker === "customer");
  if (customer.length && !customer[customer.length - 1].text) flags.empty_last_customer = true;
  const usable = turns.some((t) => ALNUM.test(t.text));
  return { turns, flags, usable };
}
