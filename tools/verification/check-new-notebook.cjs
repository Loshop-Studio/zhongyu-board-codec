const path=require('node:path');
module.exports=async(page,dir,output)=>{
  const button=name=>page.getByRole('button',{name,exact:true});
  async function start(name){
    await button('新建笔记或页面').click();
    await page.getByRole('menuitem',{name,exact:true}).click();
  }
  async function draw(x,y){
    await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x+135,y+45,{steps:9});await page.mouse.up();
  }
  async function download(name,file){
    const pending=page.waitForEvent('download');await button(name).click();await (await pending).saveAs(path.join(output,file));
  }
  await start('新建 Blackboard 笔记');
  await page.getByText(/p1\/snapshot.bin/).first().waitFor({state:'attached'});
  await draw(325,340);
  await page.getByText(/1 笔/).first().waitFor({state:'attached'});
  await start('在当前笔记加一页');
  await page.getByText(/p2\/snapshot.bin/).first().waitFor({state:'attached'});
  await page.getByText(/0 笔/).first().waitFor({state:'attached'});
  await button('撤销').click();
  await page.getByText(/p1\/snapshot.bin/).first().waitFor({state:'attached'});
  await button('重做').click();
  await page.getByText(/p2\/snapshot.bin/).first().waitFor({state:'attached'});
  await button('插入图元').click();
  await page.getByRole('menuitem',{name:'文字',exact:true}).click();
  const input=page.getByRole('textbox',{name:'文字内容',exact:true});
  await input.click();
  await page.keyboard.press('Control+a');
  await input.pressSequentially('Page two', {delay:55});
  await page.keyboard.press('Tab');
  await button('插入').click();
  await page.getByText('已插入文字', {exact:true}).waitFor();
  await button('编辑图元').waitFor();
  await download('导出 ZIP','web-new-notebook.zip');
  await download('按页面 BIN 导出云笔记副本','web-new-notebook-cloud.zip');
  const picker=page.waitForEvent('filechooser');
  await button('打开 BIN / ZIP').click();await(await picker).setFiles(path.join(output,'web-new-notebook.zip'));
  await page.getByText(/p1\/snapshot.bin/).first().waitFor({state:'attached'});
  await page.getByText(/1 笔/).first().waitFor({state:'attached'});
  await page.getByRole('button',{name:/第 1 页/}).click();
  await page.getByRole('menuitem',{name:/第 2 页/}).click();
  await button('编辑图元').click();
  await page.getByRole('menuitem',{name:/Page two/}).waitFor();
  console.log('Created a v6 notebook, drew page 1, added/undid/redid page 2, inserted text, downloaded normal and cloud copies. Reopened page 1 with one stroke and page 2 with the new text.');
};
