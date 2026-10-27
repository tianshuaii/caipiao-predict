import { test } from 'node:test';
import assert from 'node:assert/strict';
import { login, loggedIn, logout } from '../src/auth.ts';
test('fake session rejects bad credentials, survives refresh and clears on logout', () => {
 const data=new Map<string,string>();
 const storage={getItem:(key:string)=>data.get(key)??null,setItem:(key:string,value:string)=>{data.set(key,value)},removeItem:(key:string)=>{data.delete(key)}};
 assert.equal(loggedIn(storage),false);
 assert.equal(login('tian','wrong',storage),false);
 assert.equal(loggedIn(storage),false);
 assert.equal(login('tian','6666',storage),true);
 assert.equal(loggedIn(storage),true);
 logout(storage);
 assert.equal(loggedIn(storage),false);
});
