const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

module.exports = async (page, dir, out) => {
  const button = name => page.getByRole('button', {name: new RegExp('^' + name + '(?: ' + name + ')?$')});
  const source = path.join(dir, 'camera', 'native.zip');
  async function open(file) {
    const chooser = page.waitForEvent('filechooser');
    await button('打开笔记').click();
    await (await chooser).setFiles(file);
    await page.getByText(/^已导出 /).waitFor({state:'hidden'});
    await page.getByText(/1 笔/).first().waitFor();
  }
  async function save(name) {
    const download = page.waitForEvent('download');
    await button('导出 ZIP').click();
    await (await download).saveAs(path.join(out, name));
  }
  const slider = page.getByRole('group', {name:'回放进度'}).getByRole('slider');
  const label = page.getByText(/^0:\d\d\.\d\d \/ 0:\d\d\.\d\d$/);
  async function clock() {
    const m=(await label.textContent()).match(/^0:(\d+)\.(\d+) \/ 0:(\d+)\.(\d+)$/);
    return [Number(m[1])*1000+Number(m[2])*10,Number(m[3])*1000+Number(m[4])*10];
  }
  async function click(f) {
    const s=await slider.evaluate(el => ({w:el.clientWidth,h:el.clientHeight}));
    await slider.click({position:{x:Math.max(1,Math.min(s.w-1,f*s.w)),y:s.h/2},force:true});
    await page.waitForTimeout(65);
    return (await clock())[0];
  }
  async function seeks(times,prefix) {
    const lo=await click(.25), hi=await click(.75);
    const rows=[];
    for(const target of times) {
      const displayed=await click(.25+(target-lo)/(2*(hi-lo)));
      assert(Math.abs(displayed-target)<30,'seek '+target+' reached '+displayed);
      await page.screenshot({path:path.join(out,prefix+target+'.png')});
      rows.push({target,displayed});
    }
    return rows;
  }
  await open(source);
  const original=await seeks([650,800,1100,1210,1340,1460,1660,2060,2170,2300,2460,1340],'native-');
  await button('返回编辑').click();
  await button('录制页末镜头').click();
  await page.mouse.move(400,405);await page.mouse.down();await page.mouse.move(442,438);
  await page.waitForTimeout(120);await page.mouse.move(521,487);
  await page.waitForTimeout(155);await page.mouse.move(606,535);
  await page.mouse.up();
  await page.getByText('镜头已追加到本页回放',{exact:true}).waitFor();
  const mouseEnd=(await clock())[1];
  await save('mouse.zip');await button('撤销').click();await save('undo.zip');
  assert.deepEqual(fs.readFileSync(source),fs.readFileSync(path.join(out,'undo.zip')));
  await button('重做').click();await open(path.join(out,'mouse.zip'));
  await button('录制页末镜头').click();
  const client=await page.context().newCDPSession(page);
  const touch=(type,points)=>client.send('Input.dispatchTouchEvent',{type,touchPoints:points.map(([id,x,y])=>({id,x,y,radiusX:2,radiusY:2,force:1}))});
  await touch('touchStart',[[1,390,400],[2,520,430]]);
  await touch('touchMove',[[1,381,399],[2,532,436]]);
  await page.waitForTimeout(118);
  await touch('touchMove',[[1,362,392],[2,552,445]]);
  await page.waitForTimeout(137);
  await touch('touchMove',[[1,344,405],[2,584,459]]);
  await page.screenshot({path:path.join(out,'pinch-live.png')});
  await touch('touchEnd',[]);
  await page.getByText('镜头已追加到本页回放',{exact:true}).waitFor();
  await save('web.zip');await open(path.join(out,'web.zip'));
  const total=(await clock())[1];
  const edited=await seeks([2300,mouseEnd-285,total-285,total,1340],'edited-');
  await button('返回编辑').click();
  await save('reopened.zip');
  assert.deepEqual(fs.readFileSync(path.join(out,'web.zip')),fs.readFileSync(path.join(out,'reopened.zip')));
  await open(source);
  await touch('touchStart',[[1,410,410],[2,510,440]]);
  await touch('touchMove',[[1,417,417],[2,551,453]]);
  await page.waitForTimeout(95);
  await touch('touchMove',[[1,415,424],[2,590,477]]);
  await touch('touchEnd',[]);
  await page.getByText('镜头已追加到本页回放',{exact:true}).waitFor();
  await page.getByText(/1 笔/).first().waitFor();
  await save('writing.zip');
  await button('撤销').click();await save('pen-undo.zip');
  assert.deepEqual(fs.readFileSync(source),fs.readFileSync(path.join(out,'pen-undo.zip')));
  await open(source);
  await touch('touchStart',[[1,360,360]]);
  await page.waitForTimeout(100);
  await touch('touchMove',[[1,385,370]]);
  await touch('touchStart',[[1,385,370],[2,485,410]]);
  await touch('touchMove',[[1,405,389],[2,520,426]]);
  await page.waitForTimeout(80);
  await touch('touchMove',[[1,420,405],[2,545,439]]);
  await touch('touchEnd',[]);
  await page.getByText(/2 笔/).first().waitFor();
  await save('late-second-touch.zip');
  await open(source);
  await button('录制页末镜头').click();
  await touch('touchStart',[[1,380,380],[2,500,410]]);
  await touch('touchMove',[[1,351,383],[2,527,445]]);
  await touch('touchCancel',[]);
  await save('cancelled.zip');
  assert.deepEqual(fs.readFileSync(source),fs.readFileSync(path.join(out,'cancelled.zip')));
  fs.writeFileSync(path.join(out,'trace.json'),JSON.stringify({original,edited,total},null,2));
  console.log('Replayed recorded native pan and pinch, recorded mouse and two-finger camera motion, undid, redid and reopened the export.');
};
