import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";

export default function Home() {
  const router = useRouter();
  const { query } = router;
  const [session, setSession] = useState("");
  const [target, setTarget] = useState("hi-IN");
  const [backendUrl, setBackendUrl] = useState("http://localhost:8080");

  useEffect(() => {
    if (typeof query.session === "string") setSession(query.session);
    if (typeof query.session_id === "string") setSession(query.session_id);
    if (typeof query.target === "string") setTarget(query.target);
    if (typeof query.backend === "string") setBackendUrl(query.backend);
    if (!query.backend && typeof window !== "undefined" && backendUrl === "http://localhost:8080") {
      const fromWindow = window.location.origin.replace(/:3000$/, ":8080");
      setBackendUrl(fromWindow);
    }
  }, [query]);

  const canJoin = useMemo(() => session.trim().length > 0, [session]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!canJoin) return;
    const params = new URLSearchParams();
    params.set("session", session.trim());
    params.set("target", target);
    params.set("backend", backendUrl.trim());
    router.push(`/listen?${params.toString()}`);
  };

  return (
    <div style={{ minHeight: "100vh", background: "radial-gradient(circle at 20% 20%, #f5f8ff, #eef1ff 35%, #e6ecff 60%, #f5f8ff 100%)", fontFamily: "'Inter', system-ui, -apple-system, sans-serif", display: "flex", alignItems: "center", justifyContent: "center", padding: "48px 20px" }}>
      <div style={{ width: "100%", maxWidth: 720, background: "#fff", border: "1px solid #e5e8f3", borderRadius: 18, boxShadow: "0 14px 50px rgba(82, 99, 255, 0.12)", padding: 28 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 26, color: "#16192c" }}>Join the talk</h1>
            <p style={{ margin: "8px 0 0", color: "#546078", maxWidth: 520 }}>Enter the session id from the invite link (or QR). Choose your language and jump straight into the stream.</p>
          </div>
          <div style={{ padding: "8px 12px", borderRadius: 12, background: "linear-gradient(120deg, rgba(114,132,255,0.1), rgba(129,214,255,0.1))", color: "#3f4b97", fontSize: 12, border: "1px dashed rgba(114,132,255,0.5)" }}>
            <div style={{ fontWeight: 600 }}>Heads up</div>
            <div>URL params are read automatically: <code>session</code>, <code>target</code>, <code>backend</code>.</div>
          </div>
        </div>

        <form onSubmit={handleSubmit} style={{ marginTop: 22, display: "grid", gap: 14 }}>
          <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
            <div style={{ display: "grid", gap: 6 }}>
              <label style={{ fontSize: 14, color: "#394161", fontWeight: 600 }}>Session ID</label>
              <input value={session} onChange={(e) => setSession(e.target.value)} placeholder="e.g. 7c6a0f2d-..." style={{ padding: "12px 14px", borderRadius: 12, border: "1px solid #d8ddf0", fontSize: 15, outline: "none", transition: "border-color 0.2s, box-shadow 0.2s" }} onFocus={(e) => { e.target.style.borderColor = "#6b7bff"; e.target.style.boxShadow = "0 0 0 3px rgba(107,123,255,0.2)"; }} onBlur={(e) => { e.target.style.borderColor = "#d8ddf0"; e.target.style.boxShadow = "none"; }} />
            </div>
            <div style={{ display: "grid", gap: 6 }}>
              <label style={{ fontSize: 14, color: "#394161", fontWeight: 600 }}>Target language</label>
              <select value={target} onChange={(e) => setTarget(e.target.value)} style={{ padding: "12px 14px", borderRadius: 12, border: "1px solid #d8ddf0", fontSize: 15, background: "#fff" }}>
                <option value="hi-IN">Hindi</option>
              </select>
            </div>
            <div style={{ display: "grid", gap: 6 }}>
              <label style={{ fontSize: 14, color: "#394161", fontWeight: 600 }}>Backend URL</label>
              <input value={backendUrl} onChange={(e) => setBackendUrl(e.target.value)} placeholder="http://localhost:8080" style={{ padding: "12px 14px", borderRadius: 12, border: "1px solid #d8ddf0", fontSize: 15 }} />
            </div>
          </div>

          <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            <button type="submit" disabled={!canJoin} style={{ padding: "12px 18px", borderRadius: 12, border: "none", background: canJoin ? "linear-gradient(120deg, #5c6bff, #6ad2ff)" : "#c7cee6", color: "#fff", fontWeight: 700, fontSize: 15, cursor: canJoin ? "pointer" : "not-allowed", boxShadow: canJoin ? "0 10px 30px rgba(92,107,255,0.35)" : "none", transition: "transform 0.1s ease, box-shadow 0.2s ease" }} onMouseDown={(e) => { if (canJoin) (e.target as HTMLButtonElement).style.transform = "translateY(1px)"; }} onMouseUp={(e) => { (e.target as HTMLButtonElement).style.transform = "translateY(0)"; }}>
              Join stream
            </button>
            <div style={{ fontSize: 13, color: "#6a7295" }}>You can open the invite link directly; session and language will prefill from URL params.</div>
          </div>
        </form>
      </div>
    </div>
  );
}
