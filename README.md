# uEXPLORER Publication Bibliography (`uExplorer.bib`)

[![Lint Bibliography](https://github.com/MengXiangxi/uexplorer-bib/actions/workflows/lint.yml/badge.svg)](https://github.com/MengXiangxi/uexplorer-bib/actions/workflows/lint.yml)

Standalone open-source database and interactive web application tracking peer-reviewed journal articles and conference proceedings involving the **United Imaging Healthcare uEXPLORER** total-body PET/CT scanner.

- **Interactive Webpage**: <https://mengxiangxi.info/uexplorer-bib/>
- **Conference Archive (2017–2022)**: <https://mengxiangxi.info/uexplorer-bib/conference.html>
- **Raw BibTeX**: [`uExplorer.bib`](https://mengxiangxi.info/uexplorer-bib/uExplorer.bib)
- **Controlled Vocabulary**: [`taxonomy.json`](./taxonomy.json) · [`lists.md`](./lists.md)

## Repository Structure

```text
uexplorer-bib/
├── uExplorer.bib           # Curated BibTeX database
├── taxonomy.json           # Controlled vocabulary & alias mappings (institutions, keywords, journals)
├── lists.md                # Human-readable list of canonical institutions and tags
├── index.html              # Interactive search & filter web application
├── conference.html         # Historical conference abstract archive (2017–2022)
├── assets/
│   ├── style.css           # Standalone stylesheet
│   ├── app.js              # Zero-dependency BibTeX parser & interactive filter UI
│   └── conference/         # Archived conference figures
├── scripts/
│   └── bib_tool.py         # CLI toolkit (fetch, upsert, check-updates, lint, sync-taxonomy)
└── preview.py              # Standalone local HTTP preview server
```

## Local Preview

No external repository or third-party Python package is required:

```bash
uv run --no-project python preview.py             # Serves http://127.0.0.1:8765/ and opens a tab
uv run --no-project python preview.py --no-open   # Serve only
```

## CLI Toolkit (`scripts/bib_tool.py`)

```bash
# 1. Fetch metadata from Crossref + PubMed by DOI, PMID, or URL
uv run --no-project python scripts/bib_tool.py fetch "<DOI_OR_PMID_OR_URL>"

# 2. Insert a new entry or update an existing entry (auto-normalizes & syncs taxonomy)
uv run --no-project python scripts/bib_tool.py upsert \
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

# 3. Check "Just Accepted" and missing-PMID entries against Crossref & PubMed
uv run --no-project python scripts/bib_tool.py check-updates --apply

# 4. Validate and auto-fix formatting, duplicates, and taxonomy rules
uv run --no-project python scripts/bib_tool.py lint --fix

# 5. Synchronize taxonomy.json and lists.md with uExplorer.bib
uv run --no-project python scripts/bib_tool.py sync-taxonomy
```

## Entry Format

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
