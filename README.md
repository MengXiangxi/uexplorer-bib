# uEXPLORER Publication Bibliography (`uExplorer.bib`)

Manually maintained BibTeX database of peer-reviewed journal articles and conference proceedings involving the **United Imaging Healthcare uEXPLORER** total-body PET/CT scanner.

- **Webpage (interactive search & filter)**: <https://mengxiangxi.info/Link/uexplorer.html>
- **BibTeX file**: [`uExplorer.bib`](https://mengxiangxi.info/uexplorer-bib/uExplorer.bib)

## Local Preview

`preview.py` renders the live page against this checkout: it serves the GitHub Pages site
(`css/`, `javascript/`, `Link/uexplorer.html`) and mounts this repo at `/uexplorer-bib/`, so the
absolute paths used by the page resolve as in production.

```bash
uv run --no-project python preview.py                 # sibling checkout ..\MengXiangxi.github.io, port 8765, opens a tab
uv run --no-project python preview.py --site <path>   # explicit site checkout
uv run --no-project python preview.py --no-open       # serve only
```

Edit `uExplorer.bib`, reload, and the change shows up (`Cache-Control: no-store`).

## Entry Format

```bibtex
@article{citekey,
title={Sentence case title with <sup>18</sup>F tags},
author={Last, First and Last2, First2 M},
journal={Full Journal Name},
volume={X},
number={Y},
pages={123--456},
year={2024},
doi={10.xxxx/xxxxx},
pmid={12345678},
institution={Institution Name},
keywords={keyword1; keyword2; keyword3}
}
```
