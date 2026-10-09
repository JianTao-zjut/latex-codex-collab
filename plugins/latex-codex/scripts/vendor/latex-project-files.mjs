export function bytesBase64(bytes) {
  let binary='';for(let offset=0;offset<bytes.length;offset+=16384)binary+=String.fromCharCode(...bytes.subarray(offset,offset+16384));return btoa(binary);
}
export function attachProjectFiles({request,collaboration,capture,switchSource}) {
  const el=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
  const button=el('button','项目文件'),dialog=el('dialog'),toolbar=el('div'),list=el('div'),notice=el('p'),filter=el('input'),close=el('button','关闭');dialog.className='collaboration-dialog';button.hidden=true;
  const upload=el('input');upload.type='file';upload.multiple=true;upload.setAttribute('aria-label','上传项目文件');
  const form=el('form'),path=el('input'),kind=el('select'),create=el('button','新建');path.placeholder='项目内相对路径，例如 sections/intro.tex';path.required=true;
  for(const [value,text] of [['create','文本文件'],['mkdir','文件夹']]){const option=el('option',text);option.value=value;kind.append(option);}form.append(path,kind,create);
  const zip=el('a','下载整个项目');zip.href='/files/archive';zip.download='project.zip';toolbar.append(upload,form,zip);
  filter.placeholder='筛选文件';dialog.append(el('h2','项目文件'),toolbar,filter,list,notice,close);document.body.append(dialog);document.querySelector('header').append(button);
  let tree={files:[]},owner=false;
  const post=data=>request('/files',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const fail=e=>notice.textContent=e.message;
  async function refresh(){tree=await request('/files');render();}
  const version=async name=>(await request('/files/version?path='+encodeURIComponent(name))).version;
  async function mutate(data){await collaboration.flush();await post(data);await refresh();notice.textContent='操作已完成';}
  function render(){list.replaceChildren();for(const item of tree.files.filter(item=>item.path.toLowerCase().includes(filter.value.toLowerCase()))){const row=el('div');row.className='project-file-row';
    const open=el('button',(item.directory?'📁 ':'')+item.path+(item.main?'（主文件）':''));open.className='file-name';open.disabled=item.directory||!item.editable;
    open.onclick=async()=>{try{await collaboration.flush();if(await switchSource(capture().root.replace(/[\\/]$/,'')+'/'+item.path,false)){dialog.close();}}catch(e){fail(e);}};row.append(open);
    if(!item.directory){const download=el('a','下载');download.href='/files/download?path='+encodeURIComponent(item.path);download.download=item.path.split('/').pop();row.append(download);}
    if(owner&&!item.main){if(!item.directory){const rename=el('button','重命名');rename.onclick=async()=>{const name=prompt('新的项目相对路径',item.path);if(!name||name===item.path)return;try{await mutate({action:'rename',path:item.path,new_path:name,version:await version(item.path)});}catch(e){fail(e);}};row.append(rename);}
      const remove=el('button','删除');remove.onclick=async()=>{if(!confirm(item.directory?`删除空文件夹 ${item.path}？`:`将 ${item.path} 移入项目回收区？`))return;try{await mutate({action:'delete',path:item.path,...(!item.directory?{version:await version(item.path)}:{})});}catch(e){fail(e);}};row.append(remove);}list.append(row);}}
  filter.oninput=render;button.onclick=async()=>{dialog.showModal();try{await refresh();}catch(e){fail(e);}};close.onclick=()=>dialog.close();
  form.onsubmit=async event=>{event.preventDefault();try{await mutate({action:kind.value,path:path.value});path.value='';}catch(e){fail(e);}};
  upload.onchange=async()=>{upload.disabled=true;try{await collaboration.flush();for(const file of upload.files){if(file.size>16*1024*1024)throw new Error('单个文件最大 16 MiB');const name=file.webkitRelativePath||file.name,existing=tree.files.find(item=>item.path===name);let expected;
      if(existing){if(!confirm(`替换 ${name}？正在编辑的文件无法替换。`))continue;expected=await version(name);}
      notice.textContent='正在上传 '+name;await post({action:'upload',path:name,content:bytesBase64(new Uint8Array(await file.arrayBuffer())),...(expected?{version:expected}:{})});await refresh();}notice.textContent='上传完成';}catch(e){fail(e);}finally{upload.value='';upload.disabled=false;}};
  return {setIdentity(me){owner=me.role==='owner';button.hidden=false;toolbar.hidden=!owner;zip.hidden=false;/* Readers can download too. */if(!owner)dialog.insertBefore(zip,filter);render();}};
}
