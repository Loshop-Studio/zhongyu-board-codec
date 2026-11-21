const path = require('node:path');
const {execFileSync} = require('node:child_process');
module.exports = async (page, directory, output) => {
  const button = name => page.getByRole('button', {name, exact:true});
  async function open(file) {
    const picker = page.waitForEvent('filechooser');
    await button('打开笔记').click();
    await (await picker).setFiles(file);
    await button('插入图元').waitFor();
  }
  async function menu(name) {
    await button('插入图元').click();
    await page.getByRole('menuitem',{name,exact:true}).click();
  }
  async function field(name,value) {
    const input=page.getByRole('textbox',{name,exact:true});
    await input.click();
    await page.keyboard.press('Control+a');
    await page.keyboard.insertText(String(value));
    await page.waitForFunction(v=>[...document.querySelectorAll('textarea,input')].some(e=>e.value===v),String(value),{timeout:5000});
    await page.keyboard.press('Tab');
  }
  async function add(name,x,y,w,h) {
    const image=name==='图片';
    if(image) {
      const chooser=page.waitForEvent('filechooser');
      await menu(name);
      const bytes=execFileSync('unzip',['-p',path.join(directory,'artwork-edit-base.zip'),'lesson/res/image/tiles.png']);
      // Use a filename that already belongs to an original graph.
      await (await chooser).setFiles({name:'tiles.png',mimeType:'image/png',buffer:bytes});
    } else await menu(name);
    if(name==='文字') await field('文字内容','Board 17');
    await field('页面 X',x);await field('页面 Y',y);
    await field('图元宽度',w);
    if(!image)await field('图元高度',h);
    await button('插入').click();
    await page.getByRole('alertdialog').waitFor({state:'detached'});
  }
  async function save(buttonName,name) {
    const event=page.waitForEvent('download');
    await button(buttonName).click();
    await (await event).saveAs(path.join(output,name));
  }
  await open(path.join(directory,'schema-page.zip'));
  await add('矩形',0,0,60,50);
  await button('撤销').click();
  await button('编辑图元').waitFor({state:'detached',timeout:5000});
  await open(path.join(directory,'artwork-edit-base.zip'));
  await add('文字',40,290,180,58);
  await add('椭圆',65,385,90,72);
  await add('矩形',235,380,105,80);
  await add('三角形',405,375,105,88);
  await add('图片',590,355,100,100);
  await button('撤销').click();
  await button('重做').click();
  await save('导出 ZIP','web-artwork-created.zip');
  await save('按页面 BIN 导出云笔记副本','web-artwork-created-cloud.zip');
  await open(path.join(output,'web-artwork-created.zip'));
  await button('编辑图元').click();
  await page.getByRole('menuitem',{name:/文字 · Board 17/}).waitFor();
  await page.keyboard.press('Escape');
  await page.getByRole('menuitem').first().waitFor({state:'detached'});
  let last;
  for(let i=0;i<15;i++) {
    await page.waitForTimeout(150);
    const now=await page.screenshot({path:path.join(output,'artwork-create-web.png')});
    if(last && now.equals(last))break;
    last=now;
  }
  console.log('Created and undid a shape on an empty v6 page. Added text, oval, rectangle, triangle and an image with a colliding filename on an existing page, undid/redid the image, downloaded both ZIPs and reopened the saved note.');
};
