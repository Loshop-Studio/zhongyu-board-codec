const path = require('node:path');
module.exports = async (page, directory, output) => {
  const button = name => page.getByRole('button', {name, exact:true});
  async function open(file) {
    const picker = page.waitForEvent('filechooser');
    await button('打开笔记').click();
    await (await picker).setFiles(file);
    await button('编辑图元').waitFor();
  }
  async function edit(name) {
    await button('编辑图元').click();
    await page.getByRole('menuitem', {name}).click();
  }
  async function field(name, value) {
    const input = page.getByRole('textbox', {name, exact:true});
    await input.click();
    await page.keyboard.press('Control+a');
    await page.keyboard.insertText(value);
    await page.waitForFunction(text => [...document.querySelectorAll('textarea,input')].some(el => el.value === text), value, {timeout:5000});
    await page.keyboard.press('Tab');
  }
  async function download(name, dest) {
    const event = page.waitForEvent('download');
    await button(name).click();
    await (await event).saveAs(path.join(output,dest));
  }
  await open(path.join(directory,'artwork-edit-base.zip'));
  await edit(/文字 ·/);
  await field('文字内容','Board 42');
  await field('字号','36');
  await field('颜色（ARGB）','FF164E91');
  await field('水平移动','32');
  await field('垂直移动','12');
  await button('应用').click();
  await button('撤销').click();
  await edit(/文字 · 画板图元/);
  await button('取消').click();
  await button('重做').click();
  await edit(/文字 · Board 42/);
  await button('取消').click();
  await edit(/椭圆 · oval/);
  await field('图元宽度','168');
  await field('图元高度','82');
  await field('描边宽度','7');
  await field('颜色（ARGB）','FF794523');
  await page.getByRole('button',{name:/填充/}).click();
  await page.getByRole('menuitem',{name:'描边',exact:true}).click();
  await button('应用').click();
  await edit(/多边形 · triangle/);
  await field('顶点（每行 x,y）','0,80\n60,5\n110,25\n95,80');
  await field('水平移动','18');
  await field('垂直移动','-6');
  await button('应用').click();
  await page.mouse.move(365,450);await page.mouse.down();
  await page.mouse.move(478,413,{steps:10});await page.mouse.up();
  await page.getByText(/1 笔/).first().waitFor({state:'attached'});
  await download('导出 ZIP','web-artwork-edited.zip');
  await download('按页面 BIN 导出云笔记副本','web-artwork-edited-cloud.zip');
  await open(path.join(output,'web-artwork-edited.zip'));
  await edit(/文字 · Board 42/);
  const fontField = page.getByRole('textbox',{name:'字号',exact:true});
  await fontField.click();
  await page.waitForFunction(() => [...document.querySelectorAll('input,textarea,flt-semantics')].some(el => Number(el.value || el.getAttribute('aria-valuetext')) === 36), undefined, {timeout:5000});
  await button('取消').click();
  await page.getByRole('alertdialog').waitFor({state:'detached'});
  // Flutter removes the semantics node before its Material reverse transition
  // finishes painting; wait for two visually identical frames.
  let last;
  for (let i=0;i<15;i++) {
    await page.waitForTimeout(100);
    const now = await page.screenshot({path:path.join(output,'artwork-edit-web.png')});
    if (last && now.equals(last)) break;
    last = now;
  }
  console.log('v6 browser imported snapshot, edited and moved text, undo/redo, resized and outlined oval, reshaped and moved nested polygon, added stroke, exported both ZIPs, reopened font and title.');
};
