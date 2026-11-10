---
name: uexplorer-bib
description: Add, update ("Just Accepted" to formally published), or audit BibTeX citation entries in uExplorer.bib for academic papers involving the UIH uEXPLORER total-body PET/CT scanner. Use whenever the user provides paper links/DOIs/PMIDs to add, asks to check or update "Just Accepted" entries, or wants to lint/clean uExplorer.bib and its controlled institution/keyword lists.
---

# uexplorer-bib

Manage `uExplorer.bib` (consumed by `bibtex-js` on `https://mengxiangxi.info/Link/uexplorer.html`) using the deterministic CLI toolkit `.claude/skills/uexplorer-bib/scripts/bib_tool.py` plus semantic curation for titles, scanner institutions, and keywords.

## CLI Toolkit (`scripts/bib_tool.py`)

Always run the Python CLI via `uv` first instead of scraping web pages manually:

```bash
TOOL=".claude/skills/uexplorer-bib/scripts/bib_tool.py"

# 1. Fetch metadata (Crossref + PubMed XML) from DOI, PMID, or URL (supports multiple targets)
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

# 5. Synchronize references/taxonomy.json and references/lists.md with uExplorer.bib
uv run --no-project python "$TOOL" sync-taxonomy
```

## Retrieval Hierarchy

1. **Level 1 — `bib_tool.py fetch` (Primary)**: Queries Crossref + PubMed `efetch` XML in parallel to retrieve full author forenames, affiliations, DOI, PMID, volume/issue/pages, publication status, and initial institution/keyword matches.
2. **Level 2 — Literature MCPs (`pubmed-search` / `elsevier_mcp` / `wos-search`)**: Use if Level 1 lacks full author given names or affiliation strings (e.g., certain non-PubMed engineering papers).
3. **Level 3 — `@browsermcp` (Fallback only)**: Use **only** when publisher full-text (*Materials and Methods*) is needed to identify which hospital performed the uEXPLORER PET scan, or when the user provides a non-standard webpage link without a DOI/PMID.

## Workflows

### Workflow A: Add New Article(s)
1. Run `bib_tool.py fetch <target>...` to get structured JSON and a draft BibTeX entry.
2. Verify and refine semantic fields:
   - **Citekey**: `<first_author_lastname><year><1-2_keywords>` (concise, e.g., `holman2026kinetics`).
   - **Title**: Sentence case; preserve acronyms (`PET/CT`, `LAFOV`, `FAPI`, `PSMA`, `CT`, etc.) and wrap radionuclides/subscripts in HTML tags (`<sup>18</sup>F`, `<sup>68</sup>Ga`, `[<sup>68</sup>Ga]Ga-FAPI-04`).
   - **Authors**: Full given names required (`Last, First M and Last2, First2`); middle initials have no periods; never use `et al.` or `and others`.
   - **Journal**: Full journal name in Title Case, **except** `"Journal of Nuclear Medicine"` which MUST be abbreviated as `"J. Nucl. Med."` (prevents `bibtex-js` substring search collision). Use `\&` for ampersands (`Physics in Medicine \& Biology`).
   - **Status / Year**:
     - If online ahead of print / early access (or `pubmed_status == "aheadofprint"` / IEEE `volume == "PP"` / missing volume & pages): set `--year "Just Accepted"` and omit `volume`, `number`, `pages`.
     - If formally assigned to an issue: set `--year` to the **issue/volume publication year** (not online-first year) and include `volume`, `number`, `pages` (`--` for page ranges).
   - **Institution**: 1–3 succinct institutions separated by `; ` (semicolon + space):
     - Include main authors' institutions (first/corresponding) AND the hospital operating the uEXPLORER scanner.
     - Omit parent university when an affiliated hospital is already listed (e.g., use `Zhongshan Hospital`, not `Zhongshan Hospital; Fudan University`).
     - Consult `references/taxonomy.json` (`institution_aliases` and `institutions`). Notably: `"The First Affiliated Hospital of Shandong First Medical University"` $\rightarrow$ `"Qianfoshan Hospital"`.
   - **Keywords**: 1–4 keywords separated by `; ` from `references/taxonomy.json` (`keywords`):
     - Include tracer (except FDG), disease, and methodology/specialty.
     - **Forbidden**: `PET`, `total body`, `total-body`, `uEXPLORER`, `FDG`, `18F-FDG`.
     - For new tracers, use EANM-recommended names, include tracer family (`FAPI`, `PSMA`, `DOTATATE`), and add `novel tracer` for uncommon tracers.
3. Run `bib_tool.py upsert ...` to write the entry to the top of `uExplorer.bib` and auto-sync `references/taxonomy.json` + `references/lists.md`.
4. Output the formatted BibTeX entry and a concise summary of the paper's main findings.

### Workflow B: Update "Just Accepted" or Missing-PMID Entries
1. **Batch mode** (checking the whole file or multiple entries): Run `bib_tool.py check-updates --apply`, then `bib_tool.py lint --fix`.
2. **Single-entry mode** (user provides a specific citekey or link):
   - Run `bib_tool.py fetch <DOI_or_PMID_or_URL>` to inspect current publication metadata.
   - If formally published (has volume and pages), run `bib_tool.py upsert --key <citekey> --year <issue_year> --volume <vol> --number <num> --pages <pages> --pmid <pmid>`.
3. Summarize which entries transitioned from `Just Accepted` to formal publication or gained PMIDs.

### Workflow C: Audit & Clean `uExplorer.bib`
1. Run `bib_tool.py lint --fix` to deduplicate entries, strip empty fields (`pmid={}`), normalize institution/keyword/journal aliases, and enforce `bibtex-js` formatting invariants.
2. Run `bib_tool.py sync-taxonomy` to keep `references/taxonomy.json` and `references/lists.md` in sync with `uExplorer.bib`.

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

- Controlled vocabulary & alias rules: `references/taxonomy.json`
- Human-readable institution & keyword lists: `references/lists.md`
