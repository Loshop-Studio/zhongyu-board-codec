const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');

// Use actual painted pixels. The fixture has a 90-degree image at 125%,
// between two horizontal strokes, over a 40-unit grid.
module.exports = async function checkMdbPaper(page, evidence, output) {
  const source = path.join(evidence, 'mdb-ink', 'image-grid.zip');
  const tmp = fs.mkdtempSync(path.join(output, 'mdb-paper-'));
  const canvas = page.locator('[flt-semantics-identifier="cloud-ink-canvas"]');
  const button = name => page.getByRole('button', {name: new RegExp('^' + name + '(?: ' + name + ')?$')});
  async function open(label, file) {
    const chooser = page.waitForEvent('filechooser');
    await button(label).click();
    await (await chooser).setFiles(file);
    await canvas.waitFor();
  }
  async function back() {
    await page.getByRole('button', {name: /Back|返回/}).click();
  }
  function gridSamples({missing = false, edited = false} = {}) {
    return [
      [20, 20, 'fff4dc'], [120, 18, '318375'], [18, 120, '318375'],
      [220, 235, '633d91'], [365, 235, missing ? 'eeeeee' : 'c44839'],
      [365, 308, missing ? 'eeeeee' : '3480ae'],
      [365, 333, edited ? 'd32f2f' : '254625'], [310, 212, 'fff4dc'],
    ];
  }
  async function checkPixels(name, samples, width = 1200, height = 900) {
    const file = path.join(output, name + '.png');
    const box = await canvas.boundingBox();
    assert(box);
    const compare = [
      'import sys,json',
      'from PIL import Image',
      'im=Image.open(sys.argv[1]).convert("RGB")',
      'errors=[]',
      'for x,y,color in json.loads(sys.argv[2]):',
      '  cx,cy=round(x*im.width/int(sys.argv[3])),round(y*im.height/int(sys.argv[4]))',
      '  expected=bytes.fromhex(color)',
      '  adjacent=[im.getpixel((cx+i,cy+j)) for i in (-1,0,1) for j in (-1,0,1)]',
      '  if min(max(abs(a-b) for a,b in zip(rgb,expected)) for rgb in adjacent)>18:',
      '    errors.append([x,y,color,im.getpixel((cx,cy))])',
      'print(json.dumps(errors))',
    ].join('\n');
    let errors;
    for (let attempt = 0; attempt < 6; attempt++) {
      await page.screenshot({path: file, clip: box});
      errors = JSON.parse(execFileSync('python3', ['-c', compare, file, JSON.stringify(samples), String(width), String(height)]));
      if (!errors.length) return;
      await page.waitForTimeout(150);
    }
    assert.deepEqual(errors, [], name + ': mismatched canvas pixels');
  }
  try {
    execFileSync('python3', ['-m', 'zipfile', '-e', source, tmp]);
    const folder = path.join(tmp, 'lesson');
    await open('打开笔记', source);
    await checkPixels('mdb-grid-snapshot', gridSamples());
    const box = await canvas.boundingBox();
    await page.mouse.click(box.x + box.width * 480/1200, box.y + box.height * 333/900);
    await page.getByText(/已选第 2 笔/).waitFor();
    await button('红色').click();
    const downloaded = page.waitForEvent('download');
    await button('导出 ZIP').click();
    const edited = path.join(tmp, 'edited.zip');
    await (await downloaded).saveAs(edited);
    await back();
    await open('打开笔记', edited);
    await checkPixels('mdb-grid-edited', gridSamples({edited: true}));
    await back();
    fs.unlinkSync(path.join(folder, 'p1', 'snapshot.bin'));
    await open('打开画板文件夹', folder);
    await checkPixels('mdb-grid-replay', gridSamples());
    await back();
    await open('打开笔记', path.join(folder, 'page_mdb', 'data.mdb'));
    await page.getByText(/缺少 1 张图片/).waitFor();
    await checkPixels('mdb-grid-missing', gridSamples({missing: true}));
    await back();
    await open('打开笔记', path.join(evidence, 'ruled-paper', 'cloud-paper.mdb'));
    // These coordinates and colors come from the paired Android recorder image.
    await checkPixels('mdb-horizontal', [
      [29, 12, '7947a0'], [29, 42, '7947a0'], [29, 25, 'f1f3fc'], [120, 25, 'f1f3fc'],
    ], 640, 480);
    console.log('MDB snapshot, replay, image transform and stacking, grid, stroke edit/export, missing-image indicator passed.');
  } finally {
    fs.rmSync(tmp, {recursive:true, force:true});
  }
};
