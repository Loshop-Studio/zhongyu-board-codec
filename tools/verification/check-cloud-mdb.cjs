const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

module.exports = async function checkCloudMdb(page, evidence, output) {
  const source = path.join(evidence, 'page_mdb', 'native-v6-two-pages.mdb');
  const button = name => page.getByRole('button', {name: new RegExp('^' + name + '(?: ' + name + ')?$')});
  const open = async (label, input) => {
    const chooser = page.waitForEvent('filechooser');
    await button(label).click();
    await (await chooser).setFiles(input);
  };
  const save = async (label, name) => {
    const download = page.waitForEvent('download');
    await button(label).click();
    const target = path.join(output, name);
    await (await download).saveAs(target);
    return target;
  };
  const tmp = fs.mkdtempSync(path.join(output, 'mdb-input-'));
  try {
    const folder = path.join(tmp, 'lesson');
    fs.mkdirSync(path.join(folder, 'page_mdb'), {recursive:true});
    fs.copyFileSync(source, path.join(folder, 'page_mdb', 'data.mdb'));
    fs.writeFileSync(path.join(folder, 'companion.txt'), 'keep');
    const zip = path.join(tmp, 'lesson.zip');
    execFileSync('python3', ['-m','zipfile','-c',zip,'lesson'], {cwd:tmp});
    await open('打开笔记', source);
    await page.getByText('3 笔 · 640 × 480', {exact:true}).waitFor();
    const canvas = page.locator('[flt-semantics-identifier="cloud-ink-canvas"]');
    const box = await canvas.boundingBox();
    assert(box);
    const xy = (x,y) => [box.x+x*box.width/640,box.y+y*box.height/480];
    const before = path.join(output,'mdb-ink-before.png');
    await page.screenshot({path:before,clip:box});
    await page.mouse.click(...xy(120,88));
    await page.getByText(/已选第 1 笔/).waitFor();
    await button('红色').click();
    await button('线宽').click();
    await page.getByRole('menuitem',{name:'12 px',exact:true}).click();
    await button('调整采样点').click();
    await page.mouse.move(...xy(120,88)); await page.mouse.down();
    await page.mouse.move(...xy(132,100),{steps:8}); await page.mouse.up();
    await button('调整采样点').click();
    await page.screenshot({path:path.join(output,'mdb-ink-after.png'),clip:box});
    const edited = await save('导出 MDB','edited.mdb');
    for(let i=0;i<3;i++) await button('撤销').click();
    const undone = await save('导出 MDB','undone.mdb');
    assert.deepEqual(fs.readFileSync(undone),fs.readFileSync(source));
    for(let i=0;i<3;i++) await button('重做').click();
    const redone=await save('导出 MDB','redone.mdb');
    assert.deepEqual(fs.readFileSync(redone),fs.readFileSync(edited));
    await page.getByRole('button',{name:/第 1 页 ·/}).click();
    await page.getByRole('menuitem',{name:/第 2 页 ·/}).click();
    await page.getByText('0 笔 · 640 × 480',{exact:true}).waitFor();
    await page.getByRole('button',{name:/Back|返回/}).click();
    await open('打开笔记',edited);
    await page.getByText('3 笔 · 640 × 480',{exact:true}).waitFor();
    await page.getByRole('button',{name:/Back|返回/}).click();
    for(const [label,input] of [['打开笔记',zip],['打开画板文件夹',folder]]){
      await open(label,input);
      await page.getByText('3 笔 · 640 × 480',{exact:true}).waitFor();
      await page.mouse.click(...xy(120,88));
      await button('蓝色').click();
      const outputZip=await save('导出 ZIP','edited-archive.zip');
      execFileSync('python3',['-c', [
        'from zipfile import ZipFile',
        'from pathlib import Path',
        'import sys',
        'z=ZipFile(sys.argv[1]); m=next(n for n in z.namelist() if n.endswith("page_mdb/data.mdb"))',
        'assert z.read(m)!=Path(sys.argv[2]).read_bytes()',
        'assert z.read(next(n for n in z.namelist() if n.endswith("companion.txt")))==b"keep"',
      ].join('\n'),outputZip,source]);
      await page.getByRole('button',{name:/Back|返回/}).click();
    }
    await open('打开笔记',path.join(evidence,'cloud-mixed.zip'));
    await button('数据库详情').click();
    await page.getByText('本地画板样本',{exact:true}).waitFor();
    await button('关闭').click();
    await button('打开旧 BIN 页面').click();
    await button('导出 ZIP').waitFor();
    console.log('Original strokes, paint, point drag, undo/redo, pages, exported MDB reopen, folder/ZIP preservation and mixed legacy entry passed.');
  } finally {fs.rmSync(tmp,{recursive:true,force:true});}
};
