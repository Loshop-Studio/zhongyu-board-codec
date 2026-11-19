const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

module.exports = async (page, dir, out) => {
  const source=path.join(dir,'page-replay.zip');
  const button = name=>page.getByRole('button',{name:new RegExp('^'+name+'(?: '+name+')?$')});
  async function open(file){
    const chooser=page.waitForEvent('filechooser');
    await button('打开 BIN / ZIP').click();await (await chooser).setFiles(file);
    await button('播放本页回放').waitFor();
  }
  async function save(name){
    const pending=page.waitForEvent('download');
    await button('导出 ZIP').click();await(await pending).saveAs(name);
  }
  const slider=page.getByRole('group',{name:'回放进度'}).getByRole('slider');
  const stamp=page.getByText(/^0:\d\d\.\d\d \/ 0:03\.10$/);
  async function clickAt(xFraction) {
    const box=await slider.boundingBox();
    await page.mouse.click(box.x+box.width*xFraction,box.y+box.height/2);
    await page.waitForTimeout(90);
    const match=(await stamp.textContent()).match(/^0:(\d+)\.(\d+)/);
    return Number(match[1])*1000+Number(match[2])*10;
  }
  await open(source);
  await page.evaluate(()=>{
    window.replayMedia=[];
    const play=HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play=function(...args){window.replayMedia.push(this);return play.apply(this,args);};
  });
  await button('播放本页回放').click();
  await page.waitForFunction(()=>window.replayMedia.some(a=>!a.paused && a.duration===1.2 && a.currentTime>.15));
  await button('暂停回放').click();
  assert(await page.evaluate(()=>window.replayMedia.every(a=>a.paused)));
  const low=await clickAt(.25),high=await clickAt(.75);
  const slope=(high-low)/.5;
  const trace=[];
  for (const [t,reference,strokes] of [[100,0,0],[530,400,1],[850,700,1],[1100,1000,1],
      [1450,1300,0],[1850,1800,1],[2020,1900,1],[2480,2400,1],[2850,2600,1],[850,700,1]]) {
    const actual=await clickAt(.25+(t-low)/slope);
    assert(Math.abs(actual-t)<35,'slider selected '+actual+' ms instead of '+t);
    await page.getByText(new RegExp(strokes+' 笔')).first().waitFor({state:'attached'});
    const png='replay-'+t+'.png';
    await page.screenshot({path:path.join(out,png)});
    trace.push({target:t,actual,reference,png});
  }
  await button('返回编辑').click();
  const unchanged=path.join(out,'replay-unchanged.zip');
  await save(unchanged);
  assert.deepEqual(fs.readFileSync(unchanged),fs.readFileSync(source));
  await page.mouse.move(410,300);await page.mouse.down();await page.mouse.move(540,350,{steps:10});await page.mouse.up();
  await page.getByText(/2 笔/).first().waitFor({state:'attached'});
  await save(path.join(out,'web-page-replay.zip'));
  await button('撤销').click();
  await save(path.join(out,'replay-undone.zip'));
  assert.deepEqual(fs.readFileSync(path.join(out,'replay-undone.zip')),fs.readFileSync(source));
  await open(path.join(out,'web-page-replay.zip'));
  await page.getByText(/2 笔/).first().waitFor({state:'attached'});
  await page.getByRole('button',{name:/第 1 页/}).click();await page.getByRole('menuitem',{name:/第 2 页/}).click();
  assert.equal(await button('播放本页回放').count(),0);
  const result={playedAudio:true,untouchedAndUndoByteEqual:true,editedNotebookReopened:true,trace};
  fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result));
};
