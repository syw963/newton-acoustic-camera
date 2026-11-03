import sys, asyncio, json
from pathlib import Path
HERE = Path(__file__).resolve().parent
OUT = HERE.parent.parent / '문서'
sys.path.insert(0, str(HERE))
from items import ITEMS
import content as C
from playwright.async_api import async_playwright

COST = {2, 3, 45}  # 배송비·관세 행 (물품 아님)
by = {i[0]: i for i in ITEMS}
goods = [i for i in ITEMS if i[0] not in COST]

GROUPS = [
 ('음향카메라 본체', [1, 22, 34], '소리를 녹음하고 방향을 계산하는 측정 장치와 노트북 연결'),
 ('자동 회전판', [4,5,6,7,8,9,10,11,12,13,26,27,35,41], '배열을 정해진 각도만큼 돌려 실험의 기준 각도를 만드는 장치'),
 ('실험용 음원', [14,15,16,17,18,19], '위치를 알고 있는 소리를 내는 스피커 2개와 구동 회로'),
 ('측정·보정', [20,21], '음원까지의 거리와 기온(음속 보정) 측정'),
 ('목공 공구', [23,24,25,36,37,38,39,40], '회전판 제작. 이후 동아리 공용 공구로 사용'),
 ('납땜·전기 공구', [28,29,30,31,32,33,42,43,44], '음원 회로와 배선 제작. 이후 동아리 공용 공구로 사용'),
]

def names(nums):
    return ', '.join(by[n][1] for n in nums)

group_rows = ''.join(
    f'<tr><td class="g">{g}</td><td class="c">{len(ns)}</td><td>{d}</td></tr>' for g, ns, d in GROUPS)

mark = lambda v: '●' if v else ''
item_rows = ''.join(
    f'<tr><td class="c">{n}</td><td class="nm">{nm}</td>'
    f'<td class="c m">{mark(a)}</td><td class="c m">{mark(b)}</td><td class="c m">{mark(c)}</td><td class="c m">{mark(d)}</td>'
    f'<td>{u}</td></tr>' for n, nm, p, a, b, c, d, u in goods)

svg = '''
<svg viewBox="0 0 560 210" class="fig" style="max-height:60mm" role="img" aria-label="실험 배치 평면도">
  <defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#3b4a5a"/></marker></defs>
  <rect x="40" y="70" width="90" height="70" rx="6" fill="#eef2f6" stroke="#3b4a5a"/>
  <text x="85" y="92" class="t c">자동 회전판</text>
  <rect x="62" y="100" width="46" height="8" fill="#1f4e79"/>
  <text x="85" y="134" class="s c">UMA-16 + 카메라</text>
  <path d="M142 132 A 34 34 0 0 0 142 78" fill="none" stroke="#c0392b" stroke-width="1.5" marker-start="url(#ar)" marker-end="url(#ar)"/>
  <text x="150" y="150" class="s" fill="#c0392b">회전 −60° ~ +60°</text>
  <line x1="130" y1="105" x2="397" y2="105" stroke="#3b4a5a" stroke-dasharray="4 4"/>
  <text x="265" y="120" class="s c">1.5 m (0°)</text>
  <line x1="130" y1="105" x2="392" y2="41" stroke="#3b4a5a" stroke-dasharray="4 4"/>
  <circle cx="410" cy="105" r="13" fill="#fff" stroke="#3b4a5a"/><text x="410" y="109" class="t c">A</text>
  <circle cx="405" cy="38" r="13" fill="#fff" stroke="#3b4a5a"/><text x="405" y="42" class="t c">B</text>
  <text x="440" y="109" class="s">스피커 A (삼각대)</text>
  <text x="430" y="42" class="s">스피커 B (실험 2)</text>
  <text x="300" y="90" class="s c">두 음원 사이 각도 Δθ</text>
  <rect x="190" y="160" width="130" height="38" rx="5" fill="#fff" stroke="#3b4a5a"/>
  <text x="255" y="176" class="s c">노트북 · USB 허브</text>
  <text x="255" y="191" class="s c">아두이노 · 앰프(L→A, R→B)</text>
  <line x1="130" y1="135" x2="190" y2="175" stroke="#7f8c8d"/>
  <line x1="320" y1="175" x2="400" y2="118" stroke="#7f8c8d"/>
</svg>'''

def paras(ps):
    return ''.join(f'<p>{p}</p>' for p in ps)

def lis(xs):
    return ''.join(f'<li>{x}</li>' for x in xs)

def uses(nums, label='사용 물품'):
    return f'<p class="uses"><span>{label}</span> {names(nums)}</p>'

html = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<style>
@page {{ size: A4; margin: 16mm 16mm 15mm 16mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family: 'Noto Sans CJK KR',sans-serif; font-size: 9.8pt; line-height: 1.6; color:#000; margin:0; }}
h1 {{ font-size: 16pt; margin: 0 0 1.5mm; font-weight:700; }}
.sub {{ font-size:9.3pt; margin-bottom:5mm; color:#333; }}
h2 {{ font-size: 11.5pt; margin: 5.5mm 0 1.8mm; padding-bottom:0.8mm; border-bottom: 0.8px solid #000; font-weight:700; }}
h3 {{ font-size: 10pt; margin: 3mm 0 1mm; font-weight:700; }}
p {{ margin: 1mm 0 1.6mm; text-align: justify; }}
ol, ul {{ margin: 1mm 0 2mm; padding-left: 5.5mm; }}
li {{ margin: 0.5mm 0; text-align: justify; }}
.q {{ margin: 1.5mm 0 2mm; padding-left: 5.5mm; }}
.uses {{ font-size: 8.8pt; color:#222; margin: 1.5mm 0 1mm; padding: 1.5mm 0 0; border-top: 0.5px dotted #777; }}
.uses span {{ font-weight:700; margin-right: 1.5mm; }}
table {{ border-collapse: collapse; width:100%; }}
th, td {{ border: 0.6px solid #b9c3cc; padding: 1.2mm 1.8mm; vertical-align: top; }}
th {{ background:#e8eef4; font-weight:700; white-space:nowrap; }}
.c {{ text-align:center; }} .g {{ font-weight:700; white-space:nowrap; }}
.fig {{ width:100%; height:auto; margin: 2mm 0; }}
.fig .t {{ font-size:12px; font-weight:700; }} .fig .s {{ font-size:10.5px; }} .fig .c {{ text-anchor:middle; }}
.cap {{ font-size:8.6pt; text-align:center; margin-top:-1mm; color:#333; }}
.items {{ font-size:7.6pt; line-height:1.28; }}
.items th, .items td {{ padding: 0.55mm 1.2mm; }}
.items .nm {{ white-space:nowrap; }}
.items .m {{ color:#1f4e79; width:9mm; }}
.note {{ font-size:8.8pt; color:#222; }}
.pb {{ break-before: page; }}
</style></head><body>

<h1>UMA-16 음향카메라 실험 계획서</h1>
<div class="sub">{C.SUBTITLE}</div>

<h2>1. 실험 개요</h2>
{paras(C.INTRO)}
<ol class="q">{lis(C.QUESTIONS)}</ol>
{svg}
<div class="cap">그림 1. 실험 배치 평면도</div>

<h2>2. 구입 물품의 구성</h2>
<p>{C.GROUP_INTRO}</p>
<table>
<tr><th>구분</th><th>품목 수</th><th>역할</th></tr>
{group_rows}
</table>
<p class="note">각 품목이 어느 단계에서 쓰이는지는 6장의 표에 정리하였다.</p>

<h2 class="pb">3. 장치 제작 (1~3주차)</h2>
<h3>3.1 자동 회전판</h3>
<ol>{lis(C.BUILD_TURNTABLE)}</ol>
{uses(C.USES['turntable'])}

<h3>3.2 실험용 음원</h3>
{paras(C.BUILD_AUDIO)}
{uses(C.USES['audio'])}

<h2>4. 실험</h2>
<h3>실험 1. 방향 추정의 정확도와 빔 폭 (4주차)</h3>
<p>{C.EXP1_LEAD}</p>
<ol>{lis(C.EXP1)}</ol>

<h3>실험 2. 두 음원의 구분 (5주차)</h3>
<p>{C.EXP2_LEAD}</p>
<ol>{lis(C.EXP2)}</ol>

<h3>실험 3. 빔포밍과 딥러닝의 비교 (6~8주차)</h3>
<p>{C.EXP3_LEAD}</p>
<ol>{lis(C.EXP3)}</ol>
{uses(C.USES['exp3'], '사용 물품 (실험 1~3 공통)')}

<h2>5. 안전 수칙</h2>
<ul>{lis(C.SAFETY)}</ul>

<h2 class="pb">6. 물품별 사용 단계</h2>
<p class="note">{C.ITEMS_NOTE}</p>
<table class="items">
<tr><th>번호</th><th>품목</th><th>제작</th><th>실험 1</th><th>실험 2</th><th>실험 3</th><th>용도</th></tr>
{item_rows}
</table>
</body></html>'''

(HERE / 'plan.html').write_text(html, encoding='utf-8')
# docx(make.js)가 같은 내용을 쓰도록 data.json으로 내보냄
data = {'items': [list(i) for i in ITEMS], 'groups': [list(g) for g in GROUPS],
        'content': {k: getattr(C, k) for k in dir(C) if k.isupper()}}
(HERE / 'data.json').write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page()
        await pg.goto((HERE / 'plan.html').as_uri())
        await pg.pdf(path=str(OUT / '음향카메라_실험계획서.pdf'), format='A4', print_background=True, prefer_css_page_size=True)
        await b.close()
asyncio.run(main())
