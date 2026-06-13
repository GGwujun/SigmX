import { useState } from "react";
import { AlertTriangle, Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { setUser } from "@/lib/apiAuth";
import {
  DISCLAIMER_AGREE_LABEL, DISCLAIMER_BODY, DISCLAIMER_NOTE,
  DISCLAIMER_NOTE_TITLE, DISCLAIMER_TITLE,
} from "@/lib/disclaimer";

/**
 * Post-login disclaimer gate. Shown when the logged-in user has not yet
 * accepted the disclaimer. The user MUST click "我已阅读并同意" to proceed —
 * there is no dismiss/escape. On accept, PATCHes the user record and closes.
 */
export function DisclaimerModal({
  onAccepted,
}: {
  onAccepted: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);

  const accept = async () => {
    setSubmitting(true);
    try {
      const updated = await api.acceptDisclaimer();
      setUser(updated);
      toast.success("已确认免责声明");
      onAccepted();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "确认失败，请重试");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-lg rounded-xl border bg-card shadow-xl">
        <div className="flex items-center gap-2 border-b px-5 py-4">
          <AlertTriangle className="h-5 w-5 text-warning" />
          <h2 className="text-base font-semibold">{DISCLAIMER_TITLE}</h2>
        </div>

        <div className="max-h-[55vh] overflow-auto px-5 py-4 text-sm leading-relaxed text-muted-foreground">
          <p className="text-foreground">{DISCLAIMER_BODY}</p>
          <h3 className="mt-4 font-semibold text-foreground">{DISCLAIMER_NOTE_TITLE}</h3>
          <p className="mt-1">{DISCLAIMER_NOTE}</p>
        </div>

        <div className="border-t px-5 py-4">
          <button
            onClick={accept}
            disabled={submitting}
            className="w-full flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-40"
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
            {DISCLAIMER_AGREE_LABEL}
          </button>
        </div>
      </div>
    </div>
  );
}
