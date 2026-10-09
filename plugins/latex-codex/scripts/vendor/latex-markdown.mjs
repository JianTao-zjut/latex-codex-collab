import {Marked, Lexer} from './marked.mjs';
import DOMPurify from './purify.mjs';
import katex from './katex/katex.mjs';

const escape = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const imageUrl = href => /^https?:\/\//i.test(href) ? href : '/markdown-resource?path=' + encodeURIComponent(href);

// Marked handles fenced/inline code before math; source offsets belong to whole rendered blocks.
export function markdownHtml(source, sanitizeHtml = escape) {
  source = source.replace(/\r\n?/g, '\n');
  const macros = {}, slugs = new Map();
  const math = (text, displayMode) => katex.renderToString(text.replace(/^\\\(([\s\S]*)\\\)$/, '$1'), {
    displayMode, throwOnError:false, strict:'ignore', trust:false, macros, globalGroup:true,
  });
  const markdown = new Marked({gfm:true}, {
    tokenizer: {
      lheading(src) {
        const match = this.rules.block.lheading.exec(src);
        // An '=' row inside display math must never turn preceding prose into a Setext heading.
        if(match && /(?:^|\n) {0,3}(?:\$\$|\\\[)/.test(match[0]))return;
        return false;
      },
    },
    renderer: {
      html({text}) { return sanitizeHtml(text); },
      heading({tokens, text, depth}) {
        const base = text.toLowerCase().replace(/[^\p{L}\p{N}_-]+/gu, '-').replace(/^-|-$/g, '') || 'heading';
        const count = slugs.get(base) || 0; slugs.set(base, count + 1);
        return `<h${depth} id="markdown-heading-${escape(base + (count ? '-' + count : ''))}">${this.parser.parseInline(tokens)}</h${depth}>`;
      },
      link({href, title, tokens}) {
        if(href.startsWith('#'))href='#markdown-heading-'+href.slice(1);
        return `<a href="${escape(href)}"${title ? ` title="${escape(title)}"` : ''}>${this.parser.parseInline(tokens)}</a>`;
      },
      image({href, text, title}) {
        return `<img src="${escape(imageUrl(href))}" alt="${escape(text)}"${title ? ` title="${escape(title)}"` : ''} loading="lazy" referrerpolicy="no-referrer">`;
      },
    },
    extensions: [
      {name:'blockMath', level:'block', start:src=>src.search(/\$\$|\\\[/),
        tokenizer(src) {
          const match = /^(?: {0,3}\$\$([\s\S]+?)\$\$| {0,3}\\\[([\s\S]+?)\\\])[ \t]*(?:\n|$)/.exec(src);
          if (match) return {type:'blockMath', raw:match[0], text:(match[1] ?? match[2]).trim()};
        }, renderer:token=>math(token.text,true)},
      {name:'inlineMath', level:'inline', start:src=>src.search(/\$|\\\(/),
        tokenizer(src) {
          const match = /^(?:\$(?![\s$])((?:\\.|[^\\$\n])+?)\$(?!\d)|\\\(([^\n]*?)\\\))/.exec(src);
          if (match && (match[1] == null || match[1].trim() === match[1])) return {type:'inlineMath', raw:match[0], text:match[1] ?? match[2]};
        }, renderer:token=>math(token.text,false)},
      {name:'wikiImage', level:'inline', start:src=>src.indexOf('![['),
        tokenizer(src) {
          const match = /^!\[\[([^\]\n]+)\]\]/.exec(src);
          if (match) return {type:'wikiImage', raw:match[0], text:match[1]};
        }, renderer(token) {
          const [href, size] = token.text.split('|'), width = /^\d+(?:x\d+)?$/.test(size || '') ? Math.min(1200,Number(size.split('x')[0])) : null;
          return `<img src="${escape(imageUrl(href))}" alt="${escape(href)}"${width ? ` width="${width}"` : ''} loading="lazy" referrerpolicy="no-referrer">`;
        }},
    ],
  });
  const tokens = markdown.lexer(source);
  let offset = 0;
  return tokens.map(token => {
    const from = offset; offset += token.raw.length;
    const block = [token]; block.links = tokens.links;
    return `<div class="markdown-block" data-source-from="${from}" data-source-to="${offset}">${markdown.parser(block,markdown.defaults)}</div>`;
  }).join('');
}

// Keep character origins while projecting inline Markdown to visible prose.
// Unsupported HTML/images are barriers rather than guessed source positions.
export function markdownSelectionRange(source, from, to, selected) {
  const raw=source.slice(from,to), chars=[], spans=[], wrappers=[];
  function append(text,start,end) {
    for(let i=0;i<text.length;i++){chars.push(text[i]);spans.push([start+i,Math.min(end,start+i+1)]);}
  }
  function walk(tokens,base) {
    let cursor=base;
    for(const token of tokens){
      const start=cursor,end=start+token.raw.length;cursor=end;
      if(token.tokens){
        const inner=token.tokens.map(item=>item.raw).join(''),offset=token.raw.indexOf(inner);
        if(offset<0){append('\u0000',start,end);continue;}
        const a=start+offset,b=a+inner.length;
        wrappers.push({start,end,a,b});walk(token.tokens,a);
      }else if(token.type==='text'&&token.text===token.raw)append(token.raw,start,end);
      else if(token.type==='escape')append(token.text,end-token.text.length,end);
      else if(token.type==='codespan'&&token.raw.includes(token.text)){
        const a=start+token.raw.indexOf(token.text);wrappers.push({start,end,a,b:a+token.text.length});append(token.text,a,a+token.text.length);
      }else if(token.type==='br')append(' ',start,end);
      else append('\u0000',start,end);
    }
  }
  walk(Lexer.lexInline(raw,{gfm:true}),from);
  // Normalize whitespace without losing original source boundaries.
  let visible='';const positions=[];
  for(let i=0;i<chars.length;i++){
    const char=/\s/u.test(chars[i])?' ':chars[i];
    if(char===' '&&visible.endsWith(' ')){positions.at(-1)[1]=spans[i][1];continue;}
    visible+=char;positions.push([...spans[i]]);
  }
  const needle=selected.replace(/\s+/gu,' ').trim();
  if(!needle)return null;
  const index=visible.indexOf(needle);
  if(index<0||visible.indexOf(needle,index+1)>=0)return null;
  let a=positions[index][0],b=positions[index+needle.length-1][1];
  // Crossing a formatting edge includes its whole wrapper, preserving valid Markdown.
  for(let changed=true;changed;){changed=false;for(const w of wrappers){
    if(a<w.b&&b>w.a&&((a<=w.a&&b>=w.b)||(a<w.a&&b>w.a)||(a<w.b&&b>w.b))){
      const nextA=Math.min(a,w.start),nextB=Math.max(b,w.end);
      if(nextA!==a||nextB!==b){a=nextA;b=nextB;changed=true;}
    }
  }}
  return {from:a,to:b};
}

export function attachMarkdownPreview(container, editor) {
  let current = null;
  const document=container.ownerDocument,menu=document.createElement('div'),action=document.createElement('button');
  const note=document.createElement('button');note.type='button';note.textContent='添加文字注释';note.setAttribute('role','menuitem');
  menu.id='markdown-selection-menu';menu.setAttribute('popover','auto');menu.setAttribute('role','menu');
  action.type='button';action.setAttribute('role','menuitem');menu.append(action,note);document.body.append(menu);
  let pending=null;
  const message=()=>{const status=document.querySelector('#status');if(status)status.textContent='无法准确定位选区，请缩小选区或在源码中添加批注。';};
  container.addEventListener('contextmenu',event=>{
    if(container.hidden||event.shiftKey||editor.getOption('readOnly'))return;
    const selected=document.defaultView.getSelection();
    const object=event.target.closest('img,table'),block=object?.closest('.markdown-block');
    if(!block&&(!selected||selected.isCollapsed||!container.contains(selected.anchorNode)||!container.contains(selected.focusNode)))return;
    note.hidden=!['owner','editor'].includes(document.body.dataset.collaborationRole);
    if(block&&note.hidden)return;
    event.preventDefault();
    pending=block&&current===editor.getValue()?{from:Number(block.dataset.sourceFrom),to:Number(block.dataset.sourceTo),source:current,doc:editor.getDoc(),bounds:object.getBoundingClientRect()}:api.selection(selected);
    if(!pending){menu.hidePopover();message();return;}
    action.hidden=!!block;
    action.textContent=document.querySelector('#chat-quick-menu')?.textContent||'添加批注';
    menu.showPopover();
    const box=event.clientX===0&&event.clientY===0?pending.bounds:{left:event.clientX,bottom:event.clientY};
    menu.style.left=Math.max(8,Math.min(box.left,document.defaultView.innerWidth-menu.offsetWidth-8))+'px';
    menu.style.top=Math.max(8,Math.min(box.bottom,document.defaultView.innerHeight-menu.offsetHeight-8))+'px';action.focus();
  });
  action.onclick=()=>{
    const selected=pending;pending=null;menu.hidePopover();
    if(!selected||container.hidden||editor.getOption('readOnly'))return;
    if(selected.doc!==editor.getDoc()||selected.source!==editor.getValue()){message();return;}
    const entry=document.querySelector('#chat-quick-menu');if(!entry)return;
    const from=editor.posFromIndex(selected.from),to=editor.posFromIndex(selected.to);
    editor.setSelection(from,to);editor.scrollIntoView({from,to},80);
    // Reuse the existing composer and its draft, permission and request guards.
    entry.click();
  };
  note.onclick=()=>{
    const selected=pending;pending=null;menu.hidePopover();
    if(!selected||container.hidden||editor.getOption('readOnly'))return;
    document.dispatchEvent(new CustomEvent('latex-text-comment',{detail:selected}));
  };
  container.addEventListener('scroll',()=>menu.hidePopover());
  function render(source) {
    if (source === current) return;
    pending=null;menu.hidePopover();
    current = source;
    const top = container.scrollTop;
    const clean = html => {
      const fragment = DOMPurify.sanitize(html, {
        FORBID_TAGS:['style','iframe','object','embed','form','textarea','button'],
        FORBID_ATTR:['style','id','name'], ALLOW_DATA_ATTR:false, RETURN_DOM_FRAGMENT:true,
      });
      for(const image of fragment.querySelectorAll('img'))image.setAttribute('src',imageUrl(image.getAttribute('src')||''));
      const wrapper=container.ownerDocument.createElement('div');wrapper.append(fragment);return wrapper.innerHTML;
    };
    // Sanitize authored HTML separately; KaTeX's trusted layout requires inline styles.
    container.innerHTML = DOMPurify.sanitize(markdownHtml(source, clean));
    for (const link of container.querySelectorAll('a')) {
      if (!link.getAttribute('href')?.startsWith('#')) { link.target = '_blank'; link.rel = 'noopener noreferrer'; }
    }
    for (const input of container.querySelectorAll('input')) { input.disabled = true; input.type = 'checkbox'; }
    container.scrollTop = top;
  }
  container.addEventListener('dblclick', event => {
    if (event.target.closest('a,input') || editor.getOption('readOnly')) return;
    const block = event.target.closest('.markdown-block');
    if (!block) return;
    const position = editor.posFromIndex(Number(block.dataset.sourceFrom));
    editor.setCursor(position); editor.scrollIntoView(position,80); editor.focus();
  });
  const api = {
    render,
    selection(selection=container.ownerDocument.defaultView.getSelection()) {
      if(!selection||selection.isCollapsed||selection.rangeCount!==1||current!==editor.getValue())return null;
      const range=selection.getRangeAt(0),element=node=>node.nodeType===1?node:node.parentElement;
      const first=element(range.startContainer)?.closest('.markdown-block'),last=element(range.endContainer)?.closest('.markdown-block');
      if(!first||!last||!container.contains(first)||!container.contains(last))return null;
      for(const special of container.querySelectorAll('.katex,img'))if(range.intersectsNode(special))return null;
      const mapped=markdownSelectionRange(current,Number(first.dataset.sourceFrom),Number(last.dataset.sourceTo),selection.toString());
      if(!mapped)return null;
      return {...mapped,source:current,doc:editor.getDoc(),bounds:range.getBoundingClientRect()};
    },
    clear() { current = null; pending=null;menu.hidePopover();container.replaceChildren(); },
    locate() {
      const position = editor.indexFromPos(editor.getCursor());
      const block = [...container.querySelectorAll('.markdown-block')].find(block =>
        Number(block.dataset.sourceFrom) <= position && position < Number(block.dataset.sourceTo));
      if (block) container.scrollTop += block.getBoundingClientRect().top - container.getBoundingClientRect().top - container.clientHeight / 3;
    },
  };
  return api;
}
