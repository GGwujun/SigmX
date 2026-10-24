/**
 * 内容页通用壳：复用聊天工作台的 AIAnalysisShell（ChatGPT 式 288px 左栏网格），
 * 左侧导航常驻、右侧滚动承载页面本体——情报搜索/全球事件等不再回到「顶栏 +
 * 上下堆叠」的旧布局，与用户第五轮要求一致。
 */
import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { AIAnalysisShell } from "@/components/public/AIAnalysisShell";
import { listResearchTasks, type ResearchTask } from "@/lib/researchApi";
import { isAuthenticated } from "@/lib/apiAuth";

interface Props { children: ReactNode }

export function PublicAppShell({ children }: Props) {
  const navigate = useNavigate();
  const [recentTasks, setRecentTasks] = useState<ResearchTask[]>([]);
  useEffect(() => {
    // 已登录用户在内容页也能看到并跳转最近对话；匿名静默跳过。
    if (isAuthenticated()) listResearchTasks(20).then(setRecentTasks).catch(() => undefined);
  }, []);
  return <AIAnalysisShell recentTasks={recentTasks} activeTaskId={null} onNewAnalysis={() => navigate("/")}>
    {/* 移动端汉堡钮（absolute left-3 top-3，占顶部约 48px）悬浮在内容区左上，
        内容页自带的上内边距不够避开，统一让出顶部空间防标题首字被压。 */}
    <div className="min-h-0 flex-1 overflow-y-auto pt-14 lg:pt-0">{children}</div>
  </AIAnalysisShell>;
}
