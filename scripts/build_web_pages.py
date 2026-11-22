#!/usr/bin/env python3
"""Build the site's report pages from the repository's own markdown.

    python scripts/build_web_pages.py

  web/log.html         the full experiment log, edited for the public site
  web/model-card.html  the model card, with the ABCD data credit

The repository files are written for a technical review and stay as they are. The site
versions apply a fixed list of exact edits (SITE_EDITS) and drop the entries in DROP, so the
pages read as a project report. Every edit must match exactly once; if the source changes
under it, this script stops instead of publishing a half-edited page.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (old, new) pairs applied to EXPERIMENT_LOG.md for the site. Each must occur exactly once.
SITE_EDITS = [
    ("scored by the unmodified official `grader.py`.", "scored by the benchmark's own unmodified scoring script."),
    ("listed only because the plan's architecture choice leaned on it. Every number in the\nsubmission comes from the runs below.",
     "listed only because the plan's architecture choice leaned on it. Every number on this\nsite comes from the runs below."),
    ("Copied the 12 OP-06 files from the challenge repository at commit\n`d87699bb97de6504b33f681eed66918a4d433ba0`. `scripts/check_reference.py` checks them against\n`reference/SHA256SUMS`, and those hashes were checked against `RELEASE_MANIFEST.json`.",
     "Copied the benchmark's 12 files (data, scoring script, baseline) at a pinned commit.\n`scripts/check_reference.py` checks them against `reference/SHA256SUMS`, the hashes published\nwith that release."),
    ("Baseline, trained on `train.jsonl.gz`, scored by the official grader:", "Baseline, trained on `train.jsonl.gz`, scored by the benchmark's scoring script:"),
    ("## 2026-11-17 — Submitted runs (`dev-005-http`, `hostile-003`, `bench-win2-*`)",
     "## 2026-11-17 — Final runs on the laptop (`dev-005-http`, `hostile-003`, `bench-win2-*`)"),
    ("This is the submitted run. Its artifact is in `results/raw/ci-44135706221/`; the failed first",
     "This became the reference result. Its artifact is in `results/raw/ci-44135706221/`; the failed first"),
    ("manifest listed them, so a reviewer would have found missing evidence, including the failed",
     "manifest listed them, so anyone checking would have found missing evidence, including the failed"),
    ("at 90% accuracy. Dev [dev-006]: grader metrics unchanged", "at 90% accuracy. Dev [dev-006]: scored metrics unchanged"),
    ("in the sixth decimal, as before between this CPU and the laptop. This is now the submitted\nrun; the artifact is in `results/raw/ci-44775973227/`.",
     "in the sixth decimal, as before between this CPU and the laptop. The numbers on this site\ncome from this run; the artifact is in `results/raw/ci-44775973227/`."),
    ("`eb8d8c0896f96f46`), so a reviewer who retrains on Linux gets a model that behaves the same",
     "`eb8d8c0896f96f46`), so anyone who retrains on Linux gets a model that behaves the same"),
]
# Entries left out of the site version (they are about the repository, not the experiments).
DROP = ["## 2026-11-20 — History split into smaller commits"]

CARD_EDITS = [
    ("out of fold, as the service measures it (EXPERIMENT_LOG.md, 2026-11-20).", "out of fold, as the service measures it (experiment log, 20 November)."),
    ("training (EXPERIMENT_LOG.md, 2026-11-17, hostile-002); retraining writes it by default.",
     "training (experiment log, 17 November, hostile-002); retraining writes it by default."),
    ("weak on the next step at procedure branch points. See ANALYSIS.md.", "weak on the next step at procedure branch points."),
]

SUMMARY = (
    "Mentat triages customer-support conversations. It reads the last eight turns and returns the customer's "
    "problem (one of 96), the next step the written procedure allows (one of 30), how sure it is, and whether a "
    "person should check. Three linear classifiers read the words, who said them and which system steps already "
    "ran; a rule table the support manager edits removes any step the procedure does not allow; a second model, "
    "trained on the first one's mistakes, turns scores into a confidence. No language model decides anything.\n\n"
    "On 2,300 development conversations it picks the right next step 82% of the time, against 39% for the "
    "published baseline, and when it answers without a person it is right 91% of the time. An LLM re-ranker made "
    "it worse and was not used. Noisy training copies and character fragments changed nothing measurable. A "
    "confidence bug on Hinglish messages was found and fixed. Every run is below in the order it happened, failed "
    "ones included."
)


def edit(text: str, edits, name: str) -> str:
    for old, new in edits:
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"{name}: expected one match, found {n}: {old[:70]!r}")
        text = text.replace(old, new)
    return text


def drop(text: str, heads) -> str:
    for head in heads:
        start = text.find(head)
        if start < 0:
            raise SystemExit(f"entry to drop not found: {head!r}")
        end = text.find("\n## ", start + 1)
        text = text[:start] + (text[end + 1:] if end >= 0 else "")
    return text


def abcd_credit() -> str:
    """The ABCD credit with its MIT notice word for word, taken from the repository's LICENSE."""
    lic = (ROOT / "LICENSE").read_text(encoding="utf-8")
    notice = lic[lic.index("Permission is hereby granted"):].strip()
    notice = " ".join(line.strip() for line in notice.splitlines())
    return ("\n\n## Data credit\n\nThe conversations, labels and written procedures come from ABCD, the "
            "Action-Based Conversations Dataset (https://github.com/asappresearch/abcd). MIT licence, "
            "Copyright (c) ASAPP Inc.\n\n" + notice + "\n")


# ---------------------------------------------------------------- a small markdown renderer
def inline(text: str) -> str:
    out, pos = [], 0
    for m in re.finditer(r"`([^`]+)`", text):
        out.append(_fmt(text[pos:m.start()]))
        out.append(f"<code>{html.escape(m.group(1))}</code>")
        pos = m.end()
    out.append(_fmt(text[pos:]))
    return "".join(out)


def _fmt(t: str) -> str:
    t = html.escape(t, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', t)
    t = re.sub(r"(?<![\"'=])(https?://[^\s<)]+)", r'<a href="\1">\1</a>', t)
    return t


def render(md: str):
    lines = md.splitlines()
    out, toc, i, title = [], [], 0, ""
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            text = line[level:].strip()
            if level == 1:
                title = title or text
                i += 1
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]
            out.append(f'<h{level} id="{slug}">{inline(text)}</h{level}>')
            if level == 2:
                toc.append((slug, text))
            i += 1
        elif line.strip() == "---":
            out.append("<hr>")
            i += 1
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            body = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c or "--") for c in r)]
            head, rest = body[0], body[1:]
            thead = "" if not any(head) else "<thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead>"
            out.append(f'<div class="table"><table>{thead}<tbody>'
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rest)
                       + "</tbody></table></div>")
        elif re.match(r"^(\d+\.|-) ", line):
            ordered = line[0].isdigit()
            items = []
            while i < len(lines) and lines[i].strip() and (re.match(r"^(\d+\.|-) ", lines[i]) or lines[i].startswith("  ")):
                l = lines[i]
                if re.match(r"^  +(\d+\.|-) ", l) and items:
                    items[-1][1].append(re.sub(r"^\s*(\d+\.|-) ", "", l))
                elif l.startswith("  ") and items:
                    if items[-1][1]:
                        items[-1][1][-1] += " " + l.strip()
                    else:
                        items[-1][0] += " " + l.strip()
                else:
                    items.append([re.sub(r"^(\d+\.|-) ", "", l), []])
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(
                f"<li>{inline(t)}" + ("<ul>" + "".join(f"<li>{inline(s)}</li>" for s in subs) + "</ul>" if subs else "") + "</li>"
                for t, subs in items) + f"</{tag}>")
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||---$|(\d+\.|-) )", lines[i]):
                para.append(lines[i].strip())
                i += 1
            out.append(f"<p>{inline(' '.join(para))}</p>")
    return title, toc, "\n".join(out)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Mentat</title>
<meta name="theme-color" content="#0b0c10">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,300..900&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="site.css">
<link rel="stylesheet" href="doc.css">
</head>
<body class="doc">
<header class="top doc-bar">
  <a class="mark" href="index.html">MENTAT</a>
  <nav aria-label="Pages">
    <a href="index.html">Home</a>
    <a href="log.html"{log_cur}>Experiment log</a>
    <a href="model-card.html"{card_cur}>Model card</a>
  </nav>
  <button class="pdf" type="button" onclick="window.print()">Save as PDF</button>
</header>
<div class="report">
  <nav class="contents" aria-label="Contents">
    <p class="contents-title">Contents</p>
    <ol>{toc}</ol>
  </nav>
  <article class="doc-body">
    <p class="kicker">{kicker}</p>
    <h1>{title}</h1>
    <p class="byline"><a href="https://www.linkedin.com/in/vidit-choudhary">Vidit Choudhary</a></p>
    <p class="doc-status">{status}</p>
    {summary}
    {body}
  </article>
</div>
<footer class="doc-foot"><p>&copy; 2026 <a href="https://www.linkedin.com/in/vidit-choudhary">Vidit Choudhary</a></p></footer>
<script>
// Highlight the contents entry for the section being read.
const links = [...document.querySelectorAll('.contents a')];
const byId = new Map(links.map((a) => [a.getAttribute('href').slice(1), a]));
const io = new IntersectionObserver((es) => es.forEach((e) => {{
  if (!e.isIntersecting) return;
  links.forEach((a) => a.removeAttribute('aria-current'));
  const a = byId.get(e.target.id); if (a) {{ a.setAttribute('aria-current', 'true'); a.scrollIntoView({{ block: 'nearest' }}); }}
}}), {{ rootMargin: '-20% 0px -70% 0px' }});
document.querySelectorAll('.doc-body h2[id]').forEach((h) => io.observe(h));
</script>
</body>
</html>
"""


def page(dst: str, title: str, kicker: str, status: str, summary: str, toc, body: str) -> None:
    toc_html = "".join(f'<li><a href="#{slug}">{inline(text)}</a></li>' for slug, text in toc)
    summary_html = ("<section class=\"summary\" id=\"summary\"><h2>Summary</h2>"
                    + "".join(f"<p>{inline(p)}</p>" for p in summary.split("\n\n")) + "</section>") if summary else ""
    if summary:
        toc_html = '<li><a href="#summary">Summary</a></li>' + toc_html
    out = PAGE.format(title=html.escape(title), kicker=kicker, status=status, summary=summary_html, toc=toc_html, body=body,
                      log_cur=' aria-current="page"' if dst == "log.html" else "",
                      card_cur=' aria-current="page"' if dst == "model-card.html" else "")
    (ROOT / "web" / dst).write_text(out, encoding="utf-8", newline="\n")
    print(dst, len(out), "bytes,", len(toc), "sections")


def main() -> int:
    log = (ROOT / "EXPERIMENT_LOG.md").read_text(encoding="utf-8")
    log = drop(edit(log, SITE_EDITS, "EXPERIMENT_LOG.md"), DROP)
    for word in ("grader", "submission", "submitted", "reviewer", "OP-06", "challenge"):
        if re.search(word, log, re.I):
            raise SystemExit(f"site log still says {word!r}")
    _, toc, body = render(log)
    page("log.html", "Mentat: experiment log", "Full report",
         "Experiment log, 17 to 22 November 2026. Every run in the order it happened, failed ones included. "
         "Raw outputs for each run are kept with the code.", SUMMARY, toc, body)

    card = edit((ROOT / "models" / "MODEL_CARD.md").read_text(encoding="utf-8"), CARD_EDITS, "MODEL_CARD.md")
    _, toc, body = render("## The model\n\n" + card.split("\n", 1)[1] + abcd_credit())
    page("model-card.html", "Mentat: model card", "Model card",
         "The model the site runs: what it is, what it was trained on, how it scores, and its limits.", "", toc, body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
