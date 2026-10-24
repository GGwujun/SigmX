/**
 * 公开分享的对话（/s/:slug，匿名只读）：分享者点「分享」后任何持链接者可看。
 * 状态分支与 PublicReportPage 一致（410 已撤销 / 404 不存在 / error），视觉走
 * 聊天白净风；时间线只读复用 AIAnalysisTimeline（不出现重新生成按钮）。
 */
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { LoaderCircle } from "lucide-react";

import { SigmXLogo } from "@/components/brand/SigmXLogo";
import { AIAnalysisTimeline } from "@/components/public/AIAnalysisTimeline";
import { getPublicConversation, PublicConversationError, type SharedConversation } from "@/lib/researchApi";

type State =
  | { kind: "loading" }
  | { kind: "ready"; data: SharedConversation }
  | { kind: "revoked" }
  | { kind: "missing" }
  | { kind: "error" };

export function SharedConversationPage() {
  const { slug = "" } = useParams();
  const [state, setState] = useState<State>({ kind: "loading" });
  useEffect(() => {
    let cancelled = false;
    getPublicConversation(slug).then(
      data => { if (!cancelled) setState({ kind: "ready", data }); },
      (reason: unknown) => {
        if (cancelled) return;
        if (reason instanceof PublicConversationError && reason.status === 410) setState({ kind: "revoked" });
        else if (reason instanceof PublicConversationError && reason.status === 404) setState({ kind: "missing" });
        else setState({ kind: "error" });
      },
    );
    return () => { cancelled = true; };
  }, [slug]);

  return <div className="aiw flex min-h-dvh flex-col bg-white">
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-[#ececec] px-4 sm:px-6">
      <Link to="/" className="flex items-center gap-2 rounded-lg px-1 py-1 text-[15px] font-semibold text-[#0d0d0d]"><SigmXLogo className="h-[22px] w-[22px]" />SigmX</Link>
      <p className="text-[12.5px] text-[#8f8f8f]">公开分享的对话{state.kind === "ready" ? ` · ${new Date(state.data.created_at).toLocaleDateString()}` : ""}</p>
    </header>
    {state.kind === "loading" && <div className="flex flex-1 items-center justify-center gap-2 text-[14px] text-[#8f8f8f]"><LoaderCircle className="h-4 w-4 animate-spin" />正在打开分享的对话…</div>}
    {state.kind === "revoked" && <Notice title="该对话分享已撤销" body="分享者关闭了公开访问，原对话不再对外展示。" />}
    {state.kind === "missing" && <Notice title="未找到该分享" body="链接可能不完整或对话不存在。" />}
    {state.kind === "error" && <Notice title="对话暂时不可用" body="加载分享内容失败，请稍后重试。" />}
    {state.kind === "ready" && <>
      <main data-testid="shared-conversation" className="min-h-0 flex-1 overflow-y-auto pb-10">
        <AIAnalysisTimeline turns={state.data.turns} pendingQuestion="" planning={false} pendingError="" loadError="" />
      </main>
      <footer className="shrink-0 border-t border-[#ececec] px-5 py-5 text-center">
        <p className="text-[10.5px] leading-4 text-[#8f8f8f]">该对话由 SigmX 用户主动公开，仅供研究参考，不构成投资建议。</p>
        <Link to="/" className="mt-2.5 inline-flex h-9 items-center rounded-full bg-[#0d0d0d] px-4 text-[13px] font-medium text-white transition-opacity hover:opacity-90">用 SigmX 创建你自己的分析</Link>
      </footer>
    </>}
  </div>;
}

function Notice({ title, body }: { title: string; body: string }) {
  return <div className="mx-auto flex w-full max-w-[560px] flex-1 flex-col items-center justify-center px-6 text-center">
    <h1 className="text-[22px] font-semibold text-[#0d0d0d]">{title}</h1>
    <p className="mt-3 text-[13.5px] leading-6 text-[#8f8f8f]">{body}</p>
    <Link to="/" className="mt-6 inline-flex h-9 items-center rounded-full border border-[#d9d9e3] px-4 text-[13px] font-medium text-[#0d0d0d] transition-colors hover:bg-[#f3f3f3]">返回 SigmX 首页</Link>
  </div>;
}
