const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');

module.exports = async (page, directory, output) => {
  const fixture = path.join(directory, 'simple-eraser');
  const input = path.join(fixture, 'input.bin');
  const original = fs.readFileSync(input);
  const expected = fs.readFileSync(path.join(fixture, 'native-drag.bin'));
  fs.mkdirSync(output, {recursive:true});
  const button = name => page.getByRole('button', {name, exact:true});
  const count = n => page.getByText(new RegExp(n + ' 笔\\s+320 × 240')).first().waitFor();
  async function open(filename, n) {
    const chooser = page.waitForEvent('filechooser');
    await button('打开笔记').click();
    await (await chooser).setFiles(filename);
    await page.getByText(path.basename(filename) + " · SimpleBoard", {exact:true}).waitFor();
    await count(n);
  }
  async function save(filename, bytes) {
    const download = page.waitForEvent('download');
    await button('导出 BIN').click();
    const dest = path.join(output, filename);
    await (await download).saveAs(dest);
    assert.deepEqual(fs.readFileSync(dest), bytes, filename);
  }
  async function paper() {
    return JSON.parse(execFileSync('python3', ['-c',
      "import io,json,sys;sys.path.insert(0,'tools/verification');from PIL import Image;from compare_sketch_render import paper_rectangle;print(json.dumps(paper_rectangle(Image.open(io.BytesIO(sys.stdin.buffer.read())).convert('RGB'))))"
    ], {input:await page.screenshot()}).toString());
  }
  function coordinates(rect, x, y) {
    const [l,t,r,b] = rect;
    return [l + (r-l)*x/320, t + (b-t)*y/240];
  }
  async function snapshot(name) {
    const dest = path.join(output, name);
    await page.screenshot({path:dest});
    return dest;
  }
  await open(input, 7);
  await button('橡皮').click();
  await page.getByText('橡皮半径 40 px', {exact:true}).waitFor();
  await page.mouse.click(...coordinates(await paper(), 304, 225));
  await count(7);
  await save('miss.bin', original);
  const rect = await paper();
  await page.mouse.move(...coordinates(rect,160,48));
  await page.mouse.down();
  await count(6);
  await snapshot('held.png');
  await page.mouse.move(...coordinates(rect,160,60));
  await page.mouse.move(...coordinates(rect,40,175));
  await count(4);
  await page.mouse.up();
  await snapshot('released.png');
  await save('web.bin', expected);
  await button('撤销').click();
  await count(7);
  await save('undo.bin', original);
  await button('重做').click();
  await count(4);
  await save('redo.bin', expected);
  await open(path.join(output,'web.bin'), 4);
  await page.mouse.move(4,4);
  await page.evaluate(() => new Promise(ok => requestAnimationFrame(() => requestAnimationFrame(ok))));
  await snapshot('editor.png');

  await open(input, 7);
  await button('画笔').click();
  await page.getByText('3 px', {exact:true}).waitFor();
  await button('橡皮').click();
  await page.getByText('橡皮半径 40 px', {exact:true}).waitFor();
  const touchRect = await paper();
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Emulation.setTouchEmulationEnabled', {enabled:true, maxTouchPoints:2});
  const [x,y] = coordinates(touchRect,160,48);
  await cdp.send('Input.dispatchTouchEvent', {type:'touchStart', touchPoints:[{x,y,id:1}]});
  await count(6);
  await cdp.send('Input.dispatchTouchEvent', {type:'touchCancel', touchPoints:[]});
  await count(6);
  await button('撤销').click();
  await count(7);
  await save('touch-undo.bin', original);
  fs.writeFileSync(path.join(output,'browser.json'), JSON.stringify({
    viewport:page.viewportSize(), paper:rect, nativePage:[320,240],
    contacts:[[160,48],[160,60],[40,175]], counts:[7,6,4,7,4,4],
    undoRestoredInput:true, missPreservedInput:true, redoRestoredOutput:true,
    touchCancelKeptHit:true, touchUndoRestoredInput:true
  },null,2)+'\n');
  console.log('SimpleBoard: 7 → 6 on down → 4 on drag; undo, redo, export and reopen checked.');
};
