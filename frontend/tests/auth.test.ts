import { test } from 'node:test';
import assert from 'node:assert/strict';
import { login, session, logout, adminRequest } from '../src/auth.ts';

test('server sessions supply csrf; logout clears it; no local password grants rights', async () => {
 const original=globalThis.fetch;const calls:{url:string;options:RequestInit|undefined}[]=[];
 globalThis.fetch=async (url,options)=>{calls.push({url:String(url),options});return new Response(JSON.stringify(String(url).endsWith('/logout')?{authenticated:false}:{authenticated:true,username:'operator',csrf_token:'csrf-secret',expires_at:'2030-01-01T00:00:00Z'}),{status:200});};
 try {
  assert.equal((await session()).authenticated,true);
  await login('operator','test');
  await adminRequest('/admin/experiment',{method:'POST',body:'{}'});
  assert.equal(new Headers(calls.at(-1)?.options?.headers).get('X-CSRF-Token'),'csrf-secret');
  await logout();
  await assert.rejects(()=>adminRequest('/admin/experiment',{method:'POST'}));
 } finally {globalThis.fetch=original;}
});

test('failed login never establishes an admin session',async()=>{
 const original=globalThis.fetch;
 globalThis.fetch=async()=>new Response(JSON.stringify({detail:'账号或密码错误'}),{status:401});
 try {await assert.rejects(()=>login('tian','6666'),/账号或密码错误/);await assert.rejects(()=>adminRequest('/admin/x',{method:'POST'}));}
 finally {globalThis.fetch=original;}
});

test('a session response started before logout cannot restore stale credentials',async()=>{
 const original=globalThis.fetch;let finish:(value:Response)=>void=()=>{};
 globalThis.fetch=async()=>new Response(JSON.stringify({authenticated:true,csrf_token:'csrf-secret'}),{status:200});
 try {
  await login('operator','test');
  globalThis.fetch=async url=>String(url).endsWith('/session') ? new Promise<Response>(resolve=>{finish=resolve;}) : new Response(JSON.stringify({authenticated:false}),{status:200});
  const pending=session();await logout();
  finish(new Response(JSON.stringify({authenticated:true,csrf_token:'stale'}),{status:200}));
  assert.equal((await pending).authenticated,false);
  await assert.rejects(()=>adminRequest('/admin/x',{method:'POST'}));
 } finally{globalThis.fetch=original;}
});

test('late failed login cannot prevent server logout of a newer session',async()=>{
 const original=globalThis.fetch;let finish:(v:Response)=>void=()=>{};let calls=0;let exits=0;
 globalThis.fetch=async url=>{
  if(String(url).endsWith('/logout')){exits++;return new Response(JSON.stringify({authenticated:false}));}
  if(++calls===1)return new Promise<Response>(resolve=>{finish=resolve;});
  return new Response(JSON.stringify({authenticated:true,csrf_token:'new-token'}));
 };
 try{
  const old=login('operator','bad').catch(()=>{});await login('operator','good');
  finish(new Response(JSON.stringify({detail:'bad'}),{status:401}));await old;
  await logout();assert.equal(exits,1);
 }finally{globalThis.fetch=original;}
});

test('polling started during logout cannot resurrect an ended session',async()=>{
 const original=globalThis.fetch;let endLogout:(v:Response)=>void=()=>{};let endSession:(v:Response)=>void=()=>{};
 globalThis.fetch=async()=>new Response(JSON.stringify({authenticated:true,csrf_token:'token'}));
 try{
  await login('operator','good');
  globalThis.fetch=async url=>new Promise<Response>(resolve=>{if(String(url).endsWith('/logout'))endLogout=resolve;else endSession=resolve;});
  const leaving=logout();const polling=session();endLogout(new Response(JSON.stringify({authenticated:false})));await leaving;
  endSession(new Response(JSON.stringify({authenticated:true,csrf_token:'old'})));
  assert.equal((await polling).authenticated,false);
 }finally{globalThis.fetch=original;}
});
