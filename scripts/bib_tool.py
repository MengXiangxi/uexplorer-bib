#!/usr/bin/env python3
"""Deterministic bibliography toolkit for uExplorer.bib.

Subcommands:
  fetch <target>...          Fetch metadata (DOI/PMID/URL) from Crossref + PubMed and draft BibTeX
  check-updates [--apply]    Batch-check 'Just Accepted' and missing-PMID entries in uExplorer.bib
  lint [--fix]               Validate (and optionally fix) uExplorer.bib against schema and taxonomy
  sync-taxonomy              Synchronize taxonomy.json and lists.md with uExplorer.bib
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_BIB = ROOT_DIR / "uExplorer.bib"
TAXONOMY_PATH = ROOT_DIR / "taxonomy.json"
LISTS_MD_PATH = ROOT_DIR / "lists.md"

USER_AGENT = "uexplorer-bib-tool/2.0 (https://mengxiangxi.info; mailto:mengxiangxi@pku.edu.cn)"

FIELD_ORDER_PUBLISHED = [
    "title",
    "author",
    "journal",
    "volume",
    "number",
    "pages",
    "year",
    "doi",
    "pmid",
    "url",
    "institution",
    "keywords",
]

FIELD_ORDER_JUST_ACCEPTED = [
    "title",
    "author",
    "journal",
    "year",
    "doi",
    "pmid",
    "url",
    "institution",
    "keywords",
]

PRESERVE_CASE_ACRONYMS = {
    "PET", "CT", "PET/CT", "PET/MR", "MRI", "MR", "LAFOV", "SAFOV", "TOF", "DPR", "DLR",
    "FDG", "FAPI", "PSMA", "DOTATATE", "DOTATOC", "SUV", "Ki", "Patlak", "Logan", "EANM",
    "SNMMI", "EARL", "NEMA", "UIH", "uEXPLORER", "EXPLORER", "Mini", "II", "III", "IV",
    "DNA", "RNA", "mRNA", "CD147", "CD70", "CD8", "HER2", "PD-L1", "PD-1", "CAIX", "Trop2",
    "TSPO", "CXCR4", "NTSR1", "GZP", "mFBG", "CFT", "AraG", "BCH", "NOTA", "DOTA", "RESCA",
    "AlF", "BMI", "COVID-19", "ICU", "AI", "3D", "2D", "4D", "CNN", "GAN", "Transformer",
    "U-Net", "nnU-Net", "Monte", "Carlo", "Gate", "GATE", "OS-EM", "OSEM", "MLEM", "FWHM",
    "NECR", "SNR", "PSNR", "SSIM", "TAC", "IDIF", "AIF", "PBPK", "PRLT", "ccRCC", "NSCLC",
    "NPC", "HCC", "PCa", "AD", "PD", "PSP", "NMDAR",
}

ISOTOPE_PATTERN = re.compile(
    r"(?<!sup>)\b(18F|68Ga|64Cu|89Zr|11C|13N|15O|124I|131I|177Lu|90Y|225Ac|99mTc|44Sc|186Re|188Re|211At)\b"
)


def load_taxonomy() -> dict[str, Any]:
    if TAXONOMY_PATH.exists():
        return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    return {
        "institutions": [],
        "institution_aliases": {},
        "keywords": [],
        "keyword_aliases": {},
        "forbidden_keywords": [],
        "journal_aliases": {},
    }


def parse_bibtex(text: str) -> list[dict[str, Any]]:
    """Balanced-brace BibTeX parser preserving entry order and exact field values."""
    entries: list[dict[str, Any]] = []
    pos = 0
    n = len(text)
    while True:
        at = text.find("@", pos)
        if at == -1:
            break
        bopen = text.find("{", at)
        if bopen == -1:
            break
        etype = text[at + 1 : bopen].strip().lower()
        comma = text.find(",", bopen)
        if comma == -1:
            break
        key = text[bopen + 1 : comma].strip()
        depth = 1
        i = comma + 1
        while i < n and depth > 0:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body = text[comma + 1 : i - 1]
        fields: dict[str, str] = {}
        fi = 0
        bn = len(body)
        while fi < bn:
            m = re.search(r"([A-Za-z0-9_-]+)\s*=\s*\{", body[fi:])
            if not m:
                break
            fname = m.group(1).lower()
            vstart = fi + m.end()
            fdepth = 1
            vi = vstart
            while vi < bn and fdepth > 0:
                if body[vi] == "{":
                    fdepth += 1
                elif body[vi] == "}":
                    fdepth -= 1
                vi += 1
            fields[fname] = body[vstart : vi - 1].strip()
            fi = vi
        entries.append(
            {
                "type": etype,
                "key": key,
                "fields": fields,
                "raw": text[at:i],
            }
        )
        pos = i
    return entries


def format_entry(entry: dict[str, Any]) -> str:
    """Serialize a BibTeX entry according to uExplorer.bib formatting rules."""
    etype = entry.get("type", "article").lower()
    key = entry["key"]
    fields = entry["fields"]
    is_just_accepted = fields.get("year") == "Just Accepted"
    base_order = FIELD_ORDER_JUST_ACCEPTED if is_just_accepted else FIELD_ORDER_PUBLISHED

    ordered_keys = [k for k in base_order if k in fields and fields[k] != ""]
    for k in fields:
        if k not in ordered_keys and fields[k] != "":
            if is_just_accepted and k in ("volume", "number", "pages"):
                continue
            ordered_keys.append(k)

    lines = [f"@{etype}{{{key},"]
    for idx, k in enumerate(ordered_keys):
        comma = "," if idx < len(ordered_keys) - 1 else ""
        lines.append(f"{k}={{{fields[k]}}}{comma}")
    lines.append("}")
    return "\n".join(lines)


def format_isotope_tags(title: str) -> str:
    """Convert plain radionuclide tokens like 18F or [18F] into <sup>18</sup>F in titles."""
    def repl(match: re.Match[str]) -> str:
        token = match.group(1)
        m = re.match(r"^(\d+m?)([A-Za-z]+)$", token)
        if not m:
            return token
        return f"<sup>{m.group(1)}</sup>{m.group(2)}"

    return ISOTOPE_PATTERN.sub(repl, title)


def to_sentence_case_title(raw_title: str) -> str:
    """Convert title to sentence case while preserving HTML tags, acronyms, and colon capitals."""
    title = html.unescape(raw_title).strip().rstrip(".")
    title = re.sub(r"\s+", " ", title)
    title = format_isotope_tags(title)

    # Split preserving tags
    tokens = re.split(r"(\s+)", title)
    result: list[str] = []
    capitalize_next = True

    for tok in tokens:
        if not tok or tok.isspace():
            result.append(tok)
            continue

        # Strip punctuation around core word to check acronym table
        core = re.sub(r"^[^A-Za-z0-9<]+|[^A-Za-z0-9>]+$", "", tok)
        plain_core = re.sub(r"<[^>]+>", "", core)

        if (
            plain_core in PRESERVE_CASE_ACRONYMS
            or re.search(r"<sup>|<sub>", tok)
            or (len(plain_core) >= 2 and plain_core.isupper())
            or re.search(r"[0-9]", plain_core)
            or any(sub in PRESERVE_CASE_ACRONYMS for sub in plain_core.split("-"))
        ):
            out_tok = tok
        elif capitalize_next:
            out_tok = tok[0].upper() + tok[1:].lower() if len(tok) > 1 else tok.upper()
        else:
            out_tok = tok.lower()

        result.append(out_tok)
        capitalize_next = tok.endswith(":") or tok.endswith("?") or tok.endswith("!")

    return "".join(result)


def normalize_pages(pages: str | None) -> str:
    if not pages:
        return ""
    pages = pages.strip().replace("–", "-").replace("—", "-")
    if "-" in pages and "--" not in pages:
        parts = pages.split("-")
        if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
            start, end = parts[0].strip(), parts[1].strip()
            if len(end) < len(start):
                end = start[: len(start) - len(end)] + end
            return f"{start}--{end}"
        return pages.replace("-", "--", 1)
    return pages


def http_get_json(url: str, timeout: int = 12) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get_xml(url: str, timeout: int = 15) -> ET.Element:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return ET.fromstring(resp.read())


def parse_target_identifier(target: str) -> dict[str, str]:
    target = target.strip()
    # Direct PMID URL or numeric PMID
    m_pubmed = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", target)
    if m_pubmed:
        return {"pmid": m_pubmed.group(1)}
    if re.fullmatch(r"\d{7,9}", target):
        return {"pmid": target}

    # DOI in string or URL
    unquoted = urllib.parse.unquote(target)
    m_doi = re.search(r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)", unquoted)
    if m_doi:
        doi = m_doi.group(1).rstrip(".,;/)>")
        return {"doi": doi}

    return {"url": target}


def fetch_pubmed_by_pmid(pmid: str) -> dict[str, Any]:
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={pmid}&retmode=xml"
    root = http_get_xml(url)
    art = root.find(".//PubmedArticle")
    if art is None:
        return {}
    return parse_pubmed_article_xml(art)


def parse_pubmed_article_xml(art: ET.Element) -> dict[str, Any]:
    pmid = art.findtext(".//MedlineCitation/PMID") or ""
    status = art.findtext(".//PubmedData/PublicationStatus") or ""

    # Reconstruct title with inner XML tags (<sup>, <sub>, <i>)
    title_el = art.find(".//Article/ArticleTitle")
    raw_title = ""
    if title_el is not None:
        raw_title = "".join(ET.tostring(e, encoding="unicode") for e in title_el)
        if title_el.text:
            raw_title = title_el.text + raw_title
        # Clean non-sup/sub tags
        raw_title = re.sub(r"</?(?!sup\b|sub\b)[a-zA-Z0-9]+[^>]*>", "", raw_title)

    journal = art.findtext(".//Article/Journal/Title") or art.findtext(".//Article/Journal/ISOAbbreviation") or ""
    journal = re.sub(r"\s*\([^)]*\)\s*$", "", journal).strip()
    volume = (art.findtext(".//Article/Journal/JournalIssue/Volume") or "").strip()
    issue = (art.findtext(".//Article/Journal/JournalIssue/Issue") or "").strip()
    pages = (
        art.findtext(".//Article/Pagination/MedlinePgn")
        or art.findtext(".//Article/ELocationID[@EIdType='pii']")
        or ""
    ).strip()
    year = (
        art.findtext(".//Article/Journal/JournalIssue/PubDate/Year")
        or (art.findtext(".//Article/Journal/JournalIssue/PubDate/MedlineDate") or "")[:4]
    ).strip()

    doi = ""
    for aid in art.findall(".//PubmedData/ArticleIdList/ArticleId[@IdType='doi']"):
        if aid.text:
            doi = aid.text.strip()
            break
    if not doi:
        for eloc in art.findall(".//Article/ELocationID[@EIdType='doi']"):
            if eloc.text:
                doi = eloc.text.strip()
                break

    authors: list[str] = []
    affiliations: list[str] = []
    for au in art.findall(".//Article/AuthorList/Author"):
        last = (au.findtext("LastName") or "").strip()
        fore = (au.findtext("ForeName") or "").strip()
        if last and fore:
            # Remove periods from middle initials
            fore_clean = re.sub(r"\.", "", fore)
            authors.append(f"{last}, {fore_clean}")
        elif last:
            authors.append(last)
        for aff in au.findall(".//AffiliationInfo/Affiliation"):
            if aff.text and aff.text.strip() not in affiliations:
                affiliations.append(aff.text.strip())

    abstract_parts = [ab.text.strip() for ab in art.findall(".//Article/Abstract/AbstractText") if ab.text]
    keywords = [kw.text.strip() for kw in art.findall(".//MedlineCitation/KeywordList/Keyword") if kw.text]

    return {
        "pmid": pmid,
        "doi": doi,
        "status": status,
        "title": raw_title,
        "authors": authors,
        "journal": journal,
        "volume": "" if volume == "PP" else volume,
        "number": issue,
        "pages": normalize_pages(pages),
        "year": year,
        "affiliations": affiliations,
        "author_keywords": keywords,
        "abstract": " ".join(abstract_parts),
    }


def fetch_crossref_by_doi(doi: str) -> dict[str, Any]:
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"
    data = http_get_json(url)
    msg = data.get("message", {})

    titles = msg.get("title", [])
    raw_title = titles[0] if titles else ""
    containers = msg.get("container-title", [])
    journal = html.unescape(containers[0]) if containers else ""

    authors: list[str] = []
    affiliations: list[str] = []
    for au in msg.get("author", []):
        family = (au.get("family") or "").strip()
        given = re.sub(r"\.", "", (au.get("given") or "").strip())
        if family and given:
            authors.append(f"{family}, {given}")
        elif family:
            authors.append(family)
        for aff in au.get("affiliation", []):
            name = (aff.get("name") or "").strip()
            if name and name not in affiliations:
                affiliations.append(name)

    vol = (msg.get("volume") or "").strip()
    iss = (msg.get("issue") or "").strip()
    pages = normalize_pages(msg.get("page") or msg.get("article-number") or "")
    pub_print = msg.get("published-print", {}).get("date-parts", [[None]])[0][0]
    pub_online = msg.get("published-online", {}).get("date-parts", [[None]])[0][0]
    year = str(pub_print or pub_online or "")

    return {
        "doi": msg.get("DOI") or doi,
        "title": raw_title,
        "authors": authors,
        "journal": journal,
        "volume": vol,
        "number": iss,
        "pages": pages,
        "year": year,
        "year_print": str(pub_print) if pub_print else "",
        "year_online": str(pub_online) if pub_online else "",
        "affiliations": affiliations,
    }


def match_institutions_from_affiliations(affiliations: list[str], taxonomy: dict[str, Any]) -> list[str]:
    matched: list[str] = []
    aliases = taxonomy.get("institution_aliases", {})
    canonical = taxonomy.get("institutions", [])

    joined = " | ".join(affiliations)
    # 1. Check explicit aliases first (longest match first)
    for alias, target in sorted(aliases.items(), key=lambda x: -len(x[0])):
        if alias.lower() in joined.lower() and target not in matched:
            matched.append(target)

    # 2. Check canonical institutions
    for inst in sorted(canonical, key=lambda x: -len(x)):
        if inst.lower() in joined.lower() and inst not in matched:
            matched.append(inst)

    return matched[:3]


def suggest_keywords(text_blob: str, taxonomy: dict[str, Any]) -> list[str]:
    blob_lower = text_blob.lower()
    matched: list[str] = []
    for kw in taxonomy.get("keywords", []):
        if kw in taxonomy.get("forbidden_keywords", []):
            continue
        if len(kw) <= 3:
            if re.search(rf"\b{re.escape(kw)}\b", text_blob):
                matched.append(kw)
        elif kw.lower() in blob_lower:
            matched.append(kw)
    return matched[:6]


def fetch_single_target(target: str, taxonomy: dict[str, Any]) -> dict[str, Any]:
    parsed = parse_target_identifier(target)
    doi = parsed.get("doi", "")
    pmid = parsed.get("pmid", "")

    pm_data: dict[str, Any] = {}
    cr_data: dict[str, Any] = {}

    if pmid:
        try:
            pm_data = fetch_pubmed_by_pmid(pmid)
            doi = doi or pm_data.get("doi", "")
        except Exception as exc:
            pm_data = {"error": str(exc)}

    if doi and not pmid:
        try:
            es_url = (
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
                f"?db=pubmed&term={urllib.parse.quote(doi)}[LID]&retmode=json"
            )
            es = http_get_json(es_url)
            idlist = es.get("esearchresult", {}).get("idlist", [])
            if idlist:
                pmid = idlist[0]
                pm_data = fetch_pubmed_by_pmid(pmid)
        except Exception:
            pass

    if doi:
        try:
            cr_data = fetch_crossref_by_doi(doi)
        except Exception as exc:
            cr_data = {"error": str(exc)}

    raw_title = pm_data.get("title") or cr_data.get("title") or ""
    title = to_sentence_case_title(raw_title) if raw_title else ""

    # Prefer author list with full given names (longer average length)
    pm_authors = pm_data.get("authors", [])
    cr_authors = cr_data.get("authors", [])
    authors = pm_authors if sum(len(a) for a in pm_authors) >= sum(len(a) for a in cr_authors) else cr_authors

    raw_journal = cr_data.get("journal") or pm_data.get("journal") or ""
    journal = taxonomy.get("journal_aliases", {}).get(raw_journal, raw_journal)

    volume = cr_data.get("volume") or pm_data.get("volume") or ""
    number = cr_data.get("number") or pm_data.get("number") or ""
    pages = cr_data.get("pages") or pm_data.get("pages") or ""

    pm_status = pm_data.get("status", "")
    is_just_accepted = (pm_status == "aheadofprint" and not (volume and pages)) or not (volume and pages)
    year = "Just Accepted" if is_just_accepted else (cr_data.get("year_print") or pm_data.get("year") or cr_data.get("year") or "")

    affiliations = pm_data.get("affiliations") or cr_data.get("affiliations") or []
    matched_inst = match_institutions_from_affiliations(affiliations, taxonomy)

    blob = " ".join([raw_title, pm_data.get("abstract", ""), " ".join(pm_data.get("author_keywords", []))])
    suggested_kw = suggest_keywords(blob, taxonomy)

    first_last = authors[0].split(",")[0].lower() if authors else "author"
    first_last = re.sub(r"[^a-z]", "", first_last)
    key_year = (cr_data.get("year") or pm_data.get("year") or "2026")[:4]
    words = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", re.sub(r"<[^>]+>", "", title)) if w.lower() not in {"with", "from", "using", "total", "body", "study", "imaging", "patients", "based"}]
    citekey = f"{first_last}{key_year}{''.join(w.capitalize() for w in words[:2])}"

    draft_fields: dict[str, str] = {
        "title": title,
        "author": " and ".join(authors),
        "journal": journal,
    }
    if not is_just_accepted:
        if volume:
            draft_fields["volume"] = volume
        if number:
            draft_fields["number"] = number
        if pages:
            draft_fields["pages"] = pages
    draft_fields["year"] = year
    if doi:
        draft_fields["doi"] = doi
    if pmid:
        draft_fields["pmid"] = pmid
    draft_fields["institution"] = "; ".join(matched_inst) if matched_inst else "TODO_INSTITUTION"
    draft_fields["keywords"] = "; ".join(suggested_kw) if suggested_kw else "TODO_KEYWORDS"

    bibtex_draft = format_entry({"type": "article", "key": citekey, "fields": draft_fields})

    return {
        "input": target,
        "doi": doi,
        "pmid": pmid,
        "is_just_accepted": is_just_accepted,
        "pubmed_status": pm_status,
        "title": title,
        "authors": authors,
        "journal": journal,
        "volume": volume,
        "number": number,
        "pages": pages,
        "year": year,
        "raw_affiliations": affiliations,
        "matched_institutions": matched_inst,
        "suggested_keywords": suggested_kw,
        "citekey_suggestion": citekey,
        "bibtex_draft": bibtex_draft,
    }


def cmd_fetch(args: argparse.Namespace) -> int:
    taxonomy = load_taxonomy()
    results = [fetch_single_target(t, taxonomy) for t in args.targets]
    print(json.dumps(results if len(results) > 1 else results[0], indent=2, ensure_ascii=False))
    return 0


def cmd_check_updates(args: argparse.Namespace) -> int:
    bib_path = Path(args.bib)
    entries = parse_bibtex(bib_path.read_text(encoding="utf-8"))

    # 1. Batch resolve missing PMIDs via PubMed esearch + efetch
    missing_pmid = [e for e in entries if not e["fields"].get("pmid", "").strip() and e["fields"].get("doi", "").strip()]
    doi_to_pmid: dict[str, str] = {}
    for i in range(0, len(missing_pmid), 15):
        chunk = missing_pmid[i : i + 15]
        terms = " OR ".join(f'"{e["fields"]["doi"].strip()}"[LID]' for e in chunk)
        try:
            es_url = (
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
                f"?db=pubmed&term={urllib.parse.quote(terms)}&retmax=50&retmode=json"
            )
            idlist = http_get_json(es_url).get("esearchresult", {}).get("idlist", [])
            if idlist:
                ef_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={','.join(idlist)}&retmode=xml"
                rxml = http_get_xml(ef_url)
                for art in rxml.findall(".//PubmedArticle"):
                    pm = art.findtext(".//MedlineCitation/PMID") or ""
                    for aid in art.findall(".//PubmedData/ArticleIdList/ArticleId[@IdType='doi']"):
                        if aid.text and pm:
                            doi_to_pmid[aid.text.strip().lower()] = pm
        except Exception as exc:
            print(f"[warn] batch PMID lookup chunk failed: {exc}", file=sys.stderr)

    # 2. Check all Just Accepted entries via PubMed efetch + Crossref
    just_accepted = [e for e in entries if e["fields"].get("year") == "Just Accepted"]
    ja_pmids = [
        e["fields"].get("pmid", "").strip() or doi_to_pmid.get(e["fields"].get("doi", "").strip().lower(), "")
        for e in just_accepted
    ]
    ja_pmids_clean = [p for p in ja_pmids if p]
    pm_by_id: dict[str, dict[str, Any]] = {}
    if ja_pmids_clean:
        try:
            ef_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={','.join(ja_pmids_clean)}&retmode=xml"
            rxml = http_get_xml(ef_url)
            for art in rxml.findall(".//PubmedArticle"):
                parsed_art = parse_pubmed_article_xml(art)
                if parsed_art.get("pmid"):
                    pm_by_id[parsed_art["pmid"]] = parsed_art
        except Exception as exc:
            print(f"[warn] PubMed efetch failed: {exc}", file=sys.stderr)

    def fetch_cr_safe(e: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        doi = e["fields"].get("doi", "").strip()
        if not doi:
            return e["key"], {}
        try:
            return e["key"], fetch_crossref_by_doi(doi)
        except Exception:
            return e["key"], {}

    with ThreadPoolExecutor(max_workers=8) as pool:
        cr_by_key = dict(pool.map(fetch_cr_safe, just_accepted))

    updates: list[dict[str, Any]] = []
    for e in entries:
        f = e["fields"]
        key = e["key"]
        doi_lower = f.get("doi", "").strip().lower()
        changes: dict[str, str] = {}

        # Fill newly discovered PMID
        if not f.get("pmid", "").strip() and doi_lower in doi_to_pmid:
            changes["pmid"] = doi_to_pmid[doi_lower]
            f["pmid"] = doi_to_pmid[doi_lower]

        # Check Just Accepted -> formally published
        if f.get("year") == "Just Accepted":
            pm = pm_by_id.get(f.get("pmid", "").strip(), {})
            cr = cr_by_key.get(key, {})
            vol = cr.get("volume") or pm.get("volume") or ""
            num = cr.get("number") or pm.get("number") or ""
            pages = cr.get("pages") or pm.get("pages") or ""
            yr = cr.get("year_print") or pm.get("year") or cr.get("year") or ""
            pm_status = pm.get("status", "")

            if vol and pages and vol != "PP" and pm_status != "aheadofprint" and yr:
                changes["year"] = yr
                changes["volume"] = vol
                if num:
                    changes["number"] = num
                changes["pages"] = pages

                f["year"] = yr
                f["volume"] = vol
                if num:
                    f["number"] = num
                f["pages"] = pages

        if changes:
            updates.append({"key": key, "doi": f.get("doi", ""), "changes": changes})

    if args.apply and updates:
        out_text = "\n\n".join(format_entry(e) for e in entries) + "\n"
        bib_path.write_text(out_text, encoding="utf-8")

    print(
        json.dumps(
            {
                "checked_just_accepted": len(just_accepted),
                "checked_missing_pmid": len(missing_pmid),
                "updates_found": len(updates),
                "applied": bool(args.apply and updates),
                "updates": updates,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    bib_path = Path(args.bib)
    taxonomy = load_taxonomy()
    inst_aliases = taxonomy.get("institution_aliases", {})
    kw_aliases = taxonomy.get("keyword_aliases", {})
    forbidden_kw = set(taxonomy.get("forbidden_keywords", []))
    journal_aliases = taxonomy.get("journal_aliases", {})

    entries = parse_bibtex(bib_path.read_text(encoding="utf-8"))
    issues: list[dict[str, str]] = []

    seen_keys: set[str] = set()
    seen_dois: dict[str, str] = {}
    seen_pmids: dict[str, str] = {}
    deduped_entries: list[dict[str, Any]] = []

    for e in entries:
        key = e["key"]
        f = e["fields"]

        # 1. Duplicate key / DOI check
        doi = f.get("doi", "").strip().lower()
        if key in seen_keys:
            issues.append({"key": key, "type": "duplicate_key", "detail": f"Duplicate citekey {key}"})
            if args.fix:
                continue
        seen_keys.add(key)

        if doi and doi in seen_dois:
            issues.append(
                {
                    "key": key,
                    "type": "duplicate_doi",
                    "detail": f"Duplicate DOI {doi} (already in {seen_dois[doi]})",
                }
            )
            if args.fix:
                continue
        if doi:
            seen_dois[doi] = key

        # 2. Empty fields
        empty_keys = [k for k, v in list(f.items()) if not v.strip()]
        for ek in empty_keys:
            issues.append({"key": key, "type": "empty_field", "detail": f"Empty field {ek}={{}}"})
            if args.fix:
                del f[ek]

        # 3. Duplicate PMID check
        pmid = f.get("pmid", "").strip()
        if pmid and pmid in seen_pmids:
            issues.append(
                {
                    "key": key,
                    "type": "duplicate_pmid",
                    "detail": f"Duplicate PMID {pmid} (also in {seen_pmids[pmid]})",
                }
            )
        if pmid:
            seen_pmids[pmid] = key

        # 4. Just Accepted constraints
        if f.get("year") == "Just Accepted":
            for bad_f in ("volume", "number", "pages"):
                if bad_f in f:
                    issues.append(
                        {
                            "key": key,
                            "type": "just_accepted_has_vol",
                            "detail": f"Just Accepted entry has {bad_f}={f[bad_f]}",
                        }
                    )
                    if args.fix:
                        del f[bad_f]
        elif "JustAccepted" in key and f.get("year", "").isdigit():
            new_key = key.replace("JustAccepted", f["year"])
            issues.append(
                {
                    "key": key,
                    "type": "stale_just_accepted_key",
                    "detail": f"Citekey contains JustAccepted but year is {f['year']} -> {new_key}",
                }
            )
            if args.fix:
                e["key"] = new_key
                key = new_key

        # 5. Journal alias normalization
        jrnl = f.get("journal", "").strip()
        if jrnl in journal_aliases:
            target_jrnl = journal_aliases[jrnl]
            issues.append(
                {
                    "key": key,
                    "type": "journal_alias",
                    "detail": f"Journal '{jrnl}' -> '{target_jrnl}'",
                }
            )
            if args.fix:
                f["journal"] = target_jrnl

        # 6. Institution normalization
        raw_inst = f.get("institution", "")
        if "Guangdong People's Hospital, SIAT, CAS" in raw_inst:
            issues.append(
                {
                    "key": key,
                    "type": "institution_separator",
                    "detail": "Comma used instead of semicolon in 'Guangdong People's Hospital, SIAT, CAS'",
                }
            )
            if args.fix:
                raw_inst = raw_inst.replace(
                    "Guangdong People's Hospital, SIAT, CAS", "Guangdong People's Hospital; SIAT, CAS"
                )
        inst_items = [x.strip() for x in raw_inst.split(";") if x.strip()]
        norm_inst: list[str] = []
        for item in inst_items:
            mapped = inst_aliases.get(item, item)
            if mapped != item:
                issues.append(
                    {
                        "key": key,
                        "type": "institution_alias",
                        "detail": f"Institution '{item}' -> '{mapped}'",
                    }
                )
            val_to_add = mapped if args.fix else item
            if val_to_add not in norm_inst:
                norm_inst.append(val_to_add)
        if args.fix and norm_inst:
            f["institution"] = "; ".join(norm_inst)

        # 7. Keywords normalization
        raw_kw = f.get("keywords", "")
        kw_items = [x.strip() for x in raw_kw.split(";") if x.strip()]
        norm_kw: list[str] = []
        for item in kw_items:
            if item in forbidden_kw:
                issues.append(
                    {
                        "key": key,
                        "type": "forbidden_keyword",
                        "detail": f"Forbidden keyword '{item}'",
                    }
                )
                if args.fix:
                    continue
            mapped = kw_aliases.get(item, item)
            if mapped != item:
                issues.append(
                    {
                        "key": key,
                        "type": "keyword_alias",
                        "detail": f"Keyword '{item}' -> '{mapped}'",
                    }
                )
            val_to_add = mapped if args.fix else item
            if val_to_add not in norm_kw:
                norm_kw.append(val_to_add)
        if args.fix and norm_kw:
            f["keywords"] = "; ".join(norm_kw)

        # 8. Trailing comma in raw entry
        if re.search(r",\s*\}\s*$", e["raw"]):
            issues.append({"key": key, "type": "trailing_comma", "detail": "Trailing comma before closing brace"})

        deduped_entries.append(e)

    if args.fix:
        out_text = "\n\n".join(format_entry(e) for e in deduped_entries) + "\n"
        bib_path.write_text(out_text, encoding="utf-8")

    print(
        json.dumps(
            {
                "total_entries": len(deduped_entries) if args.fix else len(entries),
                "issue_count": len(issues),
                "fixed": bool(args.fix),
                "issues": issues,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if (not issues or args.fix) else 1


def cmd_sync_taxonomy(args: argparse.Namespace) -> int:
    bib_path = Path(args.bib)
    taxonomy = load_taxonomy()
    entries = parse_bibtex(bib_path.read_text(encoding="utf-8"))

    inst_aliases = taxonomy.get("institution_aliases", {})
    kw_aliases = taxonomy.get("keyword_aliases", {})
    forbidden_kw = set(taxonomy.get("forbidden_keywords", []))

    inst_set = set(taxonomy.get("institutions", []))
    kw_set = set(taxonomy.get("keywords", []))

    # Remove any alias keys or forbidden items from canonical sets
    inst_set -= set(inst_aliases.keys())
    kw_set -= set(kw_aliases.keys()) | forbidden_kw

    for e in entries:
        for i in e["fields"].get("institution", "").split(";"):
            i = i.strip()
            if i:
                inst_set.add(inst_aliases.get(i, i))
        for k in e["fields"].get("keywords", "").split(";"):
            k = k.strip()
            if k and k not in forbidden_kw:
                kw_set.add(kw_aliases.get(k, k))

    taxonomy["institutions"] = sorted(inst_set)
    taxonomy["keywords"] = sorted(kw_set)

    TAXONOMY_PATH.write_text(json.dumps(taxonomy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Regenerate human-readable lists.md
    repl_lines = [f'- "{k}" → "{v}"' for k, v in sorted(inst_aliases.items())]
    lists_md = (
        "# Lists\n\n"
        "*(Auto-synchronized from `taxonomy.json` and `uExplorer.bib` via `scripts/bib_tool.py sync-taxonomy`)*\n\n"
        "## Institutions\n\n"
        + "; ".join(taxonomy["institutions"])
        + "\n\n## Institution Replacements\n\n"
        + "\n".join(repl_lines)
        + "\n\n## Keywords\n\n"
        + "; ".join(taxonomy["keywords"])
        + "\n"
    )
    LISTS_MD_PATH.write_text(lists_md, encoding="utf-8")

    print(
        json.dumps(
            {
                "institutions_count": len(taxonomy["institutions"]),
                "keywords_count": len(taxonomy["keywords"]),
                "taxonomy_path": str(TAXONOMY_PATH.relative_to(ROOT_DIR)),
                "lists_md_path": str(LISTS_MD_PATH.relative_to(ROOT_DIR)),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0

def cmd_upsert(args: argparse.Namespace) -> int:
    bib_path = Path(args.bib)
    taxonomy = load_taxonomy()
    inst_aliases = taxonomy.get("institution_aliases", {})
    kw_aliases = taxonomy.get("keyword_aliases", {})
    forbidden_kw = set(taxonomy.get("forbidden_keywords", []))
    journal_aliases = taxonomy.get("journal_aliases", {})

    entries = parse_bibtex(bib_path.read_text(encoding="utf-8"))

    # Locate existing entry by key, DOI, or PMID
    target_entry: dict[str, Any] | None = None
    for e in entries:
        f = e["fields"]
        if (
            (args.key and e["key"] == args.key)
            or (args.doi and f.get("doi", "").strip().lower() == args.doi.strip().lower())
            or (args.pmid and f.get("pmid", "").strip() == args.pmid.strip())
        ):
            target_entry = e
            break

    is_new = target_entry is None
    if target_entry is None:
        if not args.key:
            raise SystemExit("Error: --key is required when inserting a new entry")
        target_entry = {"type": "article", "key": args.key.strip(), "fields": {}}

    if args.key:
        target_entry["key"] = args.key.strip()

    f = target_entry["fields"]
    for field_name in ("title", "author", "journal", "volume", "number", "pages", "year", "doi", "pmid", "url", "institution", "keywords"):
        val = getattr(args, field_name, None)
        if val is not None:
            f[field_name] = val.strip()

    if f.get("journal") in journal_aliases:
        f["journal"] = journal_aliases[f["journal"]]
    if "pages" in f:
        f["pages"] = normalize_pages(f["pages"])
    if f.get("year") == "Just Accepted":
        for k in ("volume", "number", "pages"):
            f.pop(k, None)

    if "institution" in f:
        inst_list: list[str] = []
        for x in f["institution"].split(";"):
            x = x.strip()
            if x:
                mapped = inst_aliases.get(x, x)
                if mapped not in inst_list:
                    inst_list.append(mapped)
        f["institution"] = "; ".join(inst_list)

    if "keywords" in f:
        kw_list: list[str] = []
        for x in f["keywords"].split(";"):
            x = x.strip()
            if x and x not in forbidden_kw:
                mapped = kw_aliases.get(x, x)
                if mapped not in kw_list:
                    kw_list.append(mapped)
        f["keywords"] = "; ".join(kw_list)

    # Remove empty values
    for k in [k for k, v in f.items() if not v]:
        del f[k]

    if is_new:
        entries.insert(0, target_entry)

    out_text = "\n\n".join(format_entry(e) for e in entries) + "\n"
    bib_path.write_text(out_text, encoding="utf-8")

    # Keep taxonomy synchronized
    cmd_sync_taxonomy(args)
    print(json.dumps({"action": "inserted" if is_new else "updated", "entry": format_entry(target_entry)}, indent=2, ensure_ascii=False))
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    import http.server
    import webbrowser

    bib_dir = ROOT_DIR.resolve()

    class StandaloneHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *h_args: Any, **h_kwargs: Any) -> None:
            super().__init__(*h_args, directory=str(bib_dir), **h_kwargs)

        extensions_map = {
            **http.server.SimpleHTTPRequestHandler.extensions_map,
            ".html": "text/html; charset=utf-8",
            ".htm": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".bib": "text/plain; charset=utf-8",
            ".json": "application/json; charset=utf-8",
        }

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            super().end_headers()

    url = f"http://{args.host}:{args.port}/"
    print(f"Serving local preview at {url}")
    print(f"  Root : {bib_dir}")
    if args.open:
        webbrowser.open(url)
    with http.server.ThreadingHTTPServer((args.host, args.port), StandaloneHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="uExplorer.bib toolkit")
    parser.add_argument("--bib", default=str(DEFAULT_BIB), help="Path to uExplorer.bib")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch", help="Fetch metadata from DOI/PMID/URL and draft BibTeX")
    p_fetch.add_argument("targets", nargs="+", help="One or more DOIs, PMIDs, or URLs")
    p_fetch.set_defaults(func=cmd_fetch)

    p_upd = sub.add_parser("check-updates", help="Batch-check Just Accepted and missing-PMID entries")
    p_upd.add_argument("--apply", action="store_true", help="Apply discovered updates to uExplorer.bib")
    p_upd.set_defaults(func=cmd_check_updates)

    p_lint = sub.add_parser("lint", help="Validate and optionally fix uExplorer.bib")
    p_lint.add_argument("--fix", action="store_true", help="Automatically fix lint issues in uExplorer.bib")
    p_lint.set_defaults(func=cmd_lint)

    p_sync = sub.add_parser("sync-taxonomy", help="Sync taxonomy.json and lists.md with uExplorer.bib")
    p_sync.set_defaults(func=cmd_sync_taxonomy)

    p_ups = sub.add_parser("upsert", help="Insert a new entry at top of uExplorer.bib or update matching entry")
    p_ups.add_argument("--key", help="Citekey")
    p_ups.add_argument("--title", help="Sentence-case title with <sup>/<sub> tags")
    p_ups.add_argument("--author", help="BibTeX author string (Last, First and Last2, First2)")
    p_ups.add_argument("--journal", help="Full journal name (or J. Nucl. Med.)")
    p_ups.add_argument("--volume", help="Volume")
    p_ups.add_argument("--number", help="Issue number")
    p_ups.add_argument("--pages", help="Page range (123--456) or article number")
    p_ups.add_argument("--year", help="4-digit publication year or 'Just Accepted'")
    p_ups.add_argument("--doi", help="DOI")
    p_ups.add_argument("--pmid", help="PubMed ID")
    p_ups.add_argument("--url", help="URL (only if no DOI)")
    p_ups.add_argument("--institution", help="Semicolon-separated institutions")
    p_ups.add_argument("--keywords", help="Semicolon-separated keywords")
    p_ups.set_defaults(func=cmd_upsert)

    p_prev = sub.add_parser("preview", help="Start standalone local HTTP preview server")
    p_prev.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    p_prev.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    p_prev.add_argument("--open", action="store_true", help="Open browser automatically")
    p_prev.set_defaults(func=cmd_preview)

    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
