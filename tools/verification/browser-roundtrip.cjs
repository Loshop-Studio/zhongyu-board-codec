const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const http=require('node:http'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve('board_editor/build/web');
const server=http.createServer((req,res)=>{
 const file=path.join(root,decodeURIComponent(new URL(req.url,'http://localhost').pathname).replace(/^\/$/,'index.html'));
 if(!file.startsWith(root+'/')||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404).end();return}
 const mime={'.html':'text/html','.js':'application/javascript','.wasm':'application/wasm','.json':'application/json','.ttf':'font/ttf','.otf':'font/otf'};
 res.setHeader('Content-Type',mime[path.extname(file)]||'application/octet-stream');fs.createReadStream(file).pipe(res);
});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_BIN || undefined,args:['--no-sandbox','--disable-dev-shm-usage']});
 try {
 const ctx=await browser.newContext({viewport:{width:1000,height:750}});const p=await ctx.newPage();
 p.on('pageerror',e=>console.error(String(e)));
 await p.goto('http://127.0.0.1:'+server.address().port);
 await p.locator('flt-glass-pane,flt-flutter-view,flutter-view').first().waitFor({state:'attached',timeout:45000});
 const sem=p.locator('flt-semantics-placeholder'); if(await sem.count()) await sem.evaluate(el=>el.click());
 await p.getByRole('button',{name:'导出 BIN'}).waitFor({timeout:20000});
 const dir=path.resolve('reports/evidence/board');
 const outputDir=process.env.BOARD_OUTPUT || fs.mkdtempSync(path.join(require('node:os').tmpdir(),'zy-board-'));
 console.log('Browser output',outputDir);
 if(process.argv.includes('--simple-eraser')) {await require('./check-simple-eraser.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--sketch-backing')) {await require('./check-sketch-backing.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--sketch-shapes')) {await require('./check-sketch-shapes.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--sketch-thumbnail')) {await require('./check-sketch-thumbnail.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--cloud-mdb')) {await require('./check-cloud-mdb.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--cloud-index')) {await require('./check-cloud-index.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--page-camera')) {await require('./check-page-camera.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--page-cursor')) {await require('./check-page-cursor.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--ruled-paper')) {await require('./check-ruled-paper.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--note-folder-test')) {await require('./check-note-folder.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--new-note-test')) {await require('./check-new-notebook.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--artwork-create-test')) {await require('./check-artwork-create.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--page-image-test')) {await require('./check-page-image.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--page-image-preview')) {await require('./check-page-image.cjs')(p,dir,outputDir,'preview');return;}
 if(process.argv.includes('--page-image-touch')) {await require('./check-page-image.cjs')(p,dir,outputDir,'touch');return;}
 if(process.argv.includes('--artwork-edit-test')) {await require('./check-artwork-edit.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--presentation-writer-test')) {await require('./check-presentations.cjs')(p,dir,outputDir,true);return;}
 if(process.argv.includes('--presentation-test')) {await require('./check-presentations.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--image-test')) {await require('./check-images.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--transform-test')) {await require('./check-transform.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--native-v6-returned')) {await require('./check-native-v6.cjs')(p,dir,outputDir,true);return;}
 if(process.argv.includes('--native-v6-test')) {await require('./check-native-v6.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--page-replay-test')) {await require('./check-page-replay.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--page-audio-test')) {await require('./check-page-audio.cjs')(p,dir,outputDir);return;}
 if(process.argv.includes('--recording-test')) {await require('./check-recording.cjs')(p,dir,outputDir);return;}
 const draw=async()=>{await p.mouse.move(360,300);await p.mouse.down();await p.mouse.move(540,370,{steps:14});await p.mouse.up();};
 if(process.argv.includes('--cloud-note-test')) {
   const chooser=p.waitForEvent('filechooser');
   await p.getByRole('button',{name:'打开笔记'}).click();
   await (await chooser).setFiles(path.join(dir,'cloud-mixed.zip'));
   await p.getByRole('button',{name:'打开旧 BIN 页面'}).click();
   await p.getByText(/0 笔/).first().waitFor({state:'attached'});
   await draw();
   await p.getByText(/1 笔/).first().waitFor({state:'attached'});
   const download=p.waitForEvent('download');
   await p.getByRole('button',{name:'按页面 BIN 导出云笔记副本'}).click();
   const result=await download;
   if(result.suggestedFilename()!=='cloud-mixed-云笔记.zip') throw new Error(result.suggestedFilename());
   await result.saveAs(path.join(outputDir,'web-cloud-note.zip'));
   console.log('Imported mixed page_mdb + BIN fixture, added one stroke, exported '+result.suggestedFilename());
   return;
 }
 const cases=process.argv.includes('--native-background-only') ? [['native-simple-page.zip','SimpleBoard',3,4,'web-native-page.zip']] : process.argv.includes('--native-return-only') ? [['native-edited.bin','SimpleBoard',3,4,'web-return.bin']] : [['art-simple.bin','SimpleBoard',1,2,'web-simple.bin'],['art-actions.bin','Sketch',1,2,'web-sketch.bin'],['schema-page.zip','Blackboard 页面',0,1,'web-page.zip'],['schema-artwork.zip','Blackboard 页面',0,1,'web-artwork.zip']];
 for(const [input,kind,before,after,output] of cases){
   const fc=p.waitForEvent('filechooser');await p.getByRole('button',{name:'打开笔记'}).click();await(await fc).setFiles(dir+'/'+input);
   await p.getByText(new RegExp(kind+'$')).first().waitFor({state:'attached'});
   await p.getByText(new RegExp(before+' 笔')).first().waitFor({state:'attached'});
   if(input==='native-simple-page.zip') {
     await p.getByRole('button',{name:'设置原生画布宽度'}).click();
     await p.getByRole('textbox').fill('320');
     await p.getByRole('button',{name:'应用',exact:true}).click();
     await p.getByText(/320 × 240/).first().waitFor({state:'attached'});
   }
   await draw();
   await p.getByText(new RegExp(after+' 笔')).first().waitFor({state:'attached'});
   const dl=p.waitForEvent('download');await p.getByRole('button',{name:input.endsWith('.zip')?'导出 ZIP':'导出 BIN'}).click();await(await dl).saveAs(outputDir+'/'+output);
   if(input==='art-simple.bin') await p.screenshot({path:outputDir+'/browser.png'});
   if(input==='native-simple-page.zip') await p.screenshot({path:outputDir+'/native-background-web.png'});
   if(input==='schema-artwork.zip') {await p.screenshot({path:outputDir+'/artwork.png'});}
   console.log(input,kind,before,'->',after,output,fs.statSync(outputDir+'/'+output).size);
 }
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
