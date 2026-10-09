// Invitation-based collaboration. Server merges disjoint edits; overlap stays in the draft.
import {attachTextComments} from './latex-text-comments.mjs';
export const clientId = Array.from(crypto.getRandomValues(new Uint8Array(16)), x=>x.toString(16).padStart(2,'0')).join('');
export const utf16Index = (text, index) => Array.from(text).slice(0,index).join('').length;
export function minimalChange(before, after) {
  let start=0, end=before.length, tail=after.length;
  while(start<end&&start<tail&&before[start]===after[start])start++;
  while(end>start&&tail>start&&before[end-1]===after[tail-1]){end--;tail--;}
  // Never split a surrogate pair.
  if(start&&/^[\uDC00-\uDFFF]$/.test(before[start]||after[start]||''))start--;
  return {start,end,text:after.slice(start,tail)};
}
export function attachCollaboration({editor,request,capture,ack,message,changed}) {
  let enabled=false, info=null, pending=null, stopped=false, marks=[], rendering=false;
  const post=data=>request('/collaboration',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const el=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
  const button=el('button','协作'), dialog=el('dialog'), heading=el('h2','项目协作'), close=el('button','关闭');
  dialog.className='collaboration-dialog'; button.hidden=true;
  const identity=el('p'), members=el('div'), invite=el('form'), name=el('input'), role=el('select');
  name.placeholder='协作者姓名';name.required=true;name.maxLength=48;
  for(const [value,label] of [['editor','可编辑'],['viewer','只读']]){const option=el('option',label);option.value=value;role.append(option);}
  const generate=el('button','生成邀请'), link=el('textarea'), copy=el('button','复制邀请链接');copy.type='button';link.readOnly=true;link.hidden=copy.hidden=true;
  invite.append(name,role,generate,link,copy);
  const commentForm=el('form'), comment=el('textarea'), send=el('button','批注当前选区'), comments=el('div'), notice=el('p');
  comment.placeholder='先在源码中选中文字，再填写批注';comment.maxLength=4000;comment.required=true;
  commentForm.append(comment,send);dialog.append(heading,identity,members,invite,el('h3','共享批注'),commentForm,comments,notice,close);
  document.body.append(dialog);document.querySelector('header').append(button);
  button.onclick=()=>{dialog.showModal();void poll();};close.onclick=()=>dialog.close();
  const fail=e=>{notice.textContent=e.message;message(e.message);};
  const textComments=attachTextComments({editor,request,capture,flush,message});
  invite.onsubmit=async event=>{event.preventDefault();try{const data=await post({action:'invite',name:name.value,role:role.value});link.value=data.url||location.origin+'/join#invite='+encodeURIComponent(data.token);link.hidden=copy.hidden=false;notice.textContent='此链接代表这位协作者的身份，请仅交给本人。';await poll();}catch(e){fail(e);}};
  copy.onclick=async()=>{try{await navigator.clipboard.writeText(link.value);notice.textContent='邀请链接已复制';}catch{link.focus();link.select();notice.textContent='请复制已选中的邀请链接';}};
  commentForm.onsubmit=async event=>{event.preventDefault();try{const doc=editor.getDoc(),from=editor.indexFromPos(editor.getCursor('from')),to=editor.indexFromPos(editor.getCursor('to')),quote=editor.getValue().slice(from,to);if(!quote)throw new Error('请先选择需要批注的源码。');await flush();if(doc!==editor.getDoc())throw new Error('文件已切换，请重新选择。');const source=editor.getValue(),start=source.indexOf(quote);if(start<0||source.indexOf(quote,start+1)!==-1)throw new Error('选区已变化或有重复，请选择一段唯一的文字后重试。');const state=capture();await post({action:'comment',version:state.version,start:Array.from(source.slice(0,start)).length,end:Array.from(source.slice(0,start+quote.length)).length,text:comment.value});comment.value='';await poll();}catch(e){fail(e);}};
  function paint(data) {
    textComments.update(data);
    info=data;identity.textContent=`${data.me.name} · ${data.me.role==='owner'?'项目所有者':data.me.role==='viewer'?'只读':'可编辑'} · Codex ${data.me.can_codex?'已授权':'未授权'}`;
    document.body.dataset.codexPermission=data.me.can_codex?'allowed':'denied';
    document.body.dataset.collaborationRole=data.me.role;
    identity.style.color=data.me.color;invite.hidden=data.me.role!=='owner';commentForm.hidden=data.me.role==='viewer';
    members.replaceChildren();
    for(const member of data.members){if(member.revoked)continue;const row=el('p',`${member.name} · ${member.online?'在线':'离线'} · Codex ${member.can_codex?'已授权':'未授权'}`);row.style.color=member.color;
      if(data.me.role==='owner'&&member.role==='editor'){const permission=el('button',member.can_codex?'撤销 Codex 权限':'允许使用 Codex');permission.onclick=async()=>{permission.disabled=true;try{await post({action:'codex-permission',member:member.id,allowed:!member.can_codex});await poll();}catch(e){fail(e);}finally{permission.disabled=false;}};row.append(permission);}
      if(data.me.role==='owner'&&member.role!=='owner'){const revoke=el('button','撤销邀请');revoke.onclick=async()=>{if(!confirm(`撤销 ${member.name} 的访问权限？`))return;try{await post({action:'revoke',member:member.id});await poll();}catch(e){fail(e);}};row.append(revoke);}members.append(row);}
    comments.replaceChildren();
    for(const item of data.comments){if(item.resolved)continue;const card=el('article'), author=el('strong',item.name),quote=el('blockquote',item.selection),text=el('p',item.text);author.style.color=item.color;quote.style.borderLeftColor=item.color;card.append(author,quote,text);
      const locate=el('button','定位');locate.onclick=()=>{const source=editor.getValue(),start=source.indexOf(item.selection);if(start<0||source.indexOf(item.selection,start+1)!==-1){notice.textContent='原选区已变化或存在重复，请根据引用文字查找。';return;}dialog.close();editor.setSelection(editor.posFromIndex(start),editor.posFromIndex(start+item.selection.length));editor.focus();};card.append(locate);
      if(item.author===data.me.id||data.me.role==='owner'){const done=el('button','解决');done.onclick=async()=>{try{await post({action:'resolve',id:item.id});await poll();}catch(e){fail(e);}};card.append(done);}comments.append(card);}
    rendering=true;marks.forEach(mark=>mark.clear());marks=[];
    const state=capture(), source=editor.getValue();
    if(source===data.state.source.replace(/\r\n/g,'\n')&&state.path===data.state.path){for(const span of data.spans){if(!/^#[0-9a-f]{6}$/i.test(span.color))continue;marks.push(editor.markText(editor.posFromIndex(utf16Index(source,span.start)),editor.posFromIndex(utf16Index(source,span.end)),{css:`background-color:${span.color}22;border-bottom:2px solid ${span.color}`,title:span.name,inclusiveLeft:false,inclusiveRight:false}));}}
    if(state.path===data.state.path){for(const item of data.comments){if(item.resolved||!item.selection||!/^#[0-9a-f]{6}$/i.test(item.color))continue;const start=source.indexOf(item.selection);if(start<0||source.indexOf(item.selection,start+1)!==-1)continue;marks.push(editor.markText(editor.posFromIndex(start),editor.posFromIndex(start+item.selection.length),{css:`box-shadow:inset 0 -2px ${item.color}`,title:item.name+': '+item.text.slice(0,200),inclusiveLeft:false,inclusiveRight:false}));}}
    rendering=false;changed(data.me);button.title=data.me.can_codex?'已获得 Codex 使用权限':'Codex 使用需项目所有者授权';
  }
  function apply(source) {
    const before=editor.getValue();if(before===source)return;
    const edit=minimalChange(before,source);rendering=true;
    editor.operation(()=>editor.replaceRange(edit.text,editor.posFromIndex(edit.start),editor.posFromIndex(edit.end),'collaboration-remote'));
    rendering=false;
  }
  async function accept(state,submitted,doc) {
    const remote=state.source.replace(/\r\n/g,'\n');
    if(doc!==editor.getDoc()||capture().path!==state.path)return;
    let current=editor.getValue(),merged=remote;
    // Preserve typing that arrived during the network request.
    for(let attempt=0;current!==submitted;attempt++){
      if(attempt>=8)throw new Error('持续输入期间同步暂缓；草稿已保留。');
      const result=await post({action:'rebase',base:submitted,source:current,remote});
      if(doc!==editor.getDoc())return;
      if(editor.getValue()===current){merged=result.source;break;}current=editor.getValue();
    }
    ack(state,remote);apply(merged);
  }
  async function resolveConflict() {
    const original=capture(), doc=editor.getDoc();
    const latest=await request('/collaboration'), draft=editor.getValue();
    if(latest.state.path!==original.path)throw new Error('当前页面的文件绑定已失效，请保留草稿并重新打开对应文件。');
    const box=el('dialog');box.className='collaboration-dialog';
    const server=el('textarea'),merge=el('textarea'),error=el('p'),cancel=el('button','保留草稿，稍后处理'),save=el('button','提交合并结果');
    server.readOnly=true;server.value=latest.state.source;merge.value=draft;
    box.append(el('h2','同一段修改发生冲突'),el('p','上方是服务器版本，下方保留你的草稿。请在下方合并双方修改后提交。'),server,merge,error,save,cancel);document.body.append(box);box.showModal();
    cancel.onclick=()=>{box.close();box.remove();};
    save.onclick=async()=>{if(doc!==editor.getDoc()||original.path!==capture().path||editor.getValue()!==draft){error.textContent='草稿已变化，请关闭后重新合并。';return;}save.disabled=true;try{
      const data=await post({action:'sync',path:original.path,version:latest.state.version,source:merge.value});
      await accept(data.state,draft,doc);stopped=false;paint(data);box.close();box.remove();message('合并结果已保存');
    }catch(e){error.textContent=e.message;}finally{save.disabled=false;}};
  }
  const conflictButton=el('button','处理协作冲突');conflictButton.hidden=true;document.querySelector('header').append(conflictButton);
  conflictButton.onclick=()=>void resolveConflict().catch(fail);
  async function cycle() {
    const state=capture();if(!enabled||stopped||!state.version)return;
    if(state.busy){const data=await request('/collaboration');if(data.state.path===capture().path)paint(data);return;}
    const doc=editor.getDoc(),submitted=editor.getValue();
    try{
      const data=info?.me.role==='viewer'?await request('/collaboration'):await post({action:'sync',path:state.path,source:submitted,version:state.version});
      await accept(data.state,submitted,doc);if(doc===editor.getDoc()){paint(data);message(submitted===state.saved?'协作已同步':'修改已同步');}
    }catch(e){if(e.conflict){stopped=true;conflictButton.hidden=false;message(e.message);}else if(e.status===401){stopped=true;message('邀请已撤销或登录已过期，请重新打开邀请链接。');}else message(e.message);throw e;}
    finally{conflictButton.hidden=!stopped;}
  }
  function poll(){if(pending)return pending;pending=cycle().finally(()=>{pending=null;});return pending;}
  async function flush(){if(!enabled)return;if(pending)await pending;await poll();if(stopped)throw new Error('请先处理协作冲突。');}
  async function init(){const data=await request('/collaboration');enabled=!!data.enabled;if(enabled){button.hidden=false;paint(data);setInterval(()=>{void poll().catch(()=>{});},1000);}return data;}
  return {init,poll,flush,accept,get enabled(){return enabled;},get canCodex(){return !!info?.me.can_codex;},get syncing(){return !!pending;},get rendering(){return rendering;},get viewer(){return info?.me.role==='viewer';}};
}
