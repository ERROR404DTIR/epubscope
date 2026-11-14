#!/usr/bin/env python3
"""EPUBScope — inspect and audit EPUB 2/3 books. Python 3.9+, stdlib only."""
import argparse, csv, json, re, sys, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
DC = "{http://purl.org/dc/elements/1.1/}"
CONT = "{urn:oasis:names:tc:opendocument:xmlns:container}"
OPF = "{http://www.idpf.org/2007/opf}"
def inspect(path):
    p=Path(path); result={"file":str(p),"size":p.stat().st_size,"valid":False,"warnings":[]}
    try:
        with zipfile.ZipFile(p) as z:
            names=set(z.namelist())
            if "mimetype" not in names: result["warnings"].append("Missing mimetype entry")
            else:
                if z.read("mimetype").decode("ascii","replace").strip()!="application/epub+zip": result["warnings"].append("Unexpected mimetype value")
                if z.namelist()[0]!="mimetype": result["warnings"].append("mimetype is not the first ZIP entry")
            if "META-INF/container.xml" not in names: raise ValueError("Missing META-INF/container.xml")
            root=ET.fromstring(z.read("META-INF/container.xml"))
            node=root.find(".//"+CONT+"rootfile")
            if node is None or not node.get("full-path"): raise ValueError("No package document path in container.xml")
            opf_path=node.get("full-path")
            if opf_path not in names: raise ValueError("Package document not found: "+opf_path)
            opf=ET.fromstring(z.read(opf_path))
            md=opf.find(OPF+"metadata")
            if md is None: raise ValueError("Package metadata is missing")
            def values(tag):
                return [x.text.strip() for x in md.findall(DC+tag) if x.text and x.text.strip()]
            manifest=opf.find(OPF+"manifest"); spine=opf.find(OPF+"spine")
            items=manifest.findall(OPF+"item") if manifest is not None else []
            result.update({"valid":True,"package":opf_path,"title":(values("title") or [""])[0],"authors":values("creator"),"language":(values("language") or [""])[0],"identifier":(values("identifier") or [""])[0],"publisher":(values("publisher") or [""])[0],"date":(values("date") or [""])[0],"subjects":values("subject"),"manifest_items":len(items),"spine_items":len(spine.findall(OPF+"itemref")) if spine is not None else 0,"format":"EPUB"})
            ids={x.get("id") for x in items}
            if spine is None: result["warnings"].append("Reading order (spine) is missing")
            elif any(x.get("idref") not in ids for x in spine.findall(OPF+"itemref")): result["warnings"].append("Spine references an unknown manifest item")
            if not result["title"]: result["warnings"].append("Book title is missing")
            if not result["language"]: result["warnings"].append("Language is missing")
            if not any(x.get("properties","").split().__contains__("nav") for x in items) and not any(x.get("media-type")=="application/x-dtbncx+xml" for x in items): result["warnings"].append("No EPUB navigation document found")
    except (zipfile.BadZipFile, ET.ParseError, OSError, KeyError, ValueError) as e:
        result["error"]=str(e)
    return result
def main():
    ap=argparse.ArgumentParser(description="Audit EPUB files and build a local book catalog")
    sub=ap.add_subparsers(dest="cmd",required=True)
    s=sub.add_parser("scan",help="scan a folder recursively"); s.add_argument("path"); s.add_argument("--json"); s.add_argument("--csv")
    i=sub.add_parser("inspect",help="inspect one EPUB file"); i.add_argument("file")
    a=ap.parse_args()
    if a.cmd=="inspect":
        r=inspect(a.file); print(json.dumps(r,indent=2,ensure_ascii=False)); return 0 if r["valid"] else 1
    root=Path(a.path); books=[]
    candidates=[root] if root.is_file() else sorted(root.rglob("*.epub")) if root.is_dir() else []
    if not candidates: print("No EPUB files found (or path does not exist).",file=sys.stderr); return 2
    for f in candidates:
        if f.suffix.lower()==".epub":
            r=inspect(f); books.append(r)
            mark="OK" if r["valid"] and not r["warnings"] else "CHECK"
            print(f"[{mark}] {f} — {r.get('title') or r.get('error','untitled')}")
            for w in r["warnings"]: print("   !",w)
    seen={}
    for b in books:
        key=re.sub(r"\s+"," ",b.get("title","").strip().casefold())
        if key: seen.setdefault(key,[]).append(b["file"])
    for group in seen.values():
        if len(group)>1: print("DUPLICATE TITLE:", " | ".join(group))
    if a.json: Path(a.json).write_text(json.dumps(books,indent=2,ensure_ascii=False),encoding="utf-8")
    if a.csv:
        fields=["file","valid","title","authors","language","identifier","publisher","date","manifest_items","spine_items","warnings","error"]
        with open(a.csv,"w",newline="",encoding="utf-8-sig") as f:
            w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
            for b in books: w.writerow({k:"; ".join(b[k]) if isinstance(b.get(k),list) else b.get(k,"") for k in fields})
    good=sum(x["valid"] for x in books); print(f"\nScanned {len(books)} EPUB(s): {good} valid, {len(books)-good} invalid.")
    return 0 if good==len(books) else 1
if __name__=="__main__": sys.exit(main())