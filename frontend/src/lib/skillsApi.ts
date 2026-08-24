export interface PublicSkill { slug: string; name: string; description: string; updated_at: string; official: boolean }
export interface PublicSkillDetail extends PublicSkill { content: string }
async function get<T>(url: string): Promise<T> { const response = await fetch(url); if (!response.ok) throw new Error((await response.json()).detail || `HTTP ${response.status}`); return response.json() as Promise<T>; }
export const getSkills = async () => (await get<{ skills: PublicSkill[] }>("/api/public/skills")).skills;
export const getSkill = (slug: string) => get<PublicSkillDetail>(`/api/public/skills/${encodeURIComponent(slug)}`);
