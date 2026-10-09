// Shared discussion comments. No model endpoints or AI submission are used here.
export function commentAnchor(source,item){
  const from=Array.from(source).slice(0,item.start).join('').length,to=Array.from(source).slice(0,item.end).join('').length;
  if(source.slice(from,to)===item.selection)return {from,to};
  const start=source.indexOf(item.selection);
  return start>=0&&source.indexOf(item.selection,start+1)<0?{from:start,to:start+item.selection.length}:null;
}
export function attachTextComments({editor,request,capture,flush,message}){
  const el=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
  const button=el('button','注释'),panel=el('aside'),head=el('div'),close=el('button','关闭'),title=el('strong','协作注释'),notice=el('p');
  panel.id='text-comments-panel';panel.hidden=button.hidden=true;panel.setAttribute('aria-label','协作注释');head.append(title,close);
  const form=el('form'),quote=el('blockquote'),input=el('textarea'),send=el('button','发布注释'),cancel=el('button','取消此选区');
  input.placeholder='对选中的内容留下评论（不使用 AI）';input.maxLength=4000;input.required=true;cancel.type='button';
  form.hidden=true;form.append(quote,input,send,cancel);
  const filter=el('label'),resolved=el('input'),list=el('div');resolved.type='checkbox';filter.append(resolved,document.createTextNode(' 显示已解决注释'));
  panel.append(head,el('p','评论与回复由协作者共享，不调用 Codex。'),form,filter,list,notice);document.body.append(panel);document.querySelector('header').append(button);
  let info=null,selected=null,fingerprint='',posting=false;
  const post=data=>request('/collaboration',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const fail=error=>{notice.textContent=error.message;message(error.message);};
  button.onclick=()=>{panel.hidden=!panel.hidden;if(!panel.hidden)render(true);};close.onclick=()=>{panel.hidden=true;};
  function begin(detail){
    if(!info||info.me.role==='viewer')return;
    if(input.value.trim()){panel.hidden=false;notice.textContent='请先发布或取消当前注释，草稿已保留。';return;}
    const source=editor.getValue(),doc=editor.getDoc();
    const from=detail?.from??editor.indexFromPos(editor.getCursor('from')),to=detail?.to??editor.indexFromPos(editor.getCursor('to'));
    if(detail&&(detail.source!==source||detail.doc!==doc)){message('选区已变化，请重新选择。');return;}
    if(from>=to){panel.hidden=false;notice.textContent='先选中文字，或在实时预览中右键图片、表格，再添加文字注释。';return;}
    selected={from,to,source,doc,path:capture().path,quote:source.slice(from,to)};
    quote.textContent=selected.quote;form.hidden=false;panel.hidden=false;notice.textContent='';input.focus();
  }
  document.addEventListener('latex-text-comment',event=>begin(event.detail));
  const sourceMenu=document.querySelector('#editor-menu'),sourceAction=el('button','添加文字注释');
  sourceAction.type='button';sourceAction.setAttribute('role','menuitem');sourceAction.hidden=true;sourceMenu.append(sourceAction);
  sourceAction.onclick=()=>{sourceMenu.hidePopover();begin();};
  cancel.onclick=()=>{if(input.value.trim()&&!confirm('放弃尚未发布的注释？'))return;selected=null;input.value='';form.hidden=true;};
  form.onsubmit=async event=>{
    event.preventDefault();if(posting||!selected)return;posting=true;send.disabled=true;
    try{
      const target=selected,text=input.value;await flush();
      if(target.doc!==editor.getDoc()||target.path!==capture().path)throw new Error('文件已切换，注释草稿已保留。');
      const source=editor.getValue();let from=target.from,to=target.to;
      if(source!==target.source){from=source.indexOf(target.quote);to=from+target.quote.length;if(from<0||source.indexOf(target.quote,from+1)>=0)throw new Error('选区已变化或存在重复，请保留注释文字并重新选择。');}
      await post({action:'comment',path:target.path,version:capture().version,start:Array.from(source.slice(0,from)).length,end:Array.from(source.slice(0,to)).length,text});
      input.value='';selected=null;form.hidden=true;notice.textContent='注释已发布';await flush();
    }catch(error){fail(error);}finally{posting=false;send.disabled=false;}
  };
  resolved.onchange=()=>render(true);
  function render(force=false){
    if(!info)return;
    const key=JSON.stringify([capture().path,info.me.id,info.comments,resolved.checked]);
    if(!force&&key===fingerprint)return;
    // Incoming collaboration polling must never discard reply drafts or focus.
    if(list.contains(document.activeElement)||[...list.querySelectorAll('textarea')].some(node=>node.value.trim()))return;
    fingerprint=key;list.replaceChildren();
    for(const item of info.comments){
      if(item.resolved&&!resolved.checked)continue;
      const card=el('article'),author=el('strong',item.name),excerpt=el('blockquote',item.selection),text=el('p',item.text),date=el('small',new Date(item.created*1000).toLocaleString());
      if(/^#[0-9a-f]{6}$/i.test(item.color))author.style.color=item.color;
      card.dataset.commentId=item.id;card.append(author,date,excerpt,text);
      const locate=el('button','定位');locate.type='button';locate.onclick=()=>{
        const range=commentAnchor(editor.getValue(),item);if(!range){notice.textContent='原对象已变化，请根据引用内容查找。';return;}
        editor.setSelection(editor.posFromIndex(range.from),editor.posFromIndex(range.to));editor.scrollIntoView({from:editor.posFromIndex(range.from),to:editor.posFromIndex(range.to)},60);
        const preview=document.querySelector('#markdown-preview');
        for(const block of preview?.querySelectorAll('.markdown-block')||[])if(Number(block.dataset.sourceFrom)<=range.from&&range.from<Number(block.dataset.sourceTo)){block.scrollIntoView({block:'center'});break;}
      };card.append(locate);
      if(info.me.role!=='viewer'&&(info.me.role==='owner'||item.author===info.me.id)){
        const done=el('button',item.resolved?'重新打开':'解决');done.type='button';done.onclick=async()=>{done.disabled=true;try{await post({action:'resolve',id:item.id,resolved:!item.resolved});done.blur();await flush();}catch(error){fail(error);}finally{done.disabled=false;}};card.append(done);
      }
      for(const reply of item.replies||[]){const row=el('div'),name=el('strong',reply.name);row.className='text-comment-reply';if(/^#[0-9a-f]{6}$/i.test(reply.color))name.style.color=reply.color;row.append(name,el('p',reply.text));card.append(row);}
      if(!item.resolved&&info.me.role!=='viewer'){
        const replyForm=el('form'),reply=el('textarea'),submit=el('button','回复');reply.placeholder='回复此注释';reply.maxLength=4000;reply.required=true;replyForm.append(reply,submit);
        replyForm.onsubmit=async event=>{event.preventDefault();const path=capture().path;submit.disabled=true;try{await post({action:'comment-reply',id:item.id,path,text:reply.value});reply.value='';submit.blur();await flush();render(true);}catch(error){fail(error);}finally{submit.disabled=false;}};card.append(replyForm);
      }
      list.append(card);
    }
    if(!list.children.length)list.append(el('p','当前文件暂无注释。'));
  }
  return {update(data){info=data;button.hidden=!data.enabled;sourceAction.hidden=!data.enabled||data.me.role==='viewer';button.textContent='注释'+(data.comments.filter(item=>!item.resolved).length?' · '+data.comments.filter(item=>!item.resolved).length:'');render();},begin};
}
