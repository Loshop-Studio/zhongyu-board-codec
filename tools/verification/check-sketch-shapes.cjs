const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');

module.exports = async (page, fixtures, out) => {
  const button = name => page.getByRole('button', {name, exact:true});
  const count = n => page.getByText(new RegExp(n+' 笔\\s+640 × 480')).first().waitFor();
  async function open(file, n) {
    const chooser = page.waitForEvent('filechooser');
    await button('打开 BIN / ZIP').click();
    await (await chooser).setFiles(file);
    if (file.endsWith('.bin')) {
      await page.getByText(path.basename(file)+' · Sketch', {exact:true}).waitFor();
    } else {
      await page.getByRole('img', {name:'thumbnail.jpg',exact:true}).waitFor({state:'attached'});
    }
    await count(n);
  }
  async function save(name) {
    const download = page.waitForEvent('download');
    await button(name.endsWith('.zip') ? '导出 ZIP' : '导出 BIN').click();
    const file = path.join(out, name);
    await (await download).saveAs(file);
    return fs.readFileSync(file);
  }
  async function drag(tool, a, b) {
    await button(tool).click();
    const script = "import io,json,sys;sys.path.insert(0,'tools/verification');from PIL import Image;from compare_sketch_render import paper_rectangle;print(json.dumps(paper_rectangle(Image.open(io.BytesIO(sys.stdin.buffer.read())).convert('RGB'))))";
    const [l,t,r,bot] = JSON.parse(execFileSync('python3', ['-c', script], {input: await page.screenshot()}));
    const coord = ([x,y]) => [l+(r-l)*x/640, t+(bot-t)*y/480];
    await page.mouse.move(...coord(a));
    await page.mouse.down();
    await page.mouse.move(...coord(b), {steps:12});
    await page.mouse.up();
  }
  fs.mkdirSync(out,{recursive:true});
  for (const v of [5,4,3,2]) {
    const input = path.join(fixtures, 'sketch-shapes/raw-v'+v+'.bin');
    const prefix = v===5 ? '' : 'v'+v+'-';
    await open(input,1);
    assert.deepEqual(await save(prefix+'untouched.bin'), fs.readFileSync(input));
    await drag('矩形', [65,110], [245,210]);
    await count(2);
    const first = await save(prefix+'rect.bin');
    await drag('椭圆', [560,380], [340,250]);
    await count(3);
    const both = await save(prefix+'web.bin');
    await button('撤销').click();
    await count(2);
    assert.deepEqual(await save(prefix+'undo.bin'), first);
    await button('重做').click();
    await count(3);
    assert.deepEqual(await save(prefix+'redo.bin'), both);
    await open(path.join(out,prefix+'web.bin'),3);
    await page.mouse.move(4,4);
    await page.screenshot({path:path.join(out,prefix+'editor.png')});
  }
  const legacy = path.join(fixtures,'sketch-shapes/raw-v1.zip');
  await open(legacy,0);
  assert.deepEqual(await save('v1-untouched.zip'),fs.readFileSync(legacy));
  await drag('矩形', [65,110], [245,210]);
  await count(1);
  await drag('椭圆', [560,380], [340,250]);
  await count(2);
  await save('v1-web.zip');
  await button('撤销').click();
  await count(1);
  await button('重做').click();
  await count(2);
  await open(path.join(out,'v1-web.zip'),0);
  await page.mouse.move(4,4);
  await page.screenshot({path:path.join(out,'v1-editor.png')});
  console.log('V1 JPEG and V2–V5 native data: shape tools, undo, redo, export and reopen checked.');
};
