const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

module.exports = async (page, directory, output, nativeWriter = false) => {
  const prefix=nativeWriter ? 'native-presentation' : 'presentation';
  async function open(file) {
    const chooser = page.waitForEvent('filechooser');
    await page.getByRole('button',{name:'打开 BIN / ZIP'}).click();
    await (await chooser).setFiles(file);
  }
  const control=page.getByRole('button',{name:'课件控制 · lesson.html'});
  const iframe=page.frameLocator('iframe[title="lesson.html"]');
  const title=iframe.locator('#title');
  const expected=async(n,step)=>title.getByText('Slide '+n+' / 3 · '+step,{exact:true}).waitFor({timeout:8000});
  const op=async(label)=>{
    await control.click();
    await page.getByRole('menuitem',{name:label,exact:true}).click();
  };
  const source=path.join(directory,nativeWriter?'native-sketch-presentation.zip':'sketch-presentations.zip');
  await open(source);
  await expected(1,0);
  const media=await iframe.locator('img').evaluate(img=>({
    imageWidth:img.naturalWidth,style:getComputedStyle(document.querySelector('main')).fontSize,
    cssImage:getComputedStyle(document.querySelector('#step')).backgroundImage.startsWith('url("data:image/png;'),
    isolated:(()=>{try{void parent.document;return false}catch(e){return e.name==='SecurityError'}})(),
  }));
  assert.deepEqual(media,{imageWidth:64,style:'24px',cssImage:true,isolated:true});
  await op('下一步动画');await expected(1,1);
  await op('下一张幻灯片');await expected(2,0);
  await op('上一步动画');await expected(1,1);
  await op('跳至课件页');
  await page.getByRole('textbox').fill('3');
  await page.getByRole('button',{name:'跳转',exact:true}).click();
  await expected(3,0);
  await control.click();
  await page.getByRole('menuitem',{name:/lesson.html · 3 \/ 3/}).waitFor();
  await page.getByRole('menuitem',{name:'上一张幻灯片',exact:true}).click();
  await expected(2,0);
  const trace=await title.evaluate(()=>trace.join(','));
  assert.equal(trace,'load,Next,NxtSlide,Prev,GotoSlide:string,PrvSlide');
  const bounds=await page.locator('iframe[title="lesson.html"]').boundingBox();
  const x=bounds.x+bounds.width*.22,y=bounds.y+bounds.height*.75;
  await page.mouse.move(x,y);await page.mouse.down();
  await page.mouse.move(x+bounds.width*.58,y,{steps:18});await page.mouse.up();
  await page.getByText(/1 笔/).first().waitFor({state:'attached'});
  await expected(2,0);
  await page.screenshot({path:path.join(output,'sketch-'+prefix+'-browser.png')});
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'导出 ZIP'}).click();
  const exported=path.join(output,'web-sketch-'+prefix+'.zip');
  await (await download).saveAs(exported);
  await open(exported); await expected(1,0);
  await page.getByText(/1 笔/).first().waitFor({state:'attached'});
  await open(source);await expected(1,0);
  await op('下一张幻灯片');await expected(2,0);
  const previewDownload=page.waitForEvent('download');
  await page.getByRole('button',{name:'导出 ZIP'}).click();
  const previewBytes=await (await previewDownload).path();
  assert.deepEqual(fs.readFileSync(previewBytes),fs.readFileSync(source));
  const result={media,trace:trace.split(','),boardBounds:bounds,stroke:{x,y,endX:x+bounds.width*.58},exportReopened:true,previewOnlyByteIdentical:true};
  fs.writeFileSync(path.join(output,prefix+'-browser.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result));
};
