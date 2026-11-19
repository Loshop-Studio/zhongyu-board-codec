const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');

module.exports = async (page, directory, output, mode = 'edit') => {
  const button = name => page.getByRole('button', {name, exact:true});
  async function open(file) {
    const picker = page.waitForEvent('filechooser');
    await button('打开 BIN / ZIP').click();
    await (await picker).setFiles(file);
    await button('编辑图元').waitFor();
  }
  async function save(name, dest) {
    const download = page.waitForEvent('download');
    await button(name).click();
    await (await download).saveAs(dest);
  }
  async function field(name, value) {
    await page.getByRole('textbox', {name, exact:true}).click();
    await page.keyboard.press('Control+a');
    await page.keyboard.insertText(value);
    await page.keyboard.press('Tab');
  }
  const input = path.join(directory,'artwork-edit-base.zip');
  const edited = path.join(output,'web-page-image.zip');
  async function capture() {
    let last;
    for (let i=0;i<12;i++) {
      await page.waitForTimeout(100);
      const now = await page.screenshot({path:path.join(output,'page-image-web.png')});
      if (last && last.equals(now)) return;
      last = now;
    }
    throw new Error('page did not reach a stable frame');
  }
  if (mode === 'preview') {
    await open(path.join(directory,'web-page-image.zip'));
    await capture();
    return;
  }
  async function paper() {
    const frame = await page.screenshot();
    return JSON.parse(execFileSync('python3',['-c',
      "import io,json,sys;sys.path.insert(0,'tools/verification');from PIL import Image;from compare_sketch_render import paper_rectangle;print(json.dumps(paper_rectangle(Image.open(io.BytesIO(sys.stdin.buffer.read())).convert('RGB'))))"],
      {input:frame}).toString());
  }
  if (mode === 'touch') {
    await open(input);
    await button('拖动图片').click();
    const [l,t,r,b] = await paper();
    const point = (x,y) => ({x:l+x*(r-l)/800,y:t+y*(b-t)/600,id:1});
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Emulation.setTouchEmulationEnabled', {enabled:true,maxTouchPoints:2});
    const event = (type, ...touchPoints) => cdp.send('Input.dispatchTouchEvent',{type,touchPoints});
    for (const end of ['touchCancel','touchEnd']) {
      await event('touchStart',point(492.5,202.5));
      await event('touchMove',point(522.5,222.5));
      await event(end);
      const result = path.join(output,'web-page-image-touch.zip');
      await save('导出 ZIP',result);
      if (end==='touchCancel') assert.deepEqual(fs.readFileSync(result),fs.readFileSync(input));
      else assert.notDeepEqual(fs.readFileSync(result),fs.readFileSync(input));
    }
    await button('撤销').click();
    const reverted = path.join(output,'touch-undo.zip');
    await save('导出 ZIP',reverted);
    assert.deepEqual(fs.readFileSync(reverted),fs.readFileSync(input));
    fs.unlinkSync(reverted);
    console.log('Chromium touch: cancelled image drag leaves entire ZIP identical; completed one-finger drag, exported and reversed to identical ZIP.');
    return;
  }
  await open(input);
  await button('编辑图元').click();
  await page.getByRole('menuitem',{name:'图片 · tiles.png'}).click();
  await field('缩放比例（%）','150');
  await field('顺时针旋转（度）','90');
  await field('水平移动','20');
  await field('垂直移动','-12');
  await button('应用').click();
  await button('撤销').click();
  await save('导出 ZIP',edited);
  assert.deepEqual(fs.readFileSync(input),fs.readFileSync(edited));
  await button('重做').click();
  await button('拖动图片').click();
  const rect = await paper();
  const xy = (x,y) => [rect[0]+x*(rect[2]-rect[0])/800,rect[1]+y*(rect[3]-rect[1])/600];
  const drag = async (start,end) => {
    await page.mouse.move(...xy(...start)); await page.mouse.down();
    await page.mouse.move(...xy(...end),{steps:10}); await page.mouse.up();
  };
  await drag([55,530],[115,565]); // Empty paper must not change the note.
  await drag([512.5,190.5],[572.5,230.5]);
  await page.getByText(/0 笔/).first().waitFor({state:'attached'});
  await save('导出 ZIP',edited);
  await save('按页面 BIN 导出云笔记副本',path.join(output,'web-page-image-cloud.zip'));
  await open(edited);
  await capture();
  console.log('V6 image: 150%, clockwise 90 degrees, translation (20,-12), undo restores identical ZIP, redo, blank drag, selected image drag (60,40), exported and reopened.');
};
