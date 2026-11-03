const fs = require('fs');
const path = require('path');
const HERE = __dirname;
const OUT = path.join(HERE, '..', '..', '문서');
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType,
  AlignmentType, BorderStyle, ImageRun, LevelFormat, PageBreak, HeadingLevel } = require('docx');

const data = JSON.parse(fs.readFileSync(path.join(HERE, 'data.json'), 'utf8'));
const by = {}; data.items.forEach(i => by[i[0]] = i);
const COST = new Set([2, 3, 45]);
const goods = data.items.filter(i => !COST.has(i[0]));
const names = ns => ns.map(n => by[n][1]).join(', ');

const FONT = '맑은 고딕';
const run = (t, o = {}) => new TextRun({ text: t, font: { name: FONT, eastAsia: FONT }, size: o.size || 20, bold: o.bold, color: o.color });
const P = (t, o = {}) => new Paragraph({ children: Array.isArray(t) ? t : [run(t, o)], alignment: o.align || AlignmentType.JUSTIFIED, spacing: { after: o.after ?? 100, line: 300 }, ...(o.extra || {}) });
const H1 = t => new Paragraph({ children: [run(t, { size: 32, bold: true, color: '000000' })], spacing: { after: 60 } });
const H2 = (t, pb) => new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: !!pb, children: [run(t, { size: 23, bold: true, color: '000000' })], spacing: { before: 260, after: 120 }, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: '000000', space: 2 } } });
const H3 = (t, pb) => new Paragraph({ heading: HeadingLevel.HEADING_2, pageBreakBefore: !!pb, children: [run(t, { size: 21, bold: true, color: '000000' })], spacing: { before: 160, after: 60 } });
const NUM = (t, ref, lvl = 0) => new Paragraph({ numbering: { reference: ref, level: lvl }, children: [run(t)], alignment: AlignmentType.JUSTIFIED, spacing: { after: 50, line: 300 } });
const BUL = t => new Paragraph({ numbering: { reference: 'bul', level: 0 }, children: [run(t)], spacing: { after: 50, line: 300 } });
const C = data.content;
const USES = (ns, label = '사용 물품  ') => new Paragraph({ children: [run(label, { bold: true, size: 18 }), run(names(ns), { size: 18 })], spacing: { before: 60, after: 120, line: 280 }, border: { top: { style: BorderStyle.DOTTED, size: 4, color: '777777', space: 3 } } });

const border = { style: BorderStyle.SINGLE, size: 4, color: 'B9C3CC' };
const borders = { top: border, bottom: border, left: border, right: border };
const cell = (t, w, o = {}) => new TableCell({
  width: { size: w, type: WidthType.DXA }, borders,
  shading: o.head ? { type: ShadingType.CLEAR, fill: 'E8EEF4', color: 'auto' } : undefined,
  margins: { top: o.tight ? 20 : 50, bottom: o.tight ? 20 : 50, left: 80, right: 80 },
  children: [new Paragraph({ alignment: o.center ? AlignmentType.CENTER : AlignmentType.LEFT, children: [run(t, { size: o.size || 19, bold: o.head || o.bold, color: o.color })] })],
});
const table = (widths, rows) => new Table({ width: { size: widths.reduce((a, b) => a + b), type: WidthType.DXA }, columnWidths: widths, rows });

// 그룹 표 (본문 폭 A4 - 여백 16mm*2 ≈ 9826 DXA)
const gW = [2000, 1100, 6726];
const groupTable = table(gW, [
  new TableRow({ tableHeader: true, children: [cell('구분', gW[0], { head: 1, center: 1 }), cell('품목 수', gW[1], { head: 1, center: 1 }), cell('역할', gW[2], { head: 1, center: 1 })] }),
  ...data.groups.map(([g, ns, d]) => new TableRow({ children: [cell(g, gW[0], { bold: 1 }), cell(String(ns.length), gW[1], { center: 1 }), cell(d, gW[2])] })),
]);

// 물품 표
const iW = [600, 2900, 650, 700, 700, 700, 3576];
const mk = v => v ? '●' : '';
const itemTable = table(iW, [
  new TableRow({ tableHeader: true, children: ['번호', '품목', '제작', '실험 1', '실험 2', '실험 3', '용도'].map((h, k) => cell(h, iW[k], { head: 1, center: 1, size: 15, tight: 1 })) }),
  ...goods.map(([n, nm, p, a, b, c, d, u]) => new TableRow({ children: [
    cell(String(n), iW[0], { center: 1, size: 15, tight: 1 }), cell(nm, iW[1], { size: 15, tight: 1 }),
    cell(mk(a), iW[2], { center: 1, size: 15, tight: 1, color: '1F4E79' }), cell(mk(b), iW[3], { center: 1, size: 15, tight: 1, color: '1F4E79' }),
    cell(mk(c), iW[4], { center: 1, size: 15, tight: 1, color: '1F4E79' }), cell(mk(d), iW[5], { center: 1, size: 15, tight: 1, color: '1F4E79' }),
    cell(u, iW[6], { size: 15, tight: 1 })] })),
]);

const img = fs.readFileSync(path.join(HERE, 'fig.png'));
const numCfg = ref => ({ reference: ref, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 400, hanging: 300 } } } }] });

const body = [
  H1('UMA-16 음향카메라 실험 계획서'),
  P(C.SUBTITLE, { size: 18, after: 200, color: '333333', align: AlignmentType.LEFT }),

  H2('1. 실험 개요'),
  ...C.INTRO.map(t => P(t)),
  ...C.QUESTIONS.map(t => NUM(t, 'q')),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120 }, children: [new ImageRun({ type: 'png', data: img, transformation: { width: 600, height: 225 } })] }),
  P('그림 1. 실험 배치 평면도', { size: 17, align: AlignmentType.CENTER, after: 120 }),

  H2('2. 구입 물품의 구성'),
  P(C.GROUP_INTRO),
  groupTable,
  P('각 품목이 어느 단계에서 쓰이는지는 6장의 표에 정리하였다.', { size: 18, extra: { spacing: { before: 80, after: 100 } } }),

  H2('3. 장치 제작 (1~3주차)', true),
  H3('3.1 자동 회전판'),
  ...C.BUILD_TURNTABLE.map(t => NUM(t, 'a')),
  USES(C.USES.turntable),
  H3('3.2 실험용 음원'),
  ...C.BUILD_AUDIO.map(t => P(t)),
  USES(C.USES.audio),

  H2('4. 실험'),
  H3('실험 1. 방향 추정의 정확도와 빔 폭 (4주차)'),
  P(C.EXP1_LEAD),
  ...C.EXP1.map(t => NUM(t, 'e1')),
  H3('실험 2. 두 음원의 구분 (5주차)'),
  P(C.EXP2_LEAD),
  ...C.EXP2.map(t => NUM(t, 'e2')),
  H3('실험 3. 빔포밍과 딥러닝의 비교 (6~8주차)'),
  P(C.EXP3_LEAD),
  ...C.EXP3.map(t => NUM(t, 'e3')),
  USES(C.USES.exp3, '사용 물품 (실험 1~3 공통)  '),

  H2('5. 안전 수칙'),
  ...C.SAFETY.map(t => BUL(t)),

  H2('6. 물품별 사용 단계', true),
  P(C.ITEMS_NOTE, { size: 18 }),
  itemTable,
];

const doc = new Document({
  styles: { default: { document: { run: { font: { name: FONT, eastAsia: FONT }, size: 20 } } } },
  numbering: { config: [numCfg('q'), numCfg('a'), numCfg('e1'), numCfg('e2'), numCfg('e3'),
    { reference: 'bul', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 400, hanging: 300 } } } }] }] },
  sections: [{ properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 907, bottom: 850, left: 907, right: 907 } } }, children: body }],
});
Packer.toBuffer(doc).then(b => { fs.writeFileSync(path.join(OUT, '음향카메라_실험계획서.docx'), b); console.log('ok'); });
