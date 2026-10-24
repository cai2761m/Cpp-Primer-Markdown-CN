from pathlib import Path
import hashlib,json,re
from collections import Counter

ROOT=Path('D:/Obsidian/✨技术/计算机/C++/C++ Primer')
def digest(b):return hashlib.sha256(b).hexdigest()
report=json.loads((ROOT/'.marker/code-ocr-manifest.json').read_text(encoding='utf-8'))
split=json.loads((ROOT/'.marker/split-manifest.json').read_text(encoding='utf-8'))
backup=ROOT/report['backup']
source_path=ROOT/split['source'];raw=source_path.read_bytes();source=raw.decode('utf-8')
assert digest(raw)==report['source_after_sha256']==split['source_sha256']
old_raw=(backup/split['source']).read_bytes()
assert digest(old_raw)==report['source_before_sha256']
registry=report['images']
pattern=re.compile(r'!\[([^\]\r\n]*)\]\(((?:\.\./)?images/([^\)\r\n]+))\)')
def expected(old):
 def sub(m):
  x=registry.get(m[3])
  if not x:return m[0]
  before=x.get('prose_before','')
  after=x.get('prose_after','')
  body=x.get('markdown_body') or '```c++\n'+x['code']+'\n```'
  return (before+'\n\n' if before else '')+'<!-- 代码原图: '+m[2]+' -->\n'+body+('\n\n'+after if after else '')
 return pattern.sub(sub,old)
assert expected(old_raw.decode('utf-8').replace('\r\n','\n'))==source
for name,r in registry.items():assert digest((ROOT/'images'/name).read_bytes())==r['image_sha256'],name
old_split=json.loads((backup/'.marker/split-manifest.json').read_text(encoding='utf-8'))
old_rows={r['path']:r for r in old_split['files']}
pieces=[];links=0;comments=Counter();previous=0
for row in split['files']:
 path=ROOT/row['path'];raw=path.read_bytes();text=raw.decode('utf-8')
 assert digest(raw)==row['output_sha256'],row['path']
 old=(backup/row['path']).read_text(encoding='utf-8')
 assert expected(old)==text,row['path']
 assert text.split('\n\n',2)[:2]==old.split('\n\n',2)[:2],row['path']
 body=text.split('\n\n',2)[2]
 length=row['end']-row['offset']+3*row['relative_image_path_prefixes']
 payload=body[:length].replace('](../images/','](images/').replace('代码原图: ../images/','代码原图: images/')
 assert len(payload)==row['end']-row['offset'],row['path']
 assert digest(payload.encode())==row['source_sha256'],row['path']
 assert row['offset']==previous;previous=row['end'];pieces.append(payload)
 assert payload.count('<!-- 代码原图:')==row['ocr_code_images'],row['path']
 assert '\x00' not in text and '\ufffd' not in text,row['path']
 assert len(re.findall(r'^```',text,re.M))%2==0,row['path']
 comments.update(re.findall(r'<!-- 代码原图: ../images/([^\n]+) -->',text))
 for m in pattern.finditer(text):assert (path.parent/m[2]).exists(),m[2]
 for rel in re.findall(r'\]\(<([^>\n]+)>\)',text):
  if not re.match(r'\w+://',rel):assert (path.parent/rel.split('#')[0]).exists(),rel;links+=1
assert ''.join(pieces)==source
assert len(comments)==len(registry) and all(v==1 for v in comments.values())
assert len(pattern.findall(source))==report['remaining_image_references_in_full_book']
assert source.count('<!-- 代码原图:')==report['converted_code_images']
assert re.findall(r'<!-- PDF 第 \d+ 页 -->',source)==re.findall(r'<!-- PDF 第 \d+ 页 -->',old_raw.decode('utf-8'))
for p in [ROOT/'目录.md']:
 for rel in re.findall(r'\]\(<([^>\n]+)>\)',p.read_text(encoding='utf-8')):
  assert (p.parent/rel.split('#')[0]).exists(),rel;links+=1
result={'notes':len(pieces),'converted_code_images':len(registry),'code_block_insertions':report['code_block_insertions'],
        'remaining_images':len(pattern.findall(source)),'page_markers':len(re.findall(r'<!-- PDF 第 \d+ 页 -->',source)),
        'navigation_links':links,'full_book_matches_split_notes':True,'non_image_content_preserved':True,
        'image_assets_intact':True,'backups_verified':True,'fences_balanced':True}
(ROOT/'.marker/code-ocr-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
