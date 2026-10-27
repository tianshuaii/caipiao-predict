import type { Game, Ticket } from './api';
export type ZoneConstraints = { odd?: number; small?: number; thirds?: number[]; fourths?: number[]; sum_min?: number; sum_max?: number; span_min?: number; span_max?: number };
export type ResearchConfig = { game: Game; seed: number; count: number; pool_size: number; front: ZoneConstraints; back: ZoneConstraints };
export type ResearchResult = { version: string; mode: string; config: ResearchConfig; status: 'complete'|'infeasible'|'exhausted'; message: string; tickets: Ticket[]; budget: number; attempts: number; matched_count: number; note: string };
export type SavedResearch = { id: string; created_at: string; result: ResearchResult };
type Storage = Pick<globalThis.Storage, 'getItem'|'setItem'>;
const KEY='lottery-research-v1';
export function loadResearch(storage: Storage): SavedResearch[] {
  const raw=storage.getItem(KEY);if (!raw) return [];
  const records=JSON.parse(raw);
  if (!Array.isArray(records) || !records.every(r => typeof r?.id==='string' && typeof r.created_at==='string' && r.result?.version==='research-constraints-v1' && ['ssq','dlt'].includes(r.result.config?.game) && Number.isInteger(r.result.config.seed) && Number.isInteger(r.result.config.count) && Number.isInteger(r.result.config.pool_size) && r.result.config.front && r.result.config.back && ['complete','infeasible','exhausted'].includes(r.result.status) && typeof r.result.message==='string' && Array.isArray(r.result.tickets) && r.result.tickets.every((t: Ticket) => Array.isArray(t.front) && Array.isArray(t.back) && [...t.front,...t.back].every(Number.isInteger)))) throw new Error('本地研究记录格式异常，请先备份浏览器数据；没有覆盖旧记录。');
  return records;
}
export function saveResearch(storage: Storage, result: ResearchResult): SavedResearch[] {
  const records=[{id:crypto.randomUUID(),created_at:new Date().toISOString(),result},...loadResearch(storage)].slice(0,20);
  storage.setItem(KEY,JSON.stringify(records));return records;
}
export function removeResearch(storage: Storage, id: string): SavedResearch[] {
  const records=loadResearch(storage).filter(r=>r.id!==id);storage.setItem(KEY,JSON.stringify(records));return records;
}

export function parseConstraints(value: Record<string,string>): ZoneConstraints {
  const result: Record<string,number|number[]>={};
  for (const [key,raw] of Object.entries(value)) {
    if (!raw.trim()) continue;
    if (key==='thirds'||key==='fourths') {
      const parts=raw.trim().split(/[,，\s]+/);
      if (parts.length!==(key==='thirds'?3:4)||parts.some(v=>!/^\d+$/.test(v))) throw Error('分区请填写完整的非负整数数量，用逗号分隔。');
      result[key]=parts.map(Number);
    } else {
      if (!/^\d+$/.test(raw)) throw Error('约束必须为非负整数，留空表示不限。');
      result[key]=Number(raw);
    }
  }
  if (Object.values(result).flat().some(v=>!Number.isSafeInteger(v))) throw Error('约束数值过大，请填写有效的非负整数。');
  return result;
}
