const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const os=require('node:os');
const {execFileSync}=require('node:child_process');

module.exports=async (page,evidence,out)=>{
  const source=path.join(evidence,'cloud-index','native.zip');
  const btn=name=>page.getByRole('button',{name,exact:true});
  async function open(name,file) {
    const wait=page.waitForEvent('filechooser');
    await btn(name).click();await(await wait).setFiles(file);
    await page.getByText(/2 笔/).first().waitFor();
  }
  async function save(name) {
    const wait=page.waitForEvent('download');await btn('导出 ZIP').click();
    await(await wait).saveAs(path.join(out,name));
  }
  async function select(from,to,n) {
    await page.getByRole('button',{name:new RegExp('第 '+from+' 页')}).click();
    await page.getByRole('menuitem',{name:new RegExp('第 '+to+' 页')}).click();
    await page.getByText(new RegExp(n+' 笔')).first().waitFor();
  }
  await open('打开笔记',source);
  await save('untouched.zip');assert.deepEqual(fs.readFileSync(path.join(out,'untouched.zip')),fs.readFileSync(source));
  await select(1,2,1);await select(2,3,2);
  await page.mouse.move(395,360);await page.mouse.down();
  await page.mouse.move(490,425,{steps:8});await page.mouse.up();
  await page.getByText(/3 笔/).first().waitFor();
  await select(3,1,3);await select(1,2,1);await save('web.zip');
  const wait=page.waitForEvent('filechooser');await btn('打开笔记').click();
  await(await wait).setFiles(path.join(out,'web.zip'));
  await page.getByText(/3 笔/).first().waitFor();
  await select(1,2,1);await select(2,3,3);
  const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'zy-cloudpages-'));
  try {
    execFileSync('unzip',['-q',source,'-d',tmp]);
    await open('打开画板文件夹',path.join(tmp,'课堂本'));
    await select(1,2,1);await select(2,3,2);
  } finally { fs.rmSync(tmp,{recursive:true,force:true}); }
  console.log('Android page order, skipped and repeated pages, ZIP and folder open, edit, untouched export and reopen passed.');
};
