const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

module.exports = async (page, catalog, out) => {
  const source = path.join(catalog, 'ruled-paper', 'native-paper.zip');
  const button = name => page.getByRole('button', {name:new RegExp('^'+name+'(?: '+name+')?$')});
  async function open(file) {
    const chooser = page.waitForEvent('filechooser');
    await button('打开 BIN / ZIP').click();
    await (await chooser).setFiles(file);
    await button('设置纸张').waitFor();
  }
  async function save(file, cloud = false) {
    const download = page.waitForEvent('download');
    await button(cloud ? '按页面 BIN 导出云笔记副本' : '导出 ZIP').click();
    await (await download).saveAs(path.join(out,file));
  }
  async function field(name, value) {
    const el=page.getByRole('textbox',{name,exact:true});
    await el.click();
    await page.keyboard.press('Control+a');
    await page.keyboard.insertText(value);
    await page.keyboard.press('Tab');
  }
  async function shot(name) {
    await page.waitForTimeout(250);
    await page.screenshot({path:path.join(out, name+'.png')});
  }
  await open(source);
  await page.getByText(/2 笔/).first().waitFor();
  await shot('original-edit');
  const slider = page.getByRole('group',{name:'回放进度'}).getByRole('slider');
  const stamp = page.getByText(/^0:\d\d\.\d\d \/ 0:01\.26$/);
  async function seek(fraction) {
    const rect = await slider.boundingBox();
    await page.mouse.click(rect.x+Math.max(1, Math.min(rect.width-1, rect.width*fraction)), rect.y+rect.height/2);
    await page.waitForTimeout(80);
    const m=(await stamp.textContent()).match(/^0:(\d+)\.(\d+)/);
    return Number(m[1])*1000+Number(m[2])*10;
  }
  const low=await seek(.25), high=await seek(.75);
  const trace=[];
  for(const t of [100,200,650,758,1010,1263,400]){
    const actual=await seek(.25+(t-low)/((high-low)*2));
    assert(Math.abs(actual-t)<17,'slider selected '+actual+' for '+t);
    await shot('seek-'+t);
    trace.push({target:t, displayed_ms:actual});
  }
  await button('返回编辑').click();
  await save('untouched.zip');
  assert.deepEqual(fs.readFileSync(path.join(out,'untouched.zip')),fs.readFileSync(source));
  await button('设置纸张').click();
  await field('纸张颜色（ARGB）','FFF1F3FC');
  await field('线条颜色（ARGB）','FF7947A0');
  await field('线距（页面像素）','24');
  await page.getByText('横线',{exact:true}).click();
  await button('应用').click();
  await page.getByText('已更新本页纸张').first().waitFor();
  await shot('changed');
  await save('web-paper.zip');
  await save('cloud-paper.zip',true);
  await button('撤销').click();
  await save('undone.zip');
  assert.deepEqual(fs.readFileSync(path.join(out,'undone.zip')),fs.readFileSync(source));
  await button('重做').click();
  await save('redone.zip');
  await open(path.join(out,'web-paper.zip'));
  await shot('reopened');
  await button('设置纸张').click();
  await page.getByText('空白',{exact:true}).click();
  await button('应用').click();
  await page.getByText('已更新本页纸张').first().waitFor();
  await shot('plain');
  await save('plain.zip');
  fs.writeFileSync(path.join(out,'trace.json'),JSON.stringify(trace,null,2)+'\n');
  console.log('Native ruled-paper recording opened. Seven seeks, backwards seek, paper edit, undo, redo, cloud export, reopen, and removal of ruling passed.');
};
