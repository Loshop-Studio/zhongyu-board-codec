const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

module.exports = async (page, directory, output) => {
  const chooser=page.waitForEvent('filechooser');
  await page.getByRole('button',{name:'打开笔记'}).click();
  await (await chooser).setFiles(path.join(directory,'sketch-transform.bin'));
  await page.getByText(/2 笔/).first().waitFor({state:'attached'});

  // Send actual browser touch input; one fingertip lifts before the second.
  const client=await page.context().newCDPSession(page);
  await client.send('Emulation.setTouchEmulationEnabled',{enabled:true,maxTouchPoints:5});
  const touch=async(type,points)=>client.send('Input.dispatchTouchEvent',
    {type,touchPoints:points.map(([id,x,y])=>({id,x,y,radiusX:3,radiusY:3,force:0.7}))});
  await touch('touchStart',[[1,370,320]]);
  await touch('touchStart',[[1,370,320],[2,440,340]]);
  await touch('touchMove',[[1,395,350],[2,465,370]]);
  await touch('touchMove',[[1,410,360],[2,480,380]]);
  await touch('touchEnd',[[2,480,380]]);
  await touch('touchEnd',[]);
  await page.getByText(/2 笔/).first().waitFor({state:'attached'});
  await client.send('Emulation.setTouchEmulationEnabled',{enabled:false});

  await page.getByRole('button',{name:'画板变换'}).click();
  await page.getByRole('menuitem',{name:'放大画板 125%'}).click();
  await page.mouse.move(385,325);
  await page.mouse.down();
  await page.mouse.move(490,370,{steps:8});
  await page.mouse.up();
  await page.getByText(/3 笔/).first().waitFor({state:'attached'});
  await page.getByRole('button',{name:'撤销'}).click();
  await page.getByText(/2 笔/).first().waitFor({state:'attached'});
  await page.getByRole('button',{name:'重做'}).click();
  await page.getByText(/3 笔/).first().waitFor({state:'attached'});
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'导出 BIN'}).click();
  const dest=path.join(output,'web-transform.bin');
  await (await download).saveAs(dest);
  assert(fs.statSync(dest).size>fs.statSync(path.join(directory,'sketch-transform.bin')).size);
  await page.screenshot({path:path.join(output,'web-transform.png')});
  console.log('Two real browser touch contacts, native-format pan and 125% zoom, one new stroke, undo/redo and BIN export.');
};
