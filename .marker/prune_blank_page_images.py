"""Keep page markers, but omit white detector crops on genuinely empty PDF pages."""
from pathlib import Path
import json
import re
from PIL import Image

work=Path('D:/DevCache/marker/cpp-primer-final')
source=json.loads(Path('D:/DevCache/marker/qa/source-audit.json').read_text(encoding='utf-8'))
removed=[]
for file in sorted(work.glob('pages-*.md')):
    meta_path=file.with_suffix('.json')
    meta=json.loads(meta_path.read_text(encoding='utf-8'))
    audit={r['page_id']:r for r in meta['image_audit']}
    text=file.read_text(encoding='utf-8')
    def replace(match):
        ref=match[1]
        found=re.search(r'_page_(\d+)_',ref)
        if not found:
            return match[0]
        page_id=int(found[1])
        if source['pages'][page_id]['text_chars'] or audit[page_id]['embedded_images']:
            return match[0]
        with Image.open(work/ref) as image:
            extrema=image.convert('RGB').getextrema()
        if not all(ext==(255,255) for ext in extrema):
            return match[0]
        removed.append({'page_id':page_id,'image':ref,'reason':'No source text or embedded images; rendered crop is pure white.'})
        return ''
    changed=re.sub(r'!\[[^\]]*\]\(([^)]+)\)',replace,text)
    if changed!=text:
        file.write_text(changed,encoding='utf-8')
        meta['output_images']=[Path(ref).name for ref in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',changed)]
        meta_path.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
(work/'blank-page-images.json').write_text(json.dumps(removed,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'omitted_blank_images':len(removed),'page_markers_preserved':True}))
