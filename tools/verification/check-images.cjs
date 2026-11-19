const path = require('node:path');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');

module.exports = async (page, directory, output) => {
  const open = async (name) => {
    const chooser = page.waitForEvent('filechooser');
    await page.getByRole('button', {name: '打开 BIN / ZIP'}).click();
    await (await chooser).setFiles(path.join(directory, name));
  };
  const named = (filename) => page.getByRole('img', {name: filename, exact: true});
  const snapshot = (name) => page.screenshot({path: path.join(output, name)});
  const image = execFileSync('python3', ['-c',
    "import sys,zipfile; sys.stdout.buffer.write(zipfile.ZipFile(sys.argv[1]).read('illustration/res/center.png'))",
    path.join(directory,'sketch-images.zip')]);
  const insert = async () => {
    const chooser = page.waitForEvent('filechooser');
    await page.getByRole('button',{name:'插入图片'}).click();
    await (await chooser).setFiles({name:'center.png',mimeType:'image/png',buffer:image});
    await page.getByRole('textbox').fill('128');
    await page.getByRole('button',{name:'居中',exact:true}).click();
    await page.getByRole('menuitem',{name:'左下',exact:true}).click();
    await page.getByRole('button',{name:'插入',exact:true}).click();
  };
  await open('sketch-images.zip');
  await named('icons/upper.jpg').waitFor({state: 'attached'});
  await named('center.png').waitFor({state: 'attached'});
  await page.getByText(/2 笔/).first().waitFor({state: 'attached'});
  await snapshot('illustration-web.png');
  await page.mouse.move(392, 484);
  await page.mouse.down();
  await page.mouse.move(594, 415, {steps: 14});
  await page.mouse.up();
  await page.getByText(/3 笔/).first().waitFor({state: 'attached'});
  await page.getByRole('button', {name: '撤销'}).click();
  await page.getByText(/2 笔/).first().waitFor({state: 'attached'});
  await page.getByRole('button', {name: '重做'}).click();
  await page.getByText(/3 笔/).first().waitFor({state: 'attached'});
  await named('center.png').waitFor({state: 'attached'});
  await insert();
  await named('center-2.png').waitFor({state:'attached'});
  await page.getByRole('button',{name:'撤销'}).click();
  await named('center-2.png').waitFor({state:'detached'});
  await page.getByRole('button',{name:'重做'}).click();
  await named('center-2.png').waitFor({state:'attached'});
  const download = page.waitForEvent('download');
  await page.getByRole('button', {name: '导出 ZIP'}).click();
  const dest = path.join(output, 'web-sketch-images.zip');
  await (await download).saveAs(dest);
  await snapshot('image-edit-web.png');
  const reopen = page.waitForEvent('filechooser');
  await page.getByRole('button', {name: '打开 BIN / ZIP'}).click();
  await (await reopen).setFiles(dest);
  await named('icons/upper.jpg').waitFor({state: 'attached'});
  await page.getByText(/3 笔/).first().waitFor({state: 'attached'});
  await open('sketch-image-recording.zip');
  await named('center.png').waitFor({state: 'attached'});
  const play = page.getByRole('button', {name:'播放录制'});
  await play.click();
  await page.getByText('0:01.20 / 0:01.20', {exact:true}).waitFor({state:'attached'});
  await named('center.png').waitFor({state: 'attached'});
  assert.equal(await named('icons/upper.jpg').count(), 0);
  await snapshot('image-recording-web.png');
  await open('art-actions.bin');
  await page.getByRole('button',{name:'导出 BIN'}).waitFor();
  await insert();
  await page.getByRole('button',{name:'导出 ZIP'}).waitFor();
  await named('center.png').waitFor({state:'attached'});
  await page.getByRole('button',{name:'撤销'}).click();
  await page.getByRole('button',{name:'导出 BIN'}).waitFor();
  await page.getByRole('button',{name:'重做'}).click();
  await page.getByRole('button',{name:'导出 ZIP'}).waitFor();
  await named('center.png').waitFor({state:'attached'});
  for (const version of [2,3,4,5]) {
    const zip = execFileSync('python3',['-c',[
      'import io,sys,zipfile',
      'src=zipfile.ZipFile(sys.argv[1]); out=io.BytesIO()',
      "with zipfile.ZipFile(out,'w') as z:",
      " for n in src.namelist():",
      "  if n.startswith('image-v'+sys.argv[2]+'/'): z.writestr(n,src.read(n))",
      'sys.stdout.buffer.write(out.getvalue())',
    ].join('\n'),path.join(directory,'sketch-image-versions.zip'),String(version)]);
    const choose = page.waitForEvent('filechooser');
    await page.getByRole('button',{name:'打开 BIN / ZIP'}).click();
    await (await choose).setFiles({name:'v'+version+'.zip',mimeType:'application/zip',buffer:zip});
    await page.getByText(new RegExp('image-v'+version+'/actions\\.bin')).first().waitFor({state:'attached'});
    await named('center.png').waitFor({state:'attached'});
    await snapshot('image-v'+version+'-web.png');
  }
  console.log('PNG and nested JPEG opened; drew third stroke, inserted another image at 128px bottom left, retained both same-name resources, undo, redo, ZIP export and reopen; standalone BIN to ZIP undo/redo; original 1.2 s recording played to its translucent snapshot.');
};
