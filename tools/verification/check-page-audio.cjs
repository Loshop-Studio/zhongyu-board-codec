const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');

module.exports = async (page, dir, output) => {
  const source = path.join(dir, 'page-audio.zip');
  const button = (name) => page.getByRole('button', {name: new RegExp('^'+name+'(?: '+name+')?$')});
  async function pick(name, payload) {
    const chooser = page.waitForEvent('filechooser');
    await button(name).click();
    await (await chooser).setFiles(payload);
  }
  async function save(label, file) {
    const download = page.waitForEvent('download');
    await button(label).click();
    const dest = path.join(output, file);
    await (await download).saveAs(dest);
    return dest;
  }
  async function at(fraction) {
    const slider = page.getByRole('group',{name:'本页录音进度'}).getByRole('slider');
    const box = await slider.boundingBox();
    assert(box);
    // Flutter's slider keeps 24 logical pixels on each side of the track.
    await page.mouse.click(box.x+24+(box.width-48)*fraction,box.y+box.height/2);
  }
  await page.evaluate(() => {
    window.audioPlays = [];
    const original = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function(...args) {
      window.audioPlays.push(this);
      return original.apply(this,args);
    };
  });
  await pick('打开笔记',source);
  async function listenOnly() {
    const toggle=button('只听录音');
    await page.getByRole('button',{name:/播放本页/}).first().waitFor();
    if(await toggle.count()) await toggle.click();
  }
  await listenOnly();
  const play=button('播放本页录音'), pause=button('暂停本页录音');
  await play.click();
  await page.waitForFunction(()=>window.audioPlays.some(a=>a.duration===1.2 && a.currentTime>0.1 && !a.paused));
  await pause.click();
  assert(await page.evaluate(()=>window.audioPlays.every(a=>a.paused)));
  await at(.77);
  await play.click();
  await page.waitForFunction(()=>window.audioPlays.some(a=>a.duration===0.8 && a.currentTime>0.12 && !a.paused));
  await pause.click();
  await button('停止试听').click();
  const unchanged=await save('导出 ZIP','page-audio-unchanged.zip');
  assert.deepEqual(fs.readFileSync(unchanged),fs.readFileSync(source));
  const sound=execFileSync('unzip',['-p',source,'lesson/res/audio/first.wav']);
  await pick('追加本页录音',{name:'first.wav',mimeType:'audio/wav',buffer:sound});
  const gap=page.getByRole('textbox',{name:'页末静音间隔（毫秒）'});
  await gap.click();
  await page.keyboard.press('Control+a');
  await page.keyboard.insertText('100');
  await page.keyboard.press('Tab');
  await button('追加').click();
  await page.getByText('已追加录音 first-2.wav',{exact:true}).waitFor({state:'attached'});
  await button('撤销').click();
  const undone=await save('导出 ZIP','page-audio-undo.zip');
  assert.deepEqual(fs.readFileSync(undone),fs.readFileSync(source));
  await button('重做').click();
  const edited=await save('导出 ZIP','web-page-audio.zip');
  await save('按页面 BIN 导出云笔记副本','web-page-audio-cloud.zip');
  await pick('打开笔记',edited);
  await page.getByText('0:00.00 / 0:04.10',{exact:true}).waitFor({state:'attached'});
  await listenOnly();
  await at(.81);
  const earlier=await page.evaluate(()=>window.audioPlays.length);
  await play.click();
  await page.waitForFunction(n=>window.audioPlays.slice(n).some(a=>a.duration===1.2 && !a.paused && a.currentTime>.15),earlier);
  await pause.click();
  const media=await page.evaluate(()=>window.audioPlays.filter(a=>Number.isFinite(a.duration)).map(a=>({seconds:a.duration,offset:a.currentTime,paused:a.paused})));
  await page.screenshot({path:path.join(output,'page-audio-browser.png')});
  await page.getByRole('button',{name:/第 1 页/}).click();
  await page.getByRole('menuitem',{name:/第 2 页/}).click();
  await page.getByText(/p2\/snapshot.bin/).first().waitFor({state:'attached'});
  assert.equal(await play.count(),0);
  await pick('打开笔记',path.join(dir,'page-audio-split.zip'));
  await page.getByText('0:00.00 / 0:02.80',{exact:true}).waitFor({state:'attached'});
  await listenOnly();
  await at(.77);
  const previousCount=await page.evaluate(()=>window.audioPlays.length);
  await play.click();
  await page.waitForFunction(n=>window.audioPlays.slice(n).some(a=>a.duration===0.8 && a.currentTime>.12 && !a.paused),previousCount);
  await pause.click();
  console.log(JSON.stringify({pageDurationMs:4100,appendedMs:1200,gapMs:100,reopened:true,
    splitSecondShardSeek:true,untouchedAndUndoByteEqual:true,secondPageHasNoTrack:true,decoded:media}));
};
