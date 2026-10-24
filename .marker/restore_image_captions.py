"""Retain text carried inside Marker image blocks as searchable Markdown alt text."""
from pathlib import Path
import json
import re

from convert_cpp_primer import ImagePreservingConverter, IMAGE_TYPES
from marker.models import create_model_dict, shutdown_models

work = Path('D:/DevCache/marker/cpp-primer-final')
audit = json.loads((work/'validation.json').read_text(encoding='utf-8'))
source = json.loads(Path('D:/DevCache/marker/qa/source-audit.json').read_text(encoding='utf-8'))
pages = [r['page_id'] for r in audit['page_stats'] if r['missing_han']]
caption_file = work/'image-alt-text.json'
captions = json.loads(caption_file.read_text(encoding='utf-8')) if caption_file.exists() else {}
models = create_model_dict()
try:
    for start in range(0,len(pages),24):
        config = {'mode':'fast','disable_ocr':True,'page_range':pages[start:start+24],
                  'pdftext_workers':1,'disable_tqdm':True,'highres_image_dpi':240,
                  'keep_pageheader_in_output':True,'keep_pagefooter_in_output':True,
                  'common_element_threshold':2.0,'max_streak':100000,
                  'filter_blank_pages':False}
        converter = ImagePreservingConverter(artifact_dict=models,config=config)
        document = converter.build_document(source['source'])
        for page in document.pages:
            for block in page.contained_blocks(document,IMAGE_TYPES):
                text = ' '.join(block.raw_text(document).split())
                if text:
                    text = re.sub(r'(?<=[\u3400-\u9fff]) +(?=[\u3400-\u9fff])','',text)
                    captions[f'{block.id.to_path()}.png'] = text
finally:
    shutdown_models(models)

count = 0
for file in sorted(work.glob('pages-*.md')):
    text = file.read_text(encoding='utf-8')
    added = {}
    def replace(match):
        name = match[1]
        if name not in captions:
            return match[0]
        caption = captions[name]
        escaped = caption.replace('\\','\\\\').replace('[','&#91;').replace(']','&#93;')
        added[name] = caption
        return f'![{escaped}](images/{name})'
    replaced = re.sub(r'!\[\]\(images/([^)]+)\)',replace,text)
    if replaced != text:
        file.write_text(replaced,encoding='utf-8')
        meta_path = file.with_suffix('.json')
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        meta.setdefault('image_alt_text',{}).update(added)
        meta_path.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        count += len(added)
(work/'image-alt-text.json').write_text(json.dumps(captions,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'pages_reviewed':len(pages),'image_captions_restored':count},ensure_ascii=False))
