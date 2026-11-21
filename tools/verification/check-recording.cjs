const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

module.exports = async (page, directory, output) => {
  const recording = path.join(directory,'sketch-recording.zip');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button',{name:'打开笔记'}).click();
  await (await chooser).setFiles(recording);
  const play = page.getByRole('button',{name:'播放录制'});
  await play.waitFor();
  await page.evaluate(() => {
    const original = HTMLMediaElement.prototype.play;
    window.recordedMedia = [];
    HTMLMediaElement.prototype.play = function (...args) {
      if (!window.recordedMedia.includes(this)) window.recordedMedia.push(this);
      return original.apply(this,args);
    };
  });
  await play.click();
  await page.waitForFunction(() => window.recordedMedia[0]?.currentTime > 0.10);
  await page.getByRole('button',{name:'暂停回放'}).click();
  const paused = await page.evaluate(() => window.recordedMedia[0].currentTime);
  assert(await page.evaluate(() => window.recordedMedia[0].paused));
  const slider = page.getByRole('group',{name:'回放进度'}).getByRole('slider');
  const box = await slider.boundingBox({timeout:4500});
  assert(box);
  // Pick the second segment, then check that decoded audio starts inside clip 2.
  await page.mouse.click(box.x+box.width*.8,box.y+box.height/2);
  await play.click();
  await page.waitForFunction(() => window.recordedMedia.some(el => Math.abs(el.duration - 0.8)<0.01 && !el.paused && el.currentTime>0.18));
  await page.getByText('0:02.00 / 0:02.00',{exact:true}).waitFor({state:'attached'});
  const media = await page.evaluate(() => window.recordedMedia.map(el=>({duration:el.duration,readyState:el.readyState,ended:el.ended})));
  assert(media.some(x=>Math.abs(x.duration-1.2)<0.01));
  assert(media.some(x=>Math.abs(x.duration-0.8)<0.01));
  await page.screenshot({path:path.join(output,'recording-preview.png')});
  await page.getByRole('button',{name:'返回编辑'}).click();
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'导出 ZIP'}).click();
  const destination=path.join(output,'recording-export.zip');
  await (await download).saveAs(destination);
  assert.deepEqual(fs.readFileSync(destination),fs.readFileSync(recording));
  await page.mouse.move(365,300);
  await page.mouse.down();
  await page.mouse.move(545,370,{steps:12});
  await page.mouse.up();
  await page.getByText(/2 笔/).first().waitFor({state:'attached'});
  const edited = page.waitForEvent('download');
  await page.getByRole('button',{name:'导出 ZIP'}).click();
  await (await edited).saveAs(path.join(output,'recording-edited.zip'));
  console.log(JSON.stringify({durationMs:2000,pausedFirstAt:paused,decodedClips:media,untouchedArchiveByteEqual:true,editedStrokes:2}));
};
