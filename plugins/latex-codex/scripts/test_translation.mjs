import assert from 'node:assert/strict';
import {readingRatio,pdfAnchor,sourceAnchor,attachTranslation} from './vendor/latex-translation.mjs';
const blocks=[{file:'main.md',from:0,to:80,source:'Following a user request does not make a response appropriate.'},
  {file:'main.md',from:82,to:160,source:'A model may produce inaccurate claims or neglect other people interests.'}];
assert.equal(sourceAnchor(90,'main.md',blocks),1);
assert.equal(sourceAnchor(90,'other.md',blocks),-1);
assert.equal(pdfAnchor('A model may produce inaccurate claims about research.',blocks),1);
assert.equal(pdfAnchor('Figure 1. x + y = z',blocks),-1);
assert.equal(readingRatio({scrollTop:100,scrollHeight:400,clientHeight:200}),.5);
assert.equal(readingRatio({scrollTop:0,scrollHeight:100,clientHeight:200}),0);
assert.equal(readingRatio({scrollTop:500,scrollHeight:400,clientHeight:200}),1);
console.log('PASS: source-block anchors, PDF text anchors and bounded scroll fallback');

class Element{
  constructor(tag){this.tag=tag;this.children=[];this.events={};this.attributes={};this.scrollTop=0;this.scrollHeight=400;this.clientHeight=100;this.offsetHeight=100;this.offsetTop=0;this.hidden=false;}
  append(...nodes){for(const node of nodes){node.offsetTop=this.children.length*100;this.children.push(node);}}
  before(){} setAttribute(name,value){this.attributes[name]=value;}
  replaceChildren(){this.children=[];}
  addEventListener(name,handler){this.events[name]=handler;}
  querySelectorAll(){return [];}
  getBoundingClientRect(){return {top:0,bottom:100,height:100};}
}
const toolbar=new Element('toolbar'),head=new Element('head'),shell=new Element('shell');
const preview=new Element('preview'),markdown=new Element('markdown');preview.closest=()=>shell;
const originalBlocks=[{dataset:{sourceFrom:'0',sourceTo:'80'},getBoundingClientRect:()=>({top:-100,bottom:100,height:200})},
  {dataset:{sourceFrom:'82',sourceTo:'160'},getBoundingClientRect:()=>({top:100,bottom:200,height:100})}];
markdown.querySelectorAll=()=>originalBlocks;
globalThis.document={head,createElement:tag=>new Element(tag),createTextNode:text=>({text}),querySelector:()=>toolbar};
globalThis.location={pathname:'/p/test/'};globalThis.localStorage={getItem:()=>null,setItem:()=>{}};
let frames=[],live=true,calls=[];
globalThis.requestAnimationFrame=callback=>{frames.push(callback);return frames.length;};
globalThis.ResizeObserver=class{observe(){}};globalThis.setInterval=()=>0;
const pdfViewer={currentPageNumber:1,getPageView:()=>({div:{offsetTop:0,clientHeight:500}}),
  pdfDocument:{getPage:async()=>({getViewport:()=>({height:500}),getTextContent:async()=>({items:[
    {str:'A model may produce inaccurate claims or neglect other people interests.',transform:[1,0,0,1,0,470]}]})})}};
let wrapper;shell.before=node=>wrapper=node;
const attached=attachTranslation({preview,markdownPane:markdown,pdfViewer,
  capture:()=>({version:'saved',projectVersion:'saved',live,file:'main.md'}),
  request:async(url,options)=>{calls.push({url,options});return {revision:'cache',status:'off',total:2,pending:2,can_translate:false,blocks:blocks.map(block=>({...block,text:null}))};}});
await attached.setActive(true);while(frames.length)frames.shift()();
const side=wrapper.children[1],content=side.children[2],follow=side.children[0].children[1].children[0];
assert.ok(Math.abs(content.scrollTop-42.5)<.001,'Markdown follows the visible source block.');
originalBlocks[0].getBoundingClientRect=()=>({top:-200,bottom:0,height:200});
originalBlocks[1].getBoundingClientRect=()=>({top:0,bottom:150,height:150});
markdown.events.scroll();while(frames.length)frames.shift()();
assert.ok(Math.abs(content.scrollTop-95)<.001);
follow.checked=false;content.scrollTop=11;markdown.events.scroll();while(frames.length)frames.shift()();assert.equal(content.scrollTop,11);
follow.checked=true;live=false;preview.events.scroll();while(frames.length)frames.shift()();
await new Promise(resolve=>setImmediate(resolve));
assert.equal(content.scrollTop,85,'PDF current-page text locates the matching translation.');
await attached.setActive(false);assert.equal(side.hidden,true);
assert.ok(calls.every(call=>!call.options),'A cache-only reader makes no translation POST request.');
console.log('PASS: rendered pane toggle, Markdown/PDF follow scroll, follow-off and cache-only permission');
calls=[];
const reopened=attachTranslation({preview,markdownPane:markdown,pdfViewer,
  capture:()=>({version:'saved',projectVersion:'saved',live,file:'main.md'}),
  request:async(url,options)=>{calls.push({url,options});return {revision:'cache',status:'running',total:2,pending:2,can_translate:true,blocks:blocks.map(block=>({...block,text:null}))};}});
await reopened.setActive(true);
assert.ok(calls.every(call=>!call.options),'Reopening an authorized pane must not restart an active translation.');
console.log('PASS: reconnect preserves the in-flight translation');
