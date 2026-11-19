const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

module.exports = async (page, fixtures, out) => {
  const button = name => page.getByRole('button', {name, exact: true});
  const note = path.join(fixtures, 'sketch-thumbnails/native.zip');
  async function open(file, strokes) {
    const incoming = page.waitForEvent('filechooser');
    await button('打开 BIN / ZIP').click();
    await (await incoming).setFiles(file);
    await page.getByText(new RegExp(strokes+' 笔')).first().waitFor();
  }
  async function save(name) {
    const download = page.waitForEvent('download');
    await button('导出 ZIP').click();
    await (await download).saveAs(path.join(out, name));
  }
  await open(note, 1);
  await page.getByRole('img', {name:'diagram.jpg', exact:true}).waitFor({state:'attached'});
  await save('untouched.zip');
  assert.deepEqual(fs.readFileSync(path.join(out,'untouched.zip')),fs.readFileSync(note));
  await page.mouse.move(405,603);
  await page.mouse.down();
  await page.mouse.move(617,551,{steps:14});
  await page.mouse.up();
  await page.getByText(/2 笔/).first().waitFor();
  await save('web.zip');
  await button('撤销').click();
  await save('undo.zip');
  assert.deepEqual(fs.readFileSync(path.join(out,'undo.zip')),fs.readFileSync(note));
  await button('重做').click();
  await save('redo.zip');
  await open(path.join(out,'web.zip'), 2);
  await page.getByRole('img', {name:'diagram.jpg', exact:true}).waitFor({state:'attached'});
  await page.screenshot({path:path.join(out,'editor.png')});
  console.log('Native compacted snapshot, edited and untouched ZIP, JPEG, undo, redo and reopen checked.');
};
