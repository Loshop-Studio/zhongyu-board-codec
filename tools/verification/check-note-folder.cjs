const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');

module.exports = async (page, evidence, output) => {
  const work = fs.mkdtempSync(path.join(os.tmpdir(),'zy-board-folder-'));
  const source = path.join(evidence,'native-note-bundle.zip');
  const folder = path.join(work,'示例笔记');
  const button = name => page.getByRole('button',{name,exact:true});
  async function open(name, file) {
    const next = page.waitForEvent('filechooser');
    await button(name).click();
    await (await next).setFiles(file);
  }
  async function save(dest) {
    const next = page.waitForEvent('download');
    await button('导出 ZIP').click();
    const download = await next;
    await download.saveAs(dest);
    return download.suggestedFilename();
  }
  async function waitCount(n) {
    await page.getByText(new RegExp(n+' 笔')).first().waitFor({state:'attached'});
  }
  try {
    fs.mkdirSync(folder);
    execFileSync('python3',['-m','zipfile','-e',source,folder]);
    await open('打开笔记',source);
    await waitCount(1);
    const raw = path.join(work,'untouched-zip.zip');
    await save(raw);
    assert.ok(fs.readFileSync(raw).equals(fs.readFileSync(source)));
    await open('打开画板文件夹',folder);
    await page.getByText('已打开文件夹 · 示例笔记', {exact:true}).waitFor({state:'attached'});
    const folderZip = path.join(output,'folder-note.zip');
    assert.equal(await save(folderZip),'示例笔记.zip');
    await page.mouse.move(366,445);await page.mouse.down();
    await page.mouse.move(513,398,{steps:12});await page.mouse.up();
    await waitCount(2);
    await button('撤销').click();await waitCount(1);
    await button('重做').click();await waitCount(2);
    const edited = path.join(output,'folder-note-edited.zip');
    assert.equal(await save(edited),'示例笔记.zip');
    await open('打开笔记',edited);
    await waitCount(2);
    const report=execFileSync('python3',[path.join(__dirname,'check_note_folder.py'),source,folderZip,edited],{encoding:'utf8'});
    fs.writeFileSync(path.join(output,'note-folders.json'),report);
    const check=JSON.parse(report);
    console.log('Native ZIP preserved byte for byte. Directory chooser, edit, undo, redo and ZIP reopen passed.',
      check.original_regular_files,'original files preserved;',check.changed.length,'updated;',check.created.length,'added.');
  } finally { fs.rmSync(work,{recursive:true,force:true}); }
};
