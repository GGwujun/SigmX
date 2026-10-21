export interface PublicSkill {
  slug: string;
  name: string;
  description: string;
  updated_at: string;
  official: boolean;
  ownership: "official" | "adapted" | "third_party" | "community";
  ownership_label: string;
  execution: "executable" | "instructional";
  primary_source: "data_hub" | "public_source" | "user_source" | "none";
  primary_source_label: string;
  datahub_endpoints: string[];
  fallback_sources: string[];
  markets: string[];
  credential_required: boolean;
  capability_status: "full" | "partial" | "instructional";
}
export interface PublicSkillDetail extends PublicSkill { content: string }
async function get<T>(url: string): Promise<T> { const response = await fetch(url); if (!response.ok) throw new Error((await response.json()).detail || `HTTP ${response.status}`); return response.json() as Promise<T>; }
export const getSkills = async () => (await get<{ skills: PublicSkill[] }>("/api/public/skills")).skills;
export const getSkill = (slug: string) => get<PublicSkillDetail>(`/api/public/skills/${encodeURIComponent(slug)}`);
