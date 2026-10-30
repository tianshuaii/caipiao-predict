import { useEffect, useState, type FormEvent } from 'react';
import App from './App';
import { login, session, logout, type AdminState } from './auth';

export default function LoginGate() {
  const [admin,setAdmin]=useState<AdminState>({authenticated:false});
  const [showLogin,setShowLogin]=useState(false);
  const [username,setUsername]=useState('');const [password,setPassword]=useState('');
  const [error,setError]=useState('');const [busy,setBusy]=useState(false);
  useEffect(()=>{
    let active=true;
    async function check(){try{const state=await session();if(active)setAdmin(state);}catch{if(active)setAdmin({authenticated:false});}}
    void check();const timer=setInterval(check,60000);
    return ()=>{active=false;clearInterval(timer);};
  },[]);
  useEffect(()=>{
    if(!admin.expires_at)return;
    const timer=setTimeout(()=>setAdmin({authenticated:false}),Math.max(0,Date.parse(admin.expires_at)-Date.now()));
    return ()=>clearTimeout(timer);
  },[admin.expires_at]);
  async function submit(event:FormEvent){
    event.preventDefault();setBusy(true);setError('');
    try{setAdmin(await login(username,password));setPassword('');setShowLogin(false);}
    catch(e){setError(e instanceof Error?e.message:'登录失败');}
    finally{setBusy(false);}
  }
  async function signOut(){
    setBusy(true);setError('');
    try{await logout();setAdmin({authenticated:false});}
    catch{setError('退出未确认，请重试；服务端会话可能仍有效。');setShowLogin(true);}
    finally{setBusy(false);}
  }
  if(!showLogin)return <App adminName={admin.authenticated?admin.username:undefined} onLogin={()=>{setError('');setShowLogin(true);}} onLogout={()=>{void signOut();}} />;
  return <main className="login-page"><form className="login-card" onSubmit={submit}>
    <div className="eyebrow">LOTTERY LAB</div><h1>管理员登录</h1><p>公共看板无需登录。管理权限由服务端验证，未配置时不会启用。</p>
    <label htmlFor="username">账号</label><input id="username" autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required />
    <label htmlFor="password">密码</label><input id="password" type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required />
    {error && <p className="login-error" role="alert">{error}</p>}
    <button type="submit" disabled={busy}>登录</button>
    {admin.authenticated && <button type="button" disabled={busy} onClick={()=>{void signOut();}}>重试退出</button>}
    <button type="button" disabled={busy} onClick={()=>{setShowLogin(false);setPassword('');}}>返回公共看板</button>
  </form></main>;
}
