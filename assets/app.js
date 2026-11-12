/**
 * Standalone BibTeX parser, indexer, and interactive filter UI for uExplorer.bib.
 * Zero external runtime dependencies.
 */
(function () {
  "use strict";

  const LATEX_MAP = {
    "\\&": "&",
    "$\beta$": "β",
    "$\\beta$": "β",
    "{\\'a}": "á", "{\\'e}": "é", "{\\'i}": "í", "{\\'\\i}": "í", "{\\'o}": "ó", "{\\'u}": "ú", "{\\'c}": "ć",
    "{\\`a}": "à", "{\\`e}": "è", "{\\`i}": "ì", "{\\`o}": "ò", "{\\`u}": "ù",
    "{\\\"a}": "ä", "{\\\"e}": "ë", "{\\\"i}": "ï", "{\\\"\\i}": "ï", "{\\\"o}": "ö", "{\\\"u}": "ü", "{\\\"O}": "Ö", "{\\\"U}": "Ü",
    "{\\~a}": "ã", "{\\~n}": "ñ", "{\\~o}": "õ",
    "{\\^a}": "â", "{\\^e}": "ê", "{\\^i}": "î", "{\\^o}": "ô", "{\\^u}": "û",
    "{\\c{c}}": "ç", "{\\v{s}}": "š", "{\\v{c}}": "č", "{\\v{z}}": "ž"
  };

  function decodeBibtex(text, isPages) {
    if (!text) return "";
    let out = text;
    for (const [k, v] of Object.entries(LATEX_MAP)) {
      if (out.includes(k)) {
        out = out.split(k).join(v);
      }
    }
    out = out.replace(/\\&/g, "&");
    if (isPages) {
      out = out.replace(/--/g, "–");
    }
    return out.trim();
  }

  function sanitizeTitleHtml(rawTitle) {
    const decoded = decodeBibtex(rawTitle, false);
    // Escape everything except <sup>, </sup>, <sub>, </sub>, <i>, </i>
    const escaped = decoded
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return escaped.replace(/&lt;(\/?(?:sup|sub|i))&gt;/gi, "<$1>");
  }

  function stripHtml(html) {
    return html.replace(/<[^>]*>/g, "");
  }

  function parseAuthorToken(rawToken) {
    const token = decodeBibtex(rawToken.replace(/[{}]/g, "").trim(), false);
    if (!token) return null;
    if (token.includes(",")) {
      const idx = token.indexOf(",");
      const last = token.slice(0, idx).trim();
      const first = token.slice(idx + 1).trim();
      return {
        canonical: first ? `${last}, ${first}` : last,
        display: first ? `${first} ${last}` : last,
        sortKey: (first ? `${last}, ${first}` : last).toLowerCase()
      };
    }
    const parts = token.split(/\s+/);
    if (parts.length > 1) {
      const last = parts[parts.length - 1];
      const first = parts.slice(0, -1).join(" ");
      return {
        canonical: `${last}, ${first}`,
        display: token,
        sortKey: `${last}, ${first}`.toLowerCase()
      };
    }
    return {
      canonical: token,
      display: token,
      sortKey: token.toLowerCase()
    };
  }

  function parseBibtex(text) {
    const entries = [];
    const n = text.length;
    let pos = 0;

    while (pos < n) {
      const at = text.indexOf("@", pos);
      if (at === -1) break;
      const bopen = text.indexOf("{", at);
      if (bopen === -1) break;
      const etype = text.slice(at + 1, bopen).trim().toLowerCase();
      const comma = text.indexOf(",", bopen);
      if (comma === -1) break;
      const key = text.slice(bopen + 1, comma).trim();

      let depth = 1;
      let i = comma + 1;
      while (i < n && depth > 0) {
        const ch = text[i];
        if (ch === "{") depth++;
        else if (ch === "}") depth--;
        i++;
      }

      const rawEntry = text.slice(at, i).trim();
      const body = text.slice(comma + 1, i - 1);
      const fields = {};

      let fi = 0;
      const bn = body.length;
      while (fi < bn) {
        const sub = body.slice(fi);
        const m = sub.match(/([A-Za-z0-9_-]+)\s*=\s*\{/);
        if (!m) break;
        const fname = m[1].toLowerCase();
        const vstart = fi + m.index + m[0].length;
        let vdepth = 1;
        let vi = vstart;
        while (vi < bn && vdepth > 0) {
          if (body[vi] === "{") vdepth++;
          else if (body[vi] === "}") vdepth--;
          vi++;
        }
        fields[fname] = body.slice(vstart, vi - 1).trim();
        fi = vi;
      }

      if (etype === "article" || etype === "inproceedings") {
        const authorObjs = (fields.author || "")
          .split(/\s+and\s+/i)
          .map(parseAuthorToken)
          .filter(Boolean);

        const institutions = (fields.institution || "")
          .split(";")
          .map((s) => decodeBibtex(s, false))
          .filter(Boolean);

        const keywords = (fields.keywords || "")
          .split(";")
          .map((s) => decodeBibtex(s, false))
          .filter(Boolean);

        const titleHtml = sanitizeTitleHtml(fields.title || "");
        const titlePlain = stripHtml(titleHtml);
        const journal = decodeBibtex(fields.journal || fields.booktitle || "", false);
        const year = (fields.year || "Unknown").trim();
        const volume = (fields.volume || "").trim();
        const number = (fields.number || "").trim();
        const pages = decodeBibtex(fields.pages || "", true);
        const doi = (fields.doi || "").trim();
        const pmid = (fields.pmid || "").trim();
        const url = (fields.url || "").trim();

        const searchBlob = [
          key,
          titlePlain,
          authorObjs.map((a) => `${a.display} ${a.canonical}`).join(" "),
          journal,
          year,
          volume,
          pages,
          doi,
          pmid,
          institutions.join(" "),
          keywords.join(" ")
        ]
          .join(" ")
          .toLowerCase();

        entries.push({
          type: etype,
          key,
          raw: rawEntry,
          titleHtml,
          titlePlain,
          authorObjs,
          authors: authorObjs.map((a) => a.canonical),
          journal,
          year,
          volume,
          number,
          pages,
          doi,
          pmid,
          url,
          institutions,
          keywords,
          searchBlob
        });
      }
      pos = i;
    }
    return entries;
  }

  function sortYears(years) {
    return Array.from(years).sort((a, b) => {
      if (a === "Just Accepted") return -1;
      if (b === "Just Accepted") return 1;
      const na = parseInt(a, 10);
      const nb = parseInt(b, 10);
      if (!isNaN(na) && !isNaN(nb)) return nb - na;
      return b.localeCompare(a);
    });
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  let allEntries = [];
  const state = {
    year: "",
    author: "",
    firstAuthor: "",
    journal: "",
    institution: "",
    keyword: "",
    q: ""
  };

  function syncStateFromUrl() {
    const params = new URLSearchParams(window.location.search);
    state.year = params.get("year") || "";
    state.author = params.get("author") || "";
    state.firstAuthor = params.get("first_author") || "";
    state.journal = params.get("journal") || "";
    state.institution = params.get("institution") || "";
    state.keyword = params.get("tag") || params.get("keyword") || "";
    state.q = params.get("q") || "";
  }

  function syncUrlFromState() {
    const params = new URLSearchParams();
    if (state.year) params.set("year", state.year);
    if (state.author) params.set("author", state.author);
    if (state.firstAuthor) params.set("first_author", state.firstAuthor);
    if (state.journal) params.set("journal", state.journal);
    if (state.institution) params.set("institution", state.institution);
    if (state.keyword) params.set("tag", state.keyword);
    if (state.q) params.set("q", state.q);
    const qs = params.toString();
    const newUrl = window.location.pathname + (qs ? `?${qs}` : "") + window.location.hash;
    window.history.replaceState(null, "", newUrl);
  }

  function populateSelect(selectEl, defaultLabel, countsMap, customSorter) {
    const keys = customSorter
      ? customSorter(Object.keys(countsMap))
      : Object.keys(countsMap).sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));
    const html = [`<option value="">${escapeHtml(defaultLabel)}</option>`];
    for (const k of keys) {
      html.push(`<option value="${escapeHtml(k)}">${escapeHtml(k)} (${countsMap[k]})</option>`);
    }
    selectEl.innerHTML = html.join("");
  }

  function buildControls(entries) {
    const yearCounts = {};
    const authorCounts = {};
    const journalCounts = {};
    const instCounts = {};
    const kwCounts = {};

    for (const e of entries) {
      yearCounts[e.year] = (yearCounts[e.year] || 0) + 1;
      if (e.journal) {
        journalCounts[e.journal] = (journalCounts[e.journal] || 0) + 1;
      }
      for (const a of e.authors) {
        authorCounts[a] = (authorCounts[a] || 0) + 1;
      }
      for (const inst of e.institutions) {
        instCounts[inst] = (instCounts[inst] || 0) + 1;
      }
      for (const kw of e.keywords) {
        kwCounts[kw] = (kwCounts[kw] || 0) + 1;
      }
    }

    populateSelect(document.getElementById("filter-year"), "Search year", yearCounts, sortYears);
    populateSelect(document.getElementById("filter-author"), "Search author", authorCounts);
    populateSelect(document.getElementById("filter-journal"), "Search journal", journalCounts);
    populateSelect(document.getElementById("filter-institution"), "Search institution", instCounts);
    populateSelect(document.getElementById("filter-keyword"), "Search tag", kwCounts);
  }

  function renderMetricCard(title, metaText, rows, filterType, fillClass, activeVal) {
    const maxCount = rows.reduce((m, r) => Math.max(m, r[1]), 1);
    const rowsHtml = rows.length
      ? rows
          .map(([label, count]) => {
            const pct = Math.max(4, Math.round((count / maxCount) * 100));
            const isActive = activeVal && activeVal === label ? " active" : "";
            return `<div class="metric-row${isActive}" data-filter-type="${escapeHtml(
              filterType
            )}" data-filter-value="${escapeHtml(label)}" title="${escapeHtml(label)}: ${count} (click to filter)">
              <span class="metric-label">${escapeHtml(label)}</span>
              <div class="metric-bar-track"><div class="metric-bar-fill ${fillClass}" style="width:${pct}%"></div></div>
              <span class="metric-val">${count}</span>
            </div>`;
          })
          .join("")
      : `<div class="metric-card-meta">No data</div>`;

    return `<div class="metric-card">
      <div class="metric-card-header">
        <h4 class="metric-card-title">${escapeHtml(title)}</h4>
        <span class="metric-card-meta">${escapeHtml(metaText)}</span>
      </div>
      <div class="metric-bars">${rowsHtml}</div>
    </div>`;
  }

  function updateStatsAndMetrics(entries) {
    const yearCounts = {};
    const authorCounts = {};
    const firstAuthorCounts = {};
    const journalCounts = {};
    const instCounts = {};
    const kwCounts = {};
    let multiCenterCount = 0;

    for (const e of entries) {
      yearCounts[e.year] = (yearCounts[e.year] || 0) + 1;
      if (e.journal) {
        journalCounts[e.journal] = (journalCounts[e.journal] || 0) + 1;
      }
      if (e.authors.length > 0) {
        const first = e.authors[0];
        firstAuthorCounts[first] = (firstAuthorCounts[first] || 0) + 1;
      }
      for (const a of e.authors) {
        authorCounts[a] = (authorCounts[a] || 0) + 1;
      }
      if (e.institutions.length > 1) {
        multiCenterCount++;
      }
      for (const inst of e.institutions) {
        instCounts[inst] = (instCounts[inst] || 0) + 1;
      }
      for (const kw of e.keywords) {
        kwCounts[kw] = (kwCounts[kw] || 0) + 1;
      }
    }

    const statsEl = document.getElementById("stats-metrics");
    if (statsEl) {
      const jaCount = yearCounts["Just Accepted"] || 0;
      statsEl.innerHTML = [
        `<span><strong>${entries.length}</strong> Publications</span>`,
        jaCount ? `<span><strong>${jaCount}</strong> Just Accepted</span>` : "",
        `<span><strong>${Object.keys(journalCounts).length}</strong> Journals</span>`,
        `<span><strong>${Object.keys(instCounts).length}</strong> Institutions</span>`,
        `<span><strong>${Object.keys(kwCounts).length}</strong> Tags</span>`
      ]
        .filter(Boolean)
        .join("");
    }

    const subEl = document.getElementById("metrics-summary-sub");
    if (subEl) {
      subEl.textContent =
        entries.length === allEntries.length
          ? `All ${allEntries.length} publications · Click any bar to filter`
          : `Filtered subset (${entries.length} of ${allEntries.length}) · Click any bar to filter`;
    }

    const gridEl = document.getElementById("metrics-grid");
    if (!gridEl) return;

    const topN = (map, n = 10) =>
      Object.entries(map)
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
        .slice(0, n);

    const yearRows = sortYears(Object.keys(yearCounts))
      .slice(0, 10)
      .map((y) => [y, yearCounts[y]]);

    const multiPct = entries.length ? ((multiCenterCount / entries.length) * 100).toFixed(1) : "0.0";

    gridEl.innerHTML = [
      renderMetricCard(
        "Annual Trend",
        `${Object.keys(yearCounts).length} yrs`,
        yearRows,
        "year",
        "fill-year",
        state.year
      ),
      renderMetricCard(
        "Top Institutions",
        `${multiPct}% multi-center`,
        topN(instCounts, 10),
        "institution",
        "fill-inst",
        state.institution
      ),
      renderMetricCard(
        "Top Journals",
        `${Object.keys(journalCounts).length} total`,
        topN(journalCounts, 10),
        "journal",
        "fill-journal",
        state.journal
      ),
      renderMetricCard(
        "Top Tags & Themes",
        `${Object.keys(kwCounts).length} total`,
        topN(kwCounts, 10),
        "keyword",
        "fill-tag",
        state.keyword
      ),
      renderMetricCard(
        "Top Authors",
        `${Object.keys(authorCounts).length} total`,
        topN(authorCounts, 10),
        "author",
        "fill-author",
        state.author
      ),
      renderMetricCard(
        "Top 1st Authors",
        "1st position only",
        topN(firstAuthorCounts, 10),
        "firstAuthor",
        "fill-first-author",
        state.firstAuthor
      )
    ].join("");
  }

  function renderAuthorList(authorObjs) {
    if (!authorObjs.length) return "";
    const spans = authorObjs.map(
      (a) =>
        `<span class="bib-author-item" data-filter-type="author" data-filter-value="${escapeHtml(
          a.canonical
        )}" title="Filter by ${escapeHtml(a.canonical)}">${escapeHtml(a.display)}</span>`
    );
    if (spans.length === 1) return spans[0];
    if (spans.length === 2) return `${spans[0]} and ${spans[1]}`;
    return `${spans.slice(0, -1).join(", ")}, and ${spans[spans.length - 1]}`;
  }

  function renderEntry(e) {
    const authorsHtml = renderAuthorList(e.authorObjs);
    let journalPart = "";
    if (e.journal) {
      journalPart = `<span class="bib-journal" data-filter-type="journal" data-filter-value="${escapeHtml(
        e.journal
      )}" title="Filter by journal">${escapeHtml(e.journal)}</span>`;
    }
    let volIssuePages = "";
    if (e.volume) {
      volIssuePages += `, <span class="bib-volume">${escapeHtml(e.volume)}</span>`;
    }
    if (e.number) {
      volIssuePages += `(${escapeHtml(e.number)})`;
    }
    if (e.pages) {
      volIssuePages += `: ${escapeHtml(e.pages)}`;
    }

    const metaParts = [];
    if (e.doi) {
      metaParts.push(
        `[<a class="ext-link" href="https://doi.org/${encodeURIComponent(e.doi).replace(/%2F/gi, "/")}" target="_blank" rel="noopener">doi link</a>]`
      );
    }
    if (e.pmid) {
      metaParts.push(
        `[<a class="ext-link" href="https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(e.pmid)}/" target="_blank" rel="noopener">PubMed</a>]`
      );
    }
    if (e.url) {
      metaParts.push(
        `[<a class="ext-link" href="${escapeHtml(e.url)}" target="_blank" rel="noopener">related link</a>]`
      );
    }
    metaParts.push(
      `[<button type="button" class="bib-action-btn" data-action="toggle-bib" data-key="${escapeHtml(
        e.key
      )}">BibTeX</button>]`
    );

    if (e.institutions.length) {
      const instSpans = e.institutions
        .map(
          (inst) =>
            `<span class="bib-inst" data-filter-type="institution" data-filter-value="${escapeHtml(
              inst
            )}" title="Filter by institution">${escapeHtml(inst)}</span>`
        )
        .join("; ");
      metaParts.push(`| ${instSpans}`);
    }

    if (e.keywords.length) {
      const kwSpans = e.keywords
        .map(
          (kw) =>
            `<span class="bib-tag" data-filter-type="keyword" data-filter-value="${escapeHtml(
              kw
            )}" title="Filter by tag">${escapeHtml(kw)}</span>`
        )
        .join("; ");
      metaParts.push(`| <span class="bib-tag-label">Tag:</span> ${kwSpans}`);
    }

    return `<div class="bib-entry" id="entry-${escapeHtml(e.key)}">
      <div class="bib-title">• ${e.titleHtml}</div>
      <div class="bib-citation">${authorsHtml ? authorsHtml + ". " : ""}${journalPart}${volIssuePages}</div>
      <div class="bib-meta">${metaParts.join(" ")}</div>
      <pre class="bib-raw-drawer" id="raw-${escapeHtml(e.key)}">${escapeHtml(e.raw)}</pre>
    </div>`;
  }

  function applyFilters() {
    const qTerms = state.q
      .trim()
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean);

    const filtered = allEntries.filter((e) => {
      if (state.year && e.year !== state.year) return false;
      if (state.author && !e.authors.includes(state.author)) return false;
      if (state.firstAuthor && e.authors[0] !== state.firstAuthor) return false;
      if (state.journal && e.journal !== state.journal) return false;
      if (state.institution && !e.institutions.includes(state.institution)) return false;
      if (state.keyword && !e.keywords.includes(state.keyword)) return false;
      for (const term of qTerms) {
        if (!e.searchBlob.includes(term)) return false;
      }
      return true;
    });

    updateStatsAndMetrics(filtered);
    renderList(filtered);
    renderFilterStatus(filtered.length, allEntries.length);
    syncUrlFromState();
  }

  function renderFilterStatus(shownCount, totalCount) {
    const countEl = document.getElementById("filter-count");
    if (countEl) {
      countEl.textContent =
        shownCount === totalCount
          ? `Showing all ${totalCount} publications`
          : `Showing ${shownCount} of ${totalCount} publications`;
    }

    const chipsEl = document.getElementById("active-chips");
    if (!chipsEl) return;
    const chips = [];
    const labels = {
      year: "Year",
      author: "Author",
      firstAuthor: "1st Author",
      journal: "Journal",
      institution: "Institution",
      keyword: "Tag",
      q: "Search"
    };
    for (const [k, label] of Object.entries(labels)) {
      if (state[k]) {
        chips.push(
          `<span class="filter-chip" data-clear-key="${k}" title="Remove filter">${label}: ${escapeHtml(
            state[k]
          )} &times;</span>`
        );
      }
    }
    chipsEl.innerHTML = chips.join("");
  }

  function renderList(entries) {
    const container = document.getElementById("bib_list");
    const yearJumpEl = document.getElementById("year-jump");
    if (!entries.length) {
      container.innerHTML = `<div class="empty-state"><p>No publications match the current filters.</p><button type="button" class="btn" onclick="window.resetBibFilters()">Reset Filters</button></div>`;
      if (yearJumpEl) yearJumpEl.innerHTML = "";
      return;
    }

    const byYear = {};
    for (const e of entries) {
      if (!byYear[e.year]) byYear[e.year] = [];
      byYear[e.year].push(e);
    }

    const sortedYears = sortYears(Object.keys(byYear));

    if (yearJumpEl) {
      yearJumpEl.innerHTML =
        `<span class="year-jump-label">Jump to:</span>` +
        sortedYears
          .map((y) => {
            const anchor = "year-" + y.replace(/\s+/g, "-");
            return `<a class="year-pill" href="#${escapeHtml(anchor)}">${escapeHtml(y)} (${byYear[y].length})</a>`;
          })
          .join("");
    }

    const groupHtml = sortedYears.map((y) => {
      const groupEntries = byYear[y];
      const anchor = "year-" + y.replace(/\s+/g, "-");
      return `<section class="year-group" id="${escapeHtml(anchor)}">
        <div class="year-header">
          <h3>${escapeHtml(y)}<span class="year-count">(${groupEntries.length})</span></h3>
          <a class="back-top" href="#top">[top]</a>
        </div>
        <div class="year-items">
          ${groupEntries.map(renderEntry).join("\n")}
        </div>
      </section>`;
    });

    container.innerHTML = groupHtml.join("\n");
  }

  function syncControlsFromState() {
    document.getElementById("filter-year").value = state.year;
    document.getElementById("filter-author").value = state.author;
    document.getElementById("filter-journal").value = state.journal;
    document.getElementById("filter-institution").value = state.institution;
    document.getElementById("filter-keyword").value = state.keyword;
    document.getElementById("searchbar").value = state.q;
  }

  function setFilter(key, value) {
    state[key] = state[key] === value ? "" : value;
    syncControlsFromState();
    applyFilters();
  }

  window.resetBibFilters = function () {
    state.year = "";
    state.author = "";
    state.firstAuthor = "";
    state.journal = "";
    state.institution = "";
    state.keyword = "";
    state.q = "";
    syncControlsFromState();
    applyFilters();
  };

  // Alias for backward compatibility
  window.reset = window.resetBibFilters;

  async function init() {
    const listEl = document.getElementById("bib_list");
    try {
      const resp = await fetch("./uExplorer.bib", { cache: "no-cache" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const bibText = await resp.text();
      allEntries = parseBibtex(bibText);
      buildControls(allEntries);
      syncStateFromUrl();
      syncControlsFromState();
      applyFilters();
    } catch (err) {
      listEl.innerHTML = `<div class="empty-state">Failed to load uExplorer.bib: ${escapeHtml(err.message)}</div>`;
      return;
    }

    const bindSelect = (id, key) => {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener("change", () => {
          state[key] = el.value;
          applyFilters();
        });
      }
    };

    bindSelect("filter-year", "year");
    bindSelect("filter-author", "author");
    bindSelect("filter-journal", "journal");
    bindSelect("filter-institution", "institution");
    bindSelect("filter-keyword", "keyword");

    const searchEl = document.getElementById("searchbar");
    if (searchEl) {
      searchEl.addEventListener("input", () => {
        state.q = searchEl.value;
        applyFilters();
      });
    }

    document.getElementById("active-chips")?.addEventListener("click", (ev) => {
      const chip = ev.target.closest("[data-clear-key]");
      if (chip) {
        setFilter(chip.getAttribute("data-clear-key"), "");
      }
    });

    document.getElementById("metrics-grid")?.addEventListener("click", (ev) => {
      const row = ev.target.closest("[data-filter-type]");
      if (row) {
        setFilter(row.getAttribute("data-filter-type"), row.getAttribute("data-filter-value"));
      }
    });

    listEl.addEventListener("click", (ev) => {
      const filterTarget = ev.target.closest("[data-filter-type]");
      if (filterTarget) {
        const fType = filterTarget.getAttribute("data-filter-type");
        const fVal = filterTarget.getAttribute("data-filter-value");
        setFilter(fType, fVal);
        return;
      }

      const actionBtn = ev.target.closest("[data-action='toggle-bib']");
      if (actionBtn) {
        const key = actionBtn.getAttribute("data-key");
        const drawer = document.getElementById(`raw-${key}`);
        if (drawer) {
          const isOpen = drawer.classList.toggle("open");
          if (isOpen && navigator.clipboard) {
            navigator.clipboard.writeText(drawer.textContent).then(() => {
              const orig = actionBtn.textContent;
              actionBtn.textContent = "Copied BibTeX!";
              setTimeout(() => {
                actionBtn.textContent = orig;
              }, 1400);
            }).catch(() => {});
          }
        }
      }
    });

    const searchPanel = document.getElementById("bib_search");
    if (searchPanel && typeof ResizeObserver !== "undefined") {
      const updateOffset = () => {
        document.documentElement.style.setProperty("--search-panel-height", `${searchPanel.offsetHeight}px`);
      };
      updateOffset();
      new ResizeObserver(updateOffset).observe(searchPanel);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
