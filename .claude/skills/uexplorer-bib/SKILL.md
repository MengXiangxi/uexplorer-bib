---
name: uexplorer-bib
description: Add, update ("Just Accepted" to formally published), or audit BibTeX citation entries in uExplorer.bib for academic papers involving the UIH uEXPLORER total-body PET/CT scanner. Use whenever the user provides paper links/DOIs/PMIDs to add, asks to check or update "Just Accepted" entries, or wants to lint/clean uExplorer.bib and its controlled institution/keyword lists.
---

# uexplorer-bib

Manage `uExplorer.bib` (published at `https://mengxiangxi.info/uexplorer-bib/`) using the deterministic CLI toolkit `scripts/bib_tool.py` plus semantic curation for titles, scanner institutions, and keywords.

## CLI Toolkit (`scripts/bib_tool.py`)

Always run the Python CLI via `uv` first instead of scraping web pages manually:

```bash
TOOL="scripts/bib_tool.py"

# 1. Fetch metadata (Crossref + PubMed XML) from DOI, PMID, or URL (supports multiple targets)
#    `year` is the volume/issue year; `year_source` shows which field produced it
uv run --no-project python "$TOOL" fetch "<DOI_OR_PMID_OR_URL>"

# 2. Insert a new entry (at top of uExplorer.bib) or update an existing entry (matched by key/DOI/PMID)
#    Automatically normalizes aliases, strips volume/number/pages if Just Accepted, and syncs lists.md
uv run --no-project python "$TOOL" upsert \
  --key "author2026keyword" \
  --title "Sentence case title with <sup>18</sup>F tags" \
  --author "Last, First M and Last2, First2" \
  --journal "Full Journal Name" \
  --volume "X" \
  --number "Y" \
  --pages "123--456" \
  --year "2026" \
  --doi "10.xxxx/xxxxx" \
  --pmid "12345678" \
  --institution "Institution 1; Institution 2" \
  --keywords "keyword1; keyword2"

# 3. Batch-check all "Just Accepted" and missing-PMID entries in uExplorer.bib against Crossref & PubMed
uv run --no-project python "$TOOL" check-updates --apply

# 4. Validate (and optionally auto-fix) uExplorer.bib formatting, duplicates, and taxonomy rules
uv run --no-project python "$TOOL" lint --fix

# 5. Synchronize taxonomy.json and lists.md with uExplorer.bib
uv run --no-project python "$TOOL" sync-taxonomy

# 6. Assign a homonymous author occurrence (<citekey>#<1-based-pos>) to a disambiguated identity
uv run --no-project python "$TOOL" assign-homonym "Zheng2025AbbreviatedDynamic#4" "Liu, Hui (UIH)"
```

## Retrieval Hierarchy

0. **Level 0 — the user's already-open Chrome tab (MUST, when the user asks for it or states the page is open)**: When the user supplies a link together with wording such as “已在 chrome 中打开” / “the page is open”, start by inspecting the user's own Chrome: `tab list` → `tab select <id>` → `get url` / `get text --max all` / `eval`. Work in that tab in place:
   - NEVER open a second tab for the same URL, and NEVER re-navigate a tab the user already opened (institutional subscription state, session, scroll position, and figure viewers are lost on reload).
   - This in-place read is also the default for paywalled publishers (Wiley/Ovid/ACS): `curl` there returns a Cloudflare/interstitial stub, while the user's logged-in tab carries the full text.
   - Only if no matching tab exists, or the page is stale/unloaded, fall back to `tab new <url>` or `curl`.
   - Tab text is only as complete as the rendered page: sections behind tabs/accordions or in separate reference panes may be missing — say so instead of inventing content.

1. **Level 1 — `bib_tool.py fetch` (Primary)**: Queries Crossref + PubMed `efetch` XML in parallel to retrieve full author forenames, affiliations, DOI, PMID, volume/issue/pages, publication status, and initial institution/keyword matches.
2. **Level 2 — Literature MCPs (`pubmed-search` / `elsevier_mcp` / `wos-search`)**: Use if Level 1 lacks full author given names or affiliation strings (e.g., certain non-PubMed engineering papers).
3. **Level 3 — `@browsermcp` navigation (`tab new` / `goto`, Fallback only)**: Use **only** when publisher full-text (*Materials and Methods*) is needed to identify which hospital performed the uEXPLORER PET scan, or when the user provides a non-standard webpage link without a DOI/PMID — and then only after Level 0 found no matching open tab.

## Workflows

### Workflow A: Add New Article(s)
1. Run `bib_tool.py fetch <target>...` to get structured JSON and a draft BibTeX entry. If the user said the page is already open, first read that Chrome tab in place per Level 0 — do not open a new tab.
2. Verify and refine semantic fields:
   - **Citekey**: `<first_author_lastname><year><1-2_keywords>` (concise, e.g., `holman2026kinetics`).
   - **Language**: non-English publications keep **title, authors and journal in the original language** (`title={全身PET/CT动态显像评估<sup>18</sup>F-MK6240…}`, `author={吴世娜 and 张萌萌 and …}`, `journal={中华核医学与分子影像杂志}`) — never substitute the publisher's English translation. Chinese names are written in full, surname-first, without a comma; radionuclide tags still apply. Every Chinese author name MUST also be mapped to its English `Last, First` form in `taxonomy.json` (`author_aliases`, enforced by `lint` rule `unaliased_cjk_author`) so dropdowns and bibliometrics remain unified in English.
   - **Title**: Sentence case; preserve acronyms (`PET/CT`, `LAFOV`, `FAPI`, `PSMA`, `CT`, etc.) and wrap radionuclides/subscripts in HTML tags (`<sup>18</sup>F`, `<sup>68</sup>Ga`, `[<sup>68</sup>Ga]Ga-FAPI-04`).
   - **Authors**: Full given names required (`Last, First M and Last2, First2`); middle initials have no periods; never use `et al.` or `and others`. Cross-language aliases (e.g. `石洪成` → `Shi, Hongcheng`, `张晓军` → `Zhang, Xiaojun`) are resolved first via `author_aliases`, and then checked against `homonym_authors` (`citekey#pos`, e.g. `Zhang, Xiaojun (PLAGH)` vs `Zhang, Xiaojun (Nanfang)`). If `upsert` or `lint` reports `unaliased_cjk_author` or `unresolved_homonyms`, add the alias to `taxonomy.json` and/or check the author's affiliation in PubMed XML and bind `citekey#pos` via `bib_tool.py assign-homonym`.
   - **Journal**: Full journal name in Title Case, **except** `"Journal of Nuclear Medicine"` which MUST be abbreviated as `"J. Nucl. Med."` (prevents `bibtex-js` substring search collision). Use `\&` for ampersands (`Physics in Medicine \& Biology`).
   - **Status / Year**:
     - If online ahead of print / early access (or `pubmed_status == "aheadofprint"` / IEEE `volume == "PP"` / missing volume & pages): set `--year "Just Accepted"` and omit `volume`, `number`, `pages`.
     - If formally assigned to an issue: set `--year` to the **issue/volume publication year** (not online-first year) and include `volume`, `number`, `pages` (`--` for page ranges).
     - **Volume year is authoritative — never the online-first year.** `bib_tool.py fetch` already resolves this and reports it as `year_source`; the precedence is `crossref_journal_issue` (`journal-issue.published-print` → `journal-issue.published-online`) → `crossref_print` → `pubmed_journal_issue` → `pubmed_pubdate` → `crossref_online`. Only override by hand with publisher evidence, and record why.
       - Do not derive the year from the DOI suffix: Springer/Nature DOIs carry the *submission-tree* year (`10.1186/s13550-025-01332-5` → vol 16, 2026), and the same mismatch runs the other way on other publishers.
       - Crossref `issued` / `published-online` and PubMed `JournalIssue/PubDate` are online dates for many OA journals (PubMed copies the epub date into `PubDate`); both are last-resort fallbacks only.
       - Confirm against the publisher page when the two disagree: Springer exposes `citation_volume`, `citation_issue`, `citation_publication_date` (the issue date) next to `citation_online_date`.
       - The citekey year MUST equal the entry year (`liu2026girentuximab`, not `liu2025…`); `fetch`'s `citekey_suggestion` is built from the resolved year.
       - Worked example: online 2025-12-24, vol 16(1), article 1 → `year={2026}`. Repo precedent: `chen2026PDL1PET` (DOI `…jitc-2025-013837`) is `year={2026}`.
   - **Institution**: 1–3 succinct institutions separated by `; ` (semicolon + space):
     - **Hard constraint — author affiliates outrank scanner site**: every institution listed MUST appear in the paper's own author affiliation list. If the unit that operates the uEXPLORER scanner (or that supplied the imaging data, e.g. a shared challenge dataset) is not among the authors' affiliations, it MUST NOT be assigned. Record the provenance in the content analysis instead of the `institution` field. Concretely: Ruijin data reused by a Tübingen/Lübeck method paper stays out of `institution`.
     - **Membership test needs the publisher byline, not just Crossref**: Crossref often truncates an affiliation to its parent (`Shanghai Jiao Tong University School of Medicine` for `Department of Nuclear Medicine …, Ruijin Hospital, Shanghai Jiao Tong University School of Medicine`). Before concluding a unit is absent, read the publisher's own author list (IEEE *Authors* panel, ScienceDirect/ACS author popovers, `@browsermcp`, or the PDF) — a hospital hidden behind a parent university is still an author affiliation.
     - Include main authors' institutions (first/corresponding) AND, subject to the hard constraint above, the hospital operating the uEXPLORER scanner.
     - Omit parent university when an affiliated hospital is already listed (e.g., use `Zhongshan Hospital`, not `Zhongshan Hospital; Fudan University`).
     - Affiliations of international collaborating co-authors do NOT fill these slots: when the author list spans many countries, list only first/corresponding + scanner site (e.g., `Zhongshan Hospital` alone, not `Zhongshan Hospital; UC Davis; University of Bern`).
     - Consult `taxonomy.json` (`institution_aliases` and `institutions`). Notably: `"The First Affiliated Hospital of Shandong First Medical University"` $\rightarrow$ `"Qianfoshan Hospital"`.
   - **Keywords**: typically 1–4 keywords separated by `; ` from `taxonomy.json` (`keywords`). The count is **advisory, not a hard limit** — exceed 4 when each additional keyword carries a separate axis (tracer, disease, methodology, physiology, tracer-class) that a reader would filter on; do not pad with near-synonyms or with anything already implied by another keyword.
     - Include tracer (except FDG), disease, and methodology/specialty.
     - **Forbidden**: `PET`, `total body`, `total-body`, `uEXPLORER`, `FDG`, `18F-FDG`.
     - For new tracers, use EANM-recommended names, include tracer family (`FAPI`, `PSMA`, `DOTATATE`), and add `novel tracer` for uncommon tracers.
     - `dynamic acquisition` and `kinetics` are **mutually exclusive** (they partition the dynamic-PET literature; never assign both). The deprecated name `dynamic imaging` is aliased to `dynamic acquisition` in `keyword_aliases` and is rewritten by `lint --fix`.
       - `kinetics` — the paper reports *fitted* tracer-kinetic quantities (`K1`, `k2`, `k3`, `k4`, `Ki`, `VT`, `BP_ND`, `DVR`, `R1`, `vB`, perfusion from a model), selects/compares kinetic models (1TCM, 2TCM, 2T4k, SRTM, Patlak, Logan, AIC), estimates an input function/IDIF *for kinetic analysis*, or is a review of kinetic methodology. `Ki`/`BP` computed only as a benchmark still counts.
       - `dynamic acquisition` — the multi-frame acquisition itself is the object of study and no kinetic parameter is reported: frame/protocol design, optimal or dual-time-point timing, temporal resolution, frame prediction/interpolation, motion correction, direct dynamic reconstruction, descriptive time–activity/washout behaviour, dynamic feasibility at low dose.
       - Tie-break: if a fitted kinetic quantity is a reported result or the method's output, use `kinetics`; the acquisition-side contribution is then carried by `reconstruction`, `motion`, `fast`, `low dose`, `TAC denoising`, `parametric image`, or `input function`.
3. Run `bib_tool.py upsert ...` to write the entry to the top of `uExplorer.bib` and auto-sync `taxonomy.json` + `lists.md`.
4. Output the formatted BibTeX entry plus a **paper content analysis** per “Paper Content Analysis” below (never a one-line "main findings" restatement of the abstract conclusion).
5. Delete temporary files created while reading the full text (e.g., downloaded HTML/TXT dumps); they do not belong in the repo.

### Workflow B: Update "Just Accepted" or Missing-PMID Entries
1. **Batch mode** (checking the whole file or multiple entries): Run `bib_tool.py check-updates --apply`, then `bib_tool.py lint --fix`.
2. **Single-entry mode** (user provides a specific citekey or link):
   - Run `bib_tool.py fetch <DOI_or_PMID_or_URL>` to inspect current publication metadata.
   - If formally published (has volume and pages), run `bib_tool.py upsert --key <citekey> --year <issue_year> --volume <vol> --number <num> --pages <pages> --pmid <pmid>`.
3. Summarize which entries transitioned from `Just Accepted` to formal publication or gained PMIDs.

### Workflow C: Audit & Clean `uExplorer.bib`
1. Run `bib_tool.py lint --fix` to deduplicate entries, strip empty fields (`pmid={}`), normalize institution/keyword/journal aliases, and enforce BibTeX formatting invariants.
2. Run `bib_tool.py sync-taxonomy` to keep `taxonomy.json` and `lists.md` in sync with `uExplorer.bib`.

## Paper Content Analysis (Workflow A step 4)

Goal: the reader learns what was actually measured, on whom, with which numbers — not that the tracer "showed favorable properties".

**Evidence sourcing**
- `fetch` abstract is the minimum; when the paper is a PK/kinetics/technical study, also read the publisher full text — prefer the user's already-open Chrome tab (Level 0); otherwise PubMed `efetch` abstract text, then `tab new` in the browser, and only as a last resort `curl -sL -A "Mozilla/5.0" <url>` plus tag stripping (paywalled publishers block it).
- Every number must come from the abstract/full text; mark `[仅基于摘要]` when the full text was unavailable. Never infer missing values, `P` values, or model names.

**Required dimensions** (skip a dimension only if the paper genuinely lacks it; each with values ± SD and units):
1. **Question & design**: trial phase/registration, single- vs multi-center, screening→enrolment→dropout counts, N analysed, population (healthy volunteers vs patients), scanner and axial FOV.
2. **Tracer & protocol**: chemical identity/parent compound, radiosynthesis route and radiochemical purity, injected activity and injection site/duration, dynamic frame schedule, static time points, blood/urine sampling times, reconstruction (matrix, voxel size, algorithm, TOF/PSF).
3. **Systemic PK**: `Cmax`/`Tmax`, `CL`, `T1/2,b`, `MRT`, `Vd` for plasma and whole blood separately; note hematocrit/plasma-to-blood corrections.
4. **Image-derived vs sampled blood**: relative differences per sampling site (e.g. SVC/IVC/RA), Bland-Altman results, significance tests, and the physical reason for any systematic bias (temporal resolution, injection vs sampling vein).
5. **Organ-level PK / kinetics**: `Kp` (and exceptions such as spleen/brain), renal excretion fraction and `CLR`, compartment model chosen (1T2K vs 2TCM, AIC), fitted `K1`/`k2`/`k3`/`Ki` ranges, fit quality (`R²`).
6. **Significance**: link to prior work (theranostic use, BNCT, transporter specificity) and to the general method claim being validated (e.g. non-invasive PK from total-body PET).
7. **Limitations**: the authors' own limitations, enumerated compactly (dose range, extrapolated AUC fraction, sex imbalance, motion correction, model simplifications).

**Prohibitions**
- No qualitative-only summary ("rapid clearance, low affinity") without the supporting numbers.
- Do not present Discussion speculation as a measured result.
- Do not copy the abstract's wording; reorganize by dimension, in Chinese by default.
- Do not repeat the BibTeX fields as prose; the analysis adds content, not restatement.

## BibTeX Format Specification

No leading indentation, no tabs, no empty fields (`field={}`), no trailing comma on the last field:

```bibtex
@article{citekey,
title={Sentence case title with <sup>18</sup>F tags},
author={Last, First and Last2, First2 M},
journal={Full Journal Name},
volume={X},
number={Y},
pages={123--456},
year={2026},
doi={10.xxxx/xxxxx},
pmid={12345678},
institution={Institution 1; Institution 2},
keywords={keyword1; keyword2; keyword3}
}
```

## References

- Controlled vocabulary & alias rules: `taxonomy.json`
- Human-readable institution & keyword lists: `lists.md`
