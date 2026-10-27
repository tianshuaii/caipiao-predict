import { useState, type FormEvent } from 'react';
import App from './App';
import { login, loggedIn, logout } from './auth';

export default function LoginGate() {
  const [active, setActive] = useState(() => { try { return loggedIn(sessionStorage); } catch { return false; } });
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  function submit(event: FormEvent) {
    event.preventDefault();
    try {
      if (login(username, password, sessionStorage)) { setPassword(''); setError(''); setActive(true); }
      else setError('账号或密码错误');
    } catch { setError('无法保存登录状态，请允许浏览器会话存储。'); }
  }
  function signOut() { try { logout(sessionStorage); } finally { setActive(false); setPassword(''); } }
  if (active) return <App onLogout={signOut} />;
  return <main className="login-page"><form className="login-card" onSubmit={submit}>
    <div className="eyebrow">LOTTERY LAB</div><h1>登录拾数</h1><p>查看开奖数据、策略预测与复盘记录。</p>
    <label htmlFor="username">账号</label><input id="username" name="username" autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required />
    <label htmlFor="password">密码</label><input id="password" name="password" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required />
    {error && <p className="login-error" role="alert">{error}</p>}<button type="submit">登录</button>
  </form></main>;
}
