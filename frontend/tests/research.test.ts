import test from 'node:test';
import assert from 'node:assert/strict';
import { loadResearch, saveResearch, removeResearch, parseConstraints } from '../src/research.ts';

function storage() { const data=new Map<string,string>(); return { getItem:(key:string)=>data.get(key)??null,setItem:(key:string,value:string)=>{data.set(key,value);} }; }
const result={version:'research-constraints-v1',mode:'research-only',config:{game:'ssq',seed:42,count:1,pool_size:100,front:{odd:3},back:{}},status:'complete',message:'ok',tickets:[{front:[1,2,3,4,5,6],back:[1]}],budget:2,attempts:8,matched_count:1,note:'research'} as const;

test('saves configuration and result together, can reload and delete',()=>{
 const s=storage();const records=saveResearch(s,JSON.parse(JSON.stringify(result)));
 assert.equal(records.length,1);assert.deepEqual(loadResearch(s)[0].result,result);
 assert.equal(removeResearch(s,records[0].id).length,0);
});
test('corrupt storage is reported without silently overwriting history',()=>{
 const s=storage();s.setItem('lottery-research-v1','{broken');
 assert.throws(()=>loadResearch(s));assert.throws(()=>saveResearch(s,JSON.parse(JSON.stringify(result))));
});
test('storage failures are visible and at most 20 records retained',()=>{
 const s=storage();for(let i=0;i<22;i++) saveResearch(s,JSON.parse(JSON.stringify(result)));
 assert.equal(loadResearch(s).length,20);
 assert.throws(()=>saveResearch({getItem:()=>null,setItem:()=>{throw Error('quota');}},JSON.parse(JSON.stringify(result))));
});

test('rejects overflowing constraints instead of serializing them as null',()=>{
 assert.throws(()=>parseConstraints({sum_min:'9'.repeat(400)}));
 assert.throws(()=>parseConstraints({thirds:'1,2,'+'9'.repeat(400)}));
 assert.deepEqual(parseConstraints({odd:'3',thirds:'2,2,2',sum_min:''}),{odd:3,thirds:[2,2,2]});
});
