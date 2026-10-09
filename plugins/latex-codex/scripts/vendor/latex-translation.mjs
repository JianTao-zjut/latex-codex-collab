import {markdownHtml} from './latex-markdown.mjs';
import DOMPurify from './purify.mjs';

export const readingRatio = pane => Math.max(0,Math.min(1,pane.scrollTop/Math.max(1,pane.scrollHeight-pane.clientHeight)));
const words = text => (text.replace(/\\(?:cite\w*|label|ref)\{[^}]*\}|\\[A-Za-z]+/g,' ').toLowerCase().match(/[a-z]{2,}/g)||[]);
const grams = text => {const tokens=words(text),set=new Set();for(let i=0;i+2<tokens.length;i++)set.add(tokens.slice(i,i+3).join(' '));return set;};
export function pdfAnchor(text,blocks){
  const sample=grams(text);let best=-1,score=1;
  blocks.forEach((block,index)=>{let hits=0;for(const gram of grams(block.source))if(sample.has(gram))hits++;if(hits>score){score=hits;best=index;}});
  return best;
}
export function sourceAnchor(offset,file,blocks){
  let index=blocks.findIndex(block=>block.file===file&&block.from<=offset&&offset<block.to);
  if(index<0)index=blocks.findIndex(block=>block.file===file&&block.from>=offset);
  return index;
}

export function attachTranslation({request,preview,markdownPane,pdfViewer,capture}){
  const shell=preview.closest('.preview-shell'),wrap=document.createElement('div');wrap.className='translation-wrap';shell.before(wrap);wrap.append(shell);
  const pane=document.createElement('aside');pane.className='translation-pane';pane.hidden=true;pane.setAttribute('aria-label','中文翻译预览');
  const heading=document.createElement('div');heading.className='translation-heading';
  const label=document.createElement('strong');label.textContent='中文译文';
  const follow=document.createElement('input');follow.type='checkbox';follow.checked=true;follow.setAttribute('aria-label','跟随原文滚动');
  const followLabel=document.createElement('label');followLabel.append(follow,document.createTextNode('跟随原文'));
  const download=document.createElement('a');download.href='/translation/download';download.textContent='下载';download.download='';
  const retry=document.createElement('button');retry.textContent='重试';retry.hidden=true;
  heading.append(label,followLabel,download,retry);
  const notice=document.createElement('div');notice.className='translation-status';notice.setAttribute('role','status');
  const content=document.createElement('div');content.className='translation-content';content.setAttribute('tabindex','0');
  pane.append(heading,notice,content);wrap.append(pane);
  const styles=document.createElement('link');styles.rel='stylesheet';styles.href='/vendor/latex-translation.css';document.head.append(styles);
  const toggle=document.createElement('button');toggle.id='translation-toggle';toggle.textContent='中文翻译';toggle.setAttribute('aria-pressed','false');toggle.title='首次翻译使用 Codex 额度；保存后仅翻译变化段落';
  document.querySelector('.pdf-toolbar').append(toggle);
  const key='latex-codex-translation:'+location.pathname.replace(/\/(?:join)?$/,'');
  let active=false,revision='',blocks=[],nodes=[],pending=null,seen='',data=null,serial=0,frame=0;
  const pdfTexts=new WeakMap();
  function paint(result){
    data=result;revision=result.revision;
    const descriptions={off:'已停止更新 · 保留已有译文',queued:'等待保存稳定后翻译…',running:'正在增量翻译…',ready:'译文已更新',error:'翻译失败'};
    notice.textContent=(descriptions[result.status]||'')+` · ${result.total-result.pending}/${result.total} 段`+(result.error?'\n'+result.error:'')+(!result.can_translate?'\n未获 Codex 授权，仅查看缓存译文':'');
    retry.hidden=result.status!=='error'||!result.can_translate;
    if(result.unchanged)return;
    blocks=result.blocks||[];nodes=[];const top=content.scrollTop;content.replaceChildren();
    for(const block of blocks){
      const node=document.createElement('article');node.className='translation-block'+(block.text==null?' pending':'');node.title=block.file+':'+block.line;
      if(block.text==null){node.textContent='待翻译 · '+block.source;}
      else{
        const options={FORBID_TAGS:['img','iframe','object','embed','form','input','textarea','button','style'],FORBID_ATTR:['id','name'],ALLOW_DATA_ATTR:false};
        node.innerHTML=DOMPurify.sanitize(markdownHtml(block.text,html=>DOMPurify.sanitize(html,{...options,FORBID_ATTR:['style','id','name']})),options);
        for(const link of node.querySelectorAll('a')){link.target='_blank';link.rel='noopener noreferrer';}
      }
      content.append(node);nodes.push(node);
    }
    content.scrollTop=top;scheduleFollow();
  }
  const post=action=>request('/translation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action})});
  function poll(){
    if(!active||pending)return pending;
    pending=(async()=>{
      const state=capture(),stamp=state.version+'|'+state.projectVersion;
      if(data?.can_translate&&stamp!==seen){await post('refresh');seen=stamp;}
      const result=await request('/translation?revision='+encodeURIComponent(revision));
      if(active)paint(result);
    })().catch(error=>{notice.textContent=error.message;retry.hidden=!data?.can_translate;}).finally(()=>pending=null);
    return pending;
  }
  async function setActive(value){
    toggle.disabled=true;
    active=value;pane.hidden=!value;toggle.setAttribute('aria-pressed',String(value));serial++;
    try{localStorage.setItem(key,value?'on':'off');}catch{}
    if(!value){try{if(data?.can_stop)await post('disable');}catch(error){notice.textContent=error.message;}finally{toggle.disabled=false;}return;}
    notice.textContent='正在读取译文…';
    try{
      const result=await request('/translation');paint(result);
      if(result.can_translate){
        // Reopening a pane must not cancel another tab's in-flight translation.
        if(!['queued','running','ready'].includes(result.status))await post('enable');
        seen=capture().version+'|'+capture().projectVersion;await poll();
      }
    }catch(error){notice.textContent=error.message;retry.hidden=false;}finally{toggle.disabled=false;}
  }
  toggle.onclick=()=>void setActive(!active);
  retry.onclick=async()=>{try{await post('enable');revision='';await poll();}catch(error){notice.textContent=error.message;}};
  function align(index,fraction=0){if(nodes[index])content.scrollTop=nodes[index].offsetTop+fraction*nodes[index].offsetHeight-content.clientHeight*.15;}
  async function sync(){
    if(!active||!follow.checked||!nodes.length)return;
    const ticket=++serial,state=capture(),origin=state.live?markdownPane:preview;
    if(state.live){
      const bounds=origin.getBoundingClientRect(),target=bounds.top+origin.clientHeight*.15;
      const block=[...origin.querySelectorAll('.markdown-block')].find(node=>node.getBoundingClientRect().bottom>target);
      if(block){const rect=block.getBoundingClientRect(),fraction=Math.max(0,Math.min(1,(target-rect.top)/Math.max(1,rect.height)));
        const offset=Number(block.dataset.sourceFrom)+fraction*(Number(block.dataset.sourceTo)-Number(block.dataset.sourceFrom));
        const index=sourceAnchor(offset,state.file,blocks);if(index>=0){align(index,(offset-blocks[index].from)/Math.max(1,blocks[index].to-blocks[index].from));return;}}
    }else if(pdfViewer.pdfDocument){
      const doc=pdfViewer.pdfDocument;let cache=pdfTexts.get(doc);if(!cache){cache=new Map();pdfTexts.set(doc,cache);}
      const number=pdfViewer.currentPageNumber||1,view=pdfViewer.getPageView(number-1);
      const fraction=Math.max(0,Math.min(1,(preview.scrollTop-(view?.div.offsetTop||0))/Math.max(1,view?.div.clientHeight||1)));
      try{
        if(!cache.has(number))cache.set(number,doc.getPage(number).then(async page=>({height:page.getViewport({scale:1}).height,items:(await page.getTextContent()).items})));
        const page=await cache.get(number);if(ticket!==serial||!active||!follow.checked)return;
        const y=page.height*(1-fraction),text=page.items.filter(item=>item.transform?.[5]<=y+45&&item.transform?.[5]>=y-180).map(item=>item.str).join(' ');
        const index=pdfAnchor(text,blocks);if(index>=0){align(index);return;}
      }catch{cache.delete(number);}
    }
    content.scrollTop=readingRatio(origin)*Math.max(0,content.scrollHeight-content.clientHeight);
  }
  function scheduleFollow(){if(frame)return;frame=requestAnimationFrame(()=>{frame=0;void sync();});}
  preview.addEventListener('scroll',scheduleFollow,{passive:true});markdownPane.addEventListener('scroll',scheduleFollow,{passive:true});follow.onchange=scheduleFollow;
  new ResizeObserver(scheduleFollow).observe(preview);setInterval(()=>void poll(),2500);
  try{if(localStorage.getItem(key)==='on')void setActive(true);}catch{}
  return {setActive,poll};
}
