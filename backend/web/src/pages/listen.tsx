import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useState } from "react";
import AudioPlayer from "../components/AudioPlayer";

const LANGUAGE_LABELS: Record<string, string> = { "hi-IN": "Hindi" };

export default function ListenPage() {
  const router = useRouter();
  const isReady = router.isReady;
  const { query } = router;
  const [targetState, setTargetState] = useState("hi-IN");
  const session = useMemo(() => {
    if (typeof query.session === "string") return query.session;
    if (typeof query.session_id === "string") return query.session_id;
    return "";
  }, [query.session, query.session_id]);
  const target = useMemo(() => {
    if (typeof query.target === "string") return query.target;
    return targetState;
  }, [query.target, targetState]);
  const backendUrl = useMemo(() => (typeof query.backend === "string" ? query.backend : "http://localhost:8080"), [query.backend]);
  const title = "Live talk stream";
  const targetName = LANGUAGE_LABELS[target] ?? target;

  useEffect(() => {
    if (typeof query.target === "string") setTargetState(query.target);
  }, [query.target]);

  const handleChangeTarget = (value: string) => {
    setTargetState(value);
    const params = { ...query, target: value };
    router.replace({ pathname: router.pathname, query: params }, undefined, { shallow: true });
  };

  if (!isReady) {
    return null;
  }

  if (!session) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "linear-gradient(145deg, #eef1ff 0%, #f8fbff 100%)", fontFamily: "'Inter', system-ui, sans-serif", padding: 24 }}>
        <div style={{ background: "#fff", border: "1px solid #e4e8f5", borderRadius: 16, padding: 24, maxWidth: 520, width: "100%", boxShadow: "0 12px 40px rgba(37, 51, 126, 0.12)" }}>
          <div style={{ fontWeight: 700, fontSize: 20, color: "#161c3d", marginBottom: 8 }}>Session missing</div>
          <p style={{ margin: "0 0 18px", color: "#56628a" }}>Add <code>session</code> (or <code>session_id</code>) and <code>target</code> in the URL, or go back to join a stream.</p>
          <Link href="/" style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "10px 14px", borderRadius: 10, background: "linear-gradient(120deg,#5c6bff,#6ad2ff)", color: "#fff", fontWeight: 700, textDecoration: "none", boxShadow: "0 8px 24px rgba(92,107,255,0.3)" }}>
            ← Back to join
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "radial-gradient(circle at 15% 20%, #f6f8ff 0%, #eef2ff 35%, #f7fbff 80%)", fontFamily: "'Inter', system-ui, sans-serif", padding: "36px 22px" }}>
      <div style={{ maxWidth: 1100, margin: "0 auto", display: "grid", gap: 18 }}>
        <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div>
            <h1 style={{ margin: "6px 0 6px", fontSize: 28, color: "#141932" }}>{title}</h1>
            <div style={{ display: "flex", gap: 10, alignItems: "center", color: "#5d678e", fontSize: 14, flexWrap: "wrap" }}>
              <span style={{ padding: "6px 10px", borderRadius: 10, background: "rgba(91,202,255,0.12)", color: "#0c86b8", fontWeight: 700 }}>Target {targetName}</span>
              <div style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "6px 8px", borderRadius: 10, background: "#f0f3ff", border: "1px solid #d8def4" }}>
                <label htmlFor="target-select" style={{ fontSize: 12, color: "#4a5170", fontWeight: 600 }}>Change language</label>
                <select id="target-select" value={target} onChange={(e) => handleChangeTarget(e.target.value)} style={{ padding: "6px 10px", borderRadius: 8, border: "1px solid #d6ddf3", background: "#fff", fontWeight: 600 }}>
                  <option value="hi-IN">Hindi</option>
                </select>
              </div>
            </div>
          </div>
          <Link href="/" style={{ padding: "10px 14px", borderRadius: 10, background: "#f0f3ff", color: "#3c4363", fontWeight: 700, border: "1px solid #d8def4", textDecoration: "none" }}>
            Change session
          </Link>
        </header>

        <div style={{ borderRadius: 20, padding: 18, background: "linear-gradient(130deg, rgba(92,107,255,0.08), rgba(107,210,255,0.08))", border: "1px solid rgba(92,107,255,0.18)" }}>
          <AudioPlayer session={session} target={target} backendUrl={backendUrl} />
        </div>
      </div>
    </div>
  );
}
