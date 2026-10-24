from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import argparse,base64,hashlib,io,json,re,time,urllib.request
from PIL import Image

ROOT=Path('D:/Obsidian/✨技术/计算机/C++/C++ Primer')
WORK=Path('D:/DevCache/marker/code-ocr')
RESULTS=WORK/'glm-results';RESULTS.mkdir(parents=True,exist_ok=True)
PATTERN=re.compile(r'!\[[^\]\r\n]*\]\(images/([^\)\r\n]+)\)')


def classify(raw):
    fences=re.findall(r'```[^\n]*\n(.*?)```',raw,re.S)
    if fences:
        return {'kind':'code','code':'\n\n'.join(fences).strip('\n'),'classification':'fenced'}
    text=raw.strip()
    if re.fullmatch(r'(?:NOTE|WARNING|TIP|Note|Warning|Tip|Best\s+Practices|C\+\+\s*11)',text,re.I):
        return {'kind':'image','text':text,'classification':'icon'}
    if re.search(r'(?:^|\n)\s*[图表]\s*\d+[.．]',text) or re.search(r'[→←↑↓↔]',text):
        return {'kind':'image','text':text,'classification':'figure_caption_or_arrow'}
    if re.search(r'<(?:table|img)\b',text,re.I) or re.search(r'^\s*\|.*\|.*\|',text,re.M):
        return {'kind':'image','text':text,'classification':'table_or_figure'}
    syntax=bool(re.search(r'#\s*(?:include|define|if|endif)|::|//|/\\?\*|;|\{|\}|\b(?:return|typedef|template|namespace|class|struct|cout|cin)\b',text))
    if syntax:
        return {'kind':'code','code':text,'classification':'syntax'}
    non_comments=re.sub(r'//[^\n]*|/\\?\*.*?\\?\*/','',text,flags=re.S)
    non_strings=re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'','',non_comments)
    if not re.search(r'[\u3400-\u9fff]',non_strings):
        weak=re.search(r'\b(?:int|double|float|while|for|if|else|sizeof|const|bool|void|new|delete|string|vector|auto|unsigned|long|short|char|decltype|nullptr|true|false|extern)\b|\w+\s*[（(]|\+\+|--|<=|>=|==|!=|\+=|-=|\*=|/=|\w\s*=\s*\w|^[\s$]*g\+\+\b|^[A-Z]:\\',text)
        literal=re.search(r'"[^\n]*"|\'[^\n]*\'|\b\d+(?:\.\d*)?[eE][-+]?\d+',text)
        if weak or literal:
            return {'kind':'code','code':text,'classification':'expression_or_literal'}
    return {'kind':'other_text' if text else 'image','text':text,'classification':'other'}


def read(name,force=False):
    target=RESULTS/(name+'.json')
    image_path=ROOT/'images'/name
    image_bytes=image_path.read_bytes();digest=hashlib.sha256(image_bytes).hexdigest()
    if target.exists() and not force:
        previous=json.loads(target.read_text(encoding='utf-8'))
        if previous.get('image_sha256')==digest and not previous.get('error'):return previous
    with Image.open(image_path) as image:size=image.size
    url='data:image/png;base64,'+base64.b64encode(image_bytes).decode()
    payload={'model':'glm-ocr','messages':[{'role':'user','content':[
      {'type':'image_url','image_url':{'url':url}},{'type':'text','text':'Text Recognition:'}]}],
      'temperature':0,'max_tokens':4096,'cache_prompt':False,'logprobs':True,'top_logprobs':1}
    then=time.monotonic();record=None
    for attempt in range(3):
        try:
            if attempt:payload['temperature']=(0,.1,.3)[attempt];payload['seed']=42+attempt
            request=urllib.request.Request('http://127.0.0.1:8317/v1/chat/completions',json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=240) as response:result=json.load(response)
            choice=result['choices'][0]; raw=choice['message'].get('content') or ''
            record={'name':name,'image_sha256':digest,'size':list(size),'raw':raw,
                    'finish_reason':choice.get('finish_reason'),'tokens':result.get('usage',{}).get('completion_tokens'),
                    'seconds':round(time.monotonic()-then,2),'attempt':attempt,
                    'error':choice.get('finish_reason')=='length',**classify(raw)}
            lp=choice.get('logprobs') or {}; content=lp.get('content') or []
            record['low_probability_tokens']=[{'token':t.get('token'),'logprob':t['logprob']} for t in content if t.get('logprob',0)<-2]
            if not record['error']:
                target.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');return record
        except Exception as e:record={'name':name,'image_sha256':digest,'error':True,'exception':repr(e)}
    target.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');return record


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sample',action='store_true');parser.add_argument('--workers',type=int,default=8);parser.add_argument('--force',action='store_true');parser.add_argument('--names')
    args=parser.parse_args()
    names=list(dict.fromkeys(PATTERN.findall((ROOT/'C++ Primer（第5版）.md').read_text(encoding='utf-8'))))
    names=[n for n in names if 18<=int(re.search(r'_page_(\d+)_',n)[1])<1274]
    if args.sample:names=['_page_20_Picture_136.png','_page_25_Picture_104.png','_page_40_Picture_92.png','_page_46_Picture_141.png','_page_26_Picture_135.png','_page_600_Diagram_2.png','_page_999_Picture_100.png']
    if args.names:names=args.names.split(',')
    then=time.monotonic();records=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(read,name,args.force):name for name in names}
        for i,future in enumerate(as_completed(futures),1):
            record=future.result();records.append(record)
            if args.sample:print(json.dumps(record,ensure_ascii=False),flush=True)
            elif i%40==0 or i==len(names):
                progress={'processed':i,'total':len(names),'errors':sum(bool(r.get('error')) for r in records),
                          **{k:sum(r.get('kind')==k for r in records) for k in ('code','image','other_text')},
                          'seconds':round(time.monotonic()-then)}
                (WORK/'glm-progress.json').write_text(json.dumps(progress,indent=2),encoding='utf-8');print(json.dumps(progress),flush=True)

if __name__=='__main__':main()
