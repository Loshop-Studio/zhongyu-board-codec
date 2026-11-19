const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

module.exports = async (page, fixtures, out, returned = false) => {
  const button = name => page.getByRole('button', {name:new RegExp('^'+name+'(?: '+name+')?$')});
  async function open(file, count) {
    const ready = page.waitForEvent('filechooser');
    await button('打开 BIN / ZIP').click();
    await (await ready).setFiles(file);
    await page.getByText(new RegExp(count+' 笔')).first().waitFor();
  }
  async function save(name,file) {
    const pending=page.waitForEvent('download');
    await button(name).click();
    await (await pending).saveAs(path.join(out,file));
  }
  if (returned) {
    const source=path.join(fixtures,'android-resaved-v6.zip');
    await open(source,4);
    await page.screenshot({path:path.join(out,'browser-return.png')});
    await save('导出 ZIP','resaved-unchanged.zip');
    assert.deepEqual(fs.readFileSync(path.join(out,'resaved-unchanged.zip')),fs.readFileSync(source));
    console.log('Opened all four strokes from the original Android resave and exported identical bytes.');
    return;
  }
  const original=process.env.V6_SOURCE || path.join(fixtures,'native-v6-recording.zip');
  await open(original,2);
  await page.screenshot({path:path.join(out,'browser-native.png')});
  const slider=page.getByRole('group',{name:'回放进度'}).getByRole('slider');
  const seek = async (fraction, count) => {
    const box=await slider.boundingBox();
    await page.mouse.click(box.x+box.width*fraction,box.y+box.height/2);
    await page.getByText(new RegExp(count+' 笔')).first().waitFor();
  };
  await seek(.03,0);
  await seek(.34,1);
  await page.screenshot({path:path.join(out,'browser-writing.png')});
  await seek(.98,2);
  await button('返回编辑').click();
  await save('导出 ZIP','untouched.zip');
  assert.deepEqual(fs.readFileSync(path.join(out,'untouched.zip')),fs.readFileSync(original));

  await page.mouse.move(390,500);
  await page.mouse.down();
  await page.mouse.move(460,545,{steps:5});
  await page.waitForTimeout(120); // Include a measurable pause in the touch history.
  await page.mouse.move(535,492,{steps:6});
  await page.mouse.up();
  await page.getByText(/3 笔/).first().waitFor();
  await page.screenshot({path:path.join(out,'browser-edit.png')});
  await save('导出 ZIP','web-native-v6.zip');
  await save('按页面 BIN 导出云笔记副本','web-native-v6-cloud.zip');
  await button('撤销').click();
  await save('导出 ZIP','undone.zip');
  assert.deepEqual(fs.readFileSync(path.join(out,'undone.zip')),fs.readFileSync(original));
  await button('重做').click();
  await page.getByText(/3 笔/).first().waitFor();
  await save('导出 ZIP','redone.zip');

  await open(path.join(out,'web-native-v6.zip'),3);
  await button('新建笔记或页面').click();
  await page.getByRole('menuitem',{name:'在当前笔记加一页',exact:true}).click();
  await page.getByText(/0 笔/).first().waitFor();
  await save('导出 ZIP','web-native-v6-two-pages.zip');
  console.log('Loaded native recording, sought to blank, first ink and both inks, added a third stroke, undid to original ZIP bytes, reopened edit and added a page.');
};
