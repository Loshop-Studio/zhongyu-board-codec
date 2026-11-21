const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

module.exports = async function(page, fixtures, out) {
  const button = name => page.getByRole('button', {name, exact:true});
  async function open(file, strokes) {
    const choose = page.waitForEvent('filechooser');
    await button('打开笔记').click();
    await (await choose).setFiles(file);
    await page.getByText(new RegExp(strokes+' 笔')).first().waitFor();
    await page.getByRole('img', {name:'thumbnail.jpg',exact:true}).waitFor({state:'attached'});
  }
  async function save(file) {
    const download = page.waitForEvent('download');
    await button('导出 ZIP').click();
    await (await download).saveAs(file);
  }
  async function stroke(x, y) {
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x+150, y-26, {steps:14});
    await page.mouse.up();
    await page.getByText(/1 笔/).first().waitFor();
  }
  for (const version of [1,5]) {
    const input = path.join(fixtures, 'sketch-thumbnails', 'backing-v'+version+'.zip');
    const dir = path.join(out,'v'+version);
    fs.mkdirSync(dir, {recursive:true});
    await open(input,0);
    await save(path.join(dir,'untouched.zip'));
    assert.deepEqual(fs.readFileSync(input),fs.readFileSync(path.join(dir,'untouched.zip')));
    await page.screenshot({path:path.join(dir,'before.png')});
    await stroke(405,603);
    await save(path.join(dir,'web.zip'));
    await button('撤销').click();
    await save(path.join(dir,'undo.zip'));
    assert.deepEqual(fs.readFileSync(input),fs.readFileSync(path.join(dir,'undo.zip')));
    await button('重做').click();
    await page.getByText(/1 笔/).first().waitFor();
    await save(path.join(dir,'redo.zip'));
    await open(path.join(dir,'web.zip'),0);
    await page.screenshot({path:path.join(dir,'after.png')});
    await stroke(300,210);
    await save(path.join(dir,'again.zip'));
  }
  console.log('V1 and old-dated V5 reopened as a single JPEG, edited again, and passed exact untouched/undo checks.');
};
