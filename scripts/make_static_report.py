import base64, pathlib, json

def enc(p):
    p = pathlib.Path(p)
    if not p.exists(): return ""
    return base64.b64encode(p.read_bytes()).decode()

cov = enc("reports/artifacts/coverage.png")
pth = enc("reports/artifacts/paths.png")
crs = enc("reports/artifacts/crashes.png")
tri = []
tfile = pathlib.Path("reports/triage.json")
if tfile.exists():
    tri = json.loads(tfile.read_text())

html = f"""<!doctype html><meta charset="utf-8">
<style>body{{font-family:sans-serif;max-width:960px;margin:2rem auto;}} img{{max-width:100%;}} table{{border-collapse:collapse;width:100%;}} td,th{{border:1px solid #ddd;padding:6px;}}</style>
<h1>RAG-Guided Greybox Fuzzing (EoH-Only)</h1>
<h2>Summary</h2>
<ul>
  <li>Unique crash clusters: {len(tri)}</li>
</ul>
<h2>Coverage</h2>{('<img src="data:image/png;base64,'+cov+'"/>') if cov else '<p>(no coverage plot)</p>'}
<h2>Paths</h2>{('<img src="data:image/png;base64,'+pth+'"/>') if pth else '<p>(no paths plot)</p>'}
<h2>Crashes</h2>{('<img src="data:image/png;base64,'+crs+'"/>') if crs else '<p>(no crashes plot)</p>'}
<h2>Triage (top)</h2>
<table><tr><th>hash</th><th>count</th><th>samples</th></tr>
{"".join(f"<tr><td>{t['hash']}</td><td>{t['count']}</td><td>{'<br>'.join(t['samples'][:2])}</td></tr>" for t in tri[:10])}
</table>
"""
pathlib.Path("reports/index.html").write_text(html, encoding="utf-8")
print("Wrote reports/index.html")
