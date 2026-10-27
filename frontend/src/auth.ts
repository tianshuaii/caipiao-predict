const KEY = 'lottery-demo-session-v1';
type SessionStore = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
export function loggedIn(storage: SessionStore): boolean { return storage.getItem(KEY) === 'tian'; }
export function login(username: string, password: string, storage: SessionStore): boolean {
  if (username !== 'tian' || password !== '6666') return false;
  storage.setItem(KEY, 'tian');
  return true;
}
export function logout(storage: SessionStore) { storage.removeItem(KEY); }
