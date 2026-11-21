const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

module.exports = async (page, dir, out) => {
  const source = path.join(dir,'cursor','native.zip');
  const button = name => page.getByRole('button',{name:new RegExp('^'+name+'(?: '+name+')?$')});
  const slider = page.getByRole('group',{name:'回放进度'}).getByRole('slider');
  const stamp = page.getByText(/^0:\d\d\.\d\d \/ 0:\d\d\.\d\d$/);
  async function open(file){
    const chooser = page.waitForEvent('filechooser');
    await button('打开笔记').click();
    await (await chooser).setFiles(file);
    await page.getByText(/^已导出 /).waitFor({state:'hidden'});
    await page.getByText(/1 笔/).first().waitFor();
  }
  async function save(file){
    const download=page.waitForEvent('download');
    await button('导出 ZIP').click();
    await (await download).saveAs(path.join(out,file));
  }
  async function times(){
    const m=(await stamp.textContent()).match(/^0:(\d+)\.(\d+) \/ 0:(\d+)\.(\d+)$/);
    return [Number(m[1])*1000+Number(m[2])*10, Number(m[3])*1000+Number(m[4])*10];
  }
  async function click(fraction){
    await slider.waitFor({state:'visible'});
    const size=await slider.evaluate(el => ({w:el.clientWidth,h:el.clientHeight}));
    await slider.click({position:{x:Math.max(1,Math.min(size.w-1,fraction*size.w)),y:size.h/2},force:true});
    await page.waitForTimeout(70);
    return (await times())[0];
  }
  async function seeks(list, prefix){
    const low=await click(.25), high=await click(.75);
    const result=[];
    for(const t of list){
      const actual=await click(.25+(t-low)/((high-low)*2));
      assert(Math.abs(actual-t)<27,[t,actual]);
      await page.getByText(/1 笔/).first().waitFor();
      await page.screenshot({path:path.join(out,prefix+t+'.png')});
      result.push({target:t, displayed:actual});
    }
    return result;
  }
  async function checkEnd(){
    await click(.80);
    await button('播放本页回放').click();
    await button('暂停回放').waitFor();
    await button('播放本页回放').waitFor();
    const [position,duration]=await times();
    assert.equal(position,duration);
    await page.screenshot({path:path.join(out,'ended.png')});
  }
  if(process.env.V6_CURSOR_REOPEN){
    await open(process.env.V6_CURSOR_REOPEN);
    await checkEnd();
    return;
  }
  await open(source);
  // Freeze the animation during the native finger interval and verify the
  // timestamp stays fixed while paused.
  await seeks([850], 'seek-');
  await button('播放本页回放').click();
  await page.waitForTimeout(100);
  await button('暂停回放').click();
  const frozen=await times();
  await page.waitForTimeout(140);
  assert.deepEqual(await times(),frozen);
  const trace=await seeks([700,850,970,1095,1200,1450,1560,1670,1820,2011,970],'seek-');
  await button('返回编辑').click();
  await save('original.zip');
  assert.deepEqual(fs.readFileSync(source), fs.readFileSync(path.join(out,'original.zip')));
  await button('录制页末光标').click();
  await page.mouse.move(355,457);await page.mouse.down();
  await page.waitForTimeout(130);
  await page.mouse.move(425,418);
  await page.screenshot({path:path.join(out,'mouse-live.png')});
  await page.waitForTimeout(240);await page.mouse.move(495,476);
  await page.waitForTimeout(120);await page.mouse.up();
  await page.getByText('光标已追加到本页回放',{exact:true}).waitFor();
  const mouseEnd=(await times())[1];
  await save('mouse.zip');
  await button('撤销').click();
  await save('undone.zip');
  assert.deepEqual(fs.readFileSync(source),fs.readFileSync(path.join(out,'undone.zip')));
  await button('重做').click();
  await page.getByText(/1 笔/).first().waitFor();
  assert.equal((await times())[1],mouseEnd);
  await open(path.join(out,'mouse.zip'));
  await button('录制页末光标').click();
  const client=await page.context().newCDPSession(page);
  const touch=(type,points)=>client.send('Input.dispatchTouchEvent',{type,touchPoints:points.map(([x,y])=>({x,y,id:1}))});
  const contact=(x,y,id)=>({x,y,id});
  const multi=(type,touchPoints)=>client.send('Input.dispatchTouchEvent',{type,touchPoints});
  await multi('touchStart',[contact(405,470,1)]);
  await multi('touchStart',[contact(405,470,1),contact(463,497,2)]);
  await multi('touchStart',[contact(405,470,1),contact(463,497,2),contact(490,503,3)]);
  await multi('touchEnd',[]);
  assert.equal((await times())[1],mouseEnd);
  await save('cancelled.zip');
  assert.deepEqual(fs.readFileSync(path.join(out,'mouse.zip')),fs.readFileSync(path.join(out,'cancelled.zip')));
  await touch('touchStart',[[410,480]]);
  await page.waitForTimeout(120);await touch('touchMove',[[450,495]]);
  await page.screenshot({path:path.join(out,'finger-live.png')});
  await page.waitForTimeout(240);await touch('touchMove',[[488,515]]);
  await page.waitForTimeout(120);await touch('touchEnd',[]);
  await page.getByText('光标已追加到本页回放',{exact:true}).waitFor();
  await save('web.zip');
  await open(path.join(out,'web.zip'));
  await page.getByText('光标已追加到本页回放',{exact:true}).waitFor({state:'hidden'});
  const final=(await times())[1];
  assert(mouseEnd>2420 && final-mouseEnd>420,{mouseEnd,final});
  const targets=[Math.round((2011+mouseEnd)/2),Math.round((mouseEnd+final)/2),final,970];
  const edited=await seeks(targets,'edited-');
  await checkEnd();
  fs.writeFileSync(path.join(out,'trace.json'),JSON.stringify({trace,frozen,mouseEnd,final,edited},null,2));
  console.log('Native cursor playback, pause, backward seek, mouse and finger recording, undo/redo and file reopen passed.');
};
