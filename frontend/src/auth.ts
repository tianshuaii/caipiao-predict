export type AdminState = { authenticated:boolean; username?:string; csrf_token?:string; expires_at?:string };
let csrf='';
let generation=0;
let current:AdminState={authenticated:false};
class AuthError extends Error { status:number; constructor(message:string,status:number){super(message);this.status=status;} }
async function request<T=AdminState>(path:string,options:RequestInit={}):Promise<T> {
  const started=generation;
  const response=await fetch('/api'+path,{...options,credentials:'same-origin',cache:'no-store'});
  const data=await response.json();
  if(!response.ok){if(response.status===401 && started===generation)remember({authenticated:false});throw new AuthError(typeof data.detail==='string'?data.detail:'管理请求失败',response.status);}
  return data;
}
function remember(data:AdminState){current=data;csrf=data.authenticated ? data.csrf_token || '' : '';return data;}
export async function session(){
  const started=generation;
  try {const data=await request('/auth/session');return started===generation?remember(data):current;}
  catch(error){if(started!==generation)return current;throw error;}
}
export async function login(username:string,password:string){
  const started=++generation;remember({authenticated:false});
  const data=await request('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});
  if(started!==generation)return current;
  ++generation;return remember(data);
}
export async function adminRequest<T=AdminState>(path:string,options:RequestInit={}) {
  if(!csrf)throw Error('需要管理员登录');
  const headers=new Headers(options.headers);headers.set('X-CSRF-Token',csrf);
  if(options.body)headers.set('Content-Type','application/json');
  return request<T>(path,{...options,headers});
}
export async function logout(){
  ++generation;
  try {
    if(!csrf){const state=await session();if(!state.authenticated){++generation;remember({authenticated:false});return;}}
    await adminRequest('/auth/logout',{method:'POST'});
  } catch(error){if(!(error instanceof AuthError && error.status===401))throw error;}
  ++generation;remember({authenticated:false});
}
