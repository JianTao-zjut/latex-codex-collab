import assert from 'node:assert/strict';
import {minimalChange,utf16Index,attachCollaboration} from './vendor/latex-collaboration.mjs';
import {bytesBase64} from './vendor/latex-project-files.mjs';
import {commentAnchor} from './vendor/latex-text-comments.mjs';

assert.equal(utf16Index('甲😀乙',2),3);
assert.deepEqual(commentAnchor('甲😀乙',{start:1,end:2,selection:'😀'}),{from:1,to:3});
assert.deepEqual(commentAnchor('same same',{start:5,end:9,selection:'same'}),{from:5,to:9},'An unchanged anchor can distinguish repeated quotes.');
assert.deepEqual(commentAnchor('prefix unique',{start:0,end:6,selection:'unique'}),{from:7,to:13},'Moved unique text remains locatable.');
assert.equal(commentAnchor('same same',{start:1,end:3,selection:'same'}),null,'Changed ambiguous anchors are never guessed.');
for(const [before,after] of [['abc','abXc'],['甲😀乙','甲🌟乙'],['','new'],['old','']]){
  const edit=minimalChange(before,after);assert.equal(before.slice(0,edit.start)+edit.text+before.slice(edit.end),after);
}
assert.equal(bytesBase64(new Uint8Array([0,255,128,1])),'AP+AAQ==');
assert.equal(bytesBase64(new Uint8Array(100000)).length,133336);

class Element {
  constructor(tag){this.tag=tag;this.children=[];this.style={};this.dataset={};this.hidden=false;}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(){} showModal(){this.open=true;} close(){this.open=false;} remove(){}
  contains(){return false;} querySelectorAll(){return [];} addEventListener(){} blur(){}
}
const header=new Element('header'),body=new Element('body');
globalThis.document={createElement:tag=>new Element(tag),createTextNode:text=>({textContent:text}),querySelector:()=>header,addEventListener(){},body};
globalThis.location={origin:'http://test.local'};
const intervals=[];globalThis.setInterval=callback=>{intervals.push(callback);};
let source='one two three',saved=source,version='v1',doc={},markCount=0,conflict=false,requestStarted,release,captureBusy=false;
const me={id:'a',name:'Alice',role:'editor',color:'#2563eb'};
const state=()=>({source:saved,version,path:'/main.tex'});
const data=()=>({enabled:true,me,members:[],spans:[{start:0,end:3,name:'Alice',color:'#2563eb'}],comments:[],state:state()});
const editor={getValue:()=>source,getDoc:()=>doc,posFromIndex:index=>index,
  operation:fn=>fn(),replaceRange:(text,start,end)=>{source=source.slice(0,start)+text+source.slice(end);},
  markText:()=>{markCount++;return {clear(){markCount--;}};}};
let delayed=false;
const request=async(route,options)=>{
  if(!options)return data();const input=JSON.parse(options.body);
  if(conflict){const error=new Error('overlap');error.conflict=true;throw error;}
  if(input.action==='rebase'){assert.equal(input.base,'ONE two three');assert.equal(input.source,'ONE two three!');assert.equal(input.remote,'ONE two THREE');return {source:'ONE two THREE!'};}
  if(delayed){delayed=false;requestStarted();await new Promise(resolve=>{release=resolve;});return {...data(),state:{...state(),source:'ONE two THREE',version:'v2'}};}
  return {...data(),state:{...state(),source:input.source,version:'v3'}};
};
const collaboration=attachCollaboration({editor,request,capture:()=>({saved,version,path:'/main.tex',busy:captureBusy}),
  ack:(state,text)=>{saved=text;version=state.version;},message:()=>{},changed:()=>{}});
await collaboration.init();assert.equal(collaboration.enabled,true);assert.equal(markCount,1);
captureBusy=true;me.can_codex=true;await collaboration.poll();assert.equal(collaboration.canCodex,true,'Permission updates must arrive even while annotations pause source sync.');captureBusy=false;
source='ONE two three';delayed=true;
const started=new Promise(resolve=>{requestStarted=resolve;});
const pending=collaboration.poll();await started;source+='!';release();await pending;
assert.equal(source,'ONE two THREE!','Keep typing that arrives while another author update is in flight.');
assert.equal(saved,'ONE two THREE');assert.equal(version,'v2');
await collaboration.flush();assert.equal(saved,'ONE two THREE!');assert.equal(markCount,1);
conflict=true;source+=' local';await assert.rejects(collaboration.poll(),/overlap/);
assert.equal(source,'ONE two THREE! local');assert.equal(saved,'ONE two THREE!');
await assert.rejects(collaboration.flush(),/协作冲突/);
console.log('PASS: Unicode positions, binary upload, author marks, in-flight typing, shared synchronization and conflict draft protection');
