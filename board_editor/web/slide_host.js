/* Render a selected local Sketch HTML entry in an opaque-origin iframe. Only the
 * parent resolves relative courseware assets. The child can report slide
 * numbers and receives the five presentation operations used by Android. */
(() => {
  'use strict';
  const sessions = new WeakMap();
  const decoder = new TextDecoder();
  const types = {css:'text/css',js:'text/javascript',png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',
    gif:'image/gif',svg:'image/svg+xml',webp:'image/webp',bmp:'image/bmp',avif:'image/avif',
    woff:'font/woff',woff2:'font/woff2',ttf:'font/ttf',otf:'font/otf',mp3:'audio/mpeg',
    wav:'audio/wav',ogg:'audio/ogg',m4a:'audio/mp4',mp4:'video/mp4',webm:'video/webm'};
  function resolve(file, ref) {
    if (!ref || /^(?:[a-z][\w+.-]*:|[\/\\#])/i.test(ref)) return null;
    try {
      const parts = file.split('/').slice(0,-1);
      for (const piece of decodeURIComponent(ref.split(/[?#]/)[0]).split('/')) {
        if (!piece || piece === '.') continue;
        if (piece === '..') { if (!parts.length) return null; parts.pop(); }
        else { if (/[\\:\0]/.test(piece)) return null; parts.push(piece); }
      }
      return parts.join('/');
    } catch (_) { return null; }
  }

  function asData(type, bytes) {
    let binary='';
    for (let i=0;i<bytes.length;i+=16384) binary+=String.fromCharCode(...bytes.subarray(i,i+16384));
    return 'data:'+type+';base64,'+btoa(binary);
  }

  // This function is serialized into the sandboxed document, before its own scripts.
  function slideBridge() {
    let current=0,total=0;
    function notify() { parent.postMessage({zySlide:true,current,total},'*'); }
    window.SlideNative={
      setCurrentSlide(n){ if(Number.isInteger(n)){current=n;notify();} },
      setTotalCount(n){ if(Number.isInteger(n)){total=n;notify();} }
    };
    addEventListener('message',event=>{
      if(event.source!==parent || !event.data || event.data.zySlideCommand!==true)return;
      const api=window.Presentation;
      if(!api)return;
      const name=event.data.name;
      if(name==='GotoSlide' && Number.isInteger(event.data.page))api.GotoSlide?.(String(event.data.page));
      if(['Next','Prev','NxtSlide','PrvSlide'].includes(name))api[name]?.();
    });
    addEventListener('load',notify);
  }

  function documentFor(entry, read) {
    const input=read(entry);
    if(!input)throw new Error('找不到课件入口');
    const doc=document.implementation.createHTMLDocument('');
    doc.documentElement.innerHTML=decoder.decode(input);
    doc.querySelectorAll('base,iframe,frame,frameset,object,embed,portal,meta[http-equiv],link:not([rel~="stylesheet"])').forEach(n=>n.remove());
    const cache=new Map();
    function asset(file,ref) {
      if (/^(?:data:(?:image|font|audio|video)\/|#)/i.test(ref))return ref;
      const path=resolve(file,ref);
      if(!path)return '';
      if(cache.has(path))return cache.get(path);
      const type=types[path.split('.').pop().toLowerCase()];
      if(!type)return '';
      const bytes=read(path);
      if(!bytes)return '';
      cache.set(path,''); // break recursive CSS imports
      const content=type==='text/css'?new TextEncoder().encode(css(path,decoder.decode(bytes))):bytes;
      const value=asData(type,content);
      cache.set(path,value);
      return value;
    }
    function css(file, style) {
      return style.replace(/@import\s+(['"])([^'"]+)\1/gi,(_,q,url)=>'@import url("'+asset(file,url)+'")')
        .replace(/url\(\s*(['"]?)([^\s)'"]+)\1\s*\)/gi,(match,q,url)=>
          url.startsWith('data:text/css;base64,')?match:'url("'+asset(file,url)+'")');
    }
    for (const el of doc.querySelectorAll('*')) {
      if(el.hasAttribute('src')) {
        const value=asset(entry,el.getAttribute('src'));
        if(value)el.setAttribute('src',value);else if(el.localName==='script'){el.remove();continue;}
        else el.removeAttribute('src');
      }
      if(el.hasAttribute('href') || el.hasAttribute('xlink:href')) {
        const attr=el.hasAttribute('href')?'href':'xlink:href';
        const original=el.getAttribute(attr);
        const value=el.localName==='link' || el.namespaceURI==='http://www.w3.org/2000/svg' ?
          asset(entry,original) : (original.startsWith('#')?original:'');
        if(value)el.setAttribute(attr,value);else el.removeAttribute(attr);
      }
      el.removeAttribute('srcset');el.removeAttribute('action');el.removeAttribute('formaction');
      if(el.hasAttribute('poster'))el.setAttribute('poster',asset(entry,el.getAttribute('poster')));
      if(el.hasAttribute('style'))el.setAttribute('style',css(entry,el.getAttribute('style')));
      if(el.localName==='style')el.textContent=css(entry,el.textContent);
    }
    const policy=doc.createElement('meta');
    policy.httpEquiv='Content-Security-Policy';
    policy.content="default-src 'none'; script-src 'unsafe-inline' data:; style-src 'unsafe-inline' data:; img-src data:; font-src data:; media-src data:; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'";
    const bridge=doc.createElement('script');
    bridge.textContent='('+slideBridge.toString()+')();';
    doc.head.prepend(policy,bridge);
    return '<!doctype html>'+doc.documentElement.outerHTML;
  }

  window.zyMountSlides=(frame,entry,read,report)=>{
    const listener=event=>{
      if(event.source!==frame.contentWindow || !event.data || event.data.zySlide!==true)return;
      const {current,total}=event.data;
      if(Number.isSafeInteger(current)&&Number.isSafeInteger(total)&&current>=0&&total>=0)
        report(current,total);
    };
    frame.setAttribute('sandbox','allow-scripts');
    frame.setAttribute('referrerpolicy','no-referrer');
    frame.title=entry;frame.tabIndex=-1;
    frame.style.cssText='border:0;pointer-events:none;display:block;width:100%;height:100%';
    frame.srcdoc=documentFor(entry,read);
    sessions.set(frame,listener);window.addEventListener('message',listener);
  };
  window.zyUnmountSlides=frame=>{
    const listener=sessions.get(frame);
    if(listener)window.removeEventListener('message',listener);
    sessions.delete(frame);
  };
  window.zyControlSlides=(frame,name,page)=>frame.contentWindow?.postMessage({zySlideCommand:true,name,page},'*');
})();
