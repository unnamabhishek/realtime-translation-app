import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";

type ChunkMeta = { chunk_id: string; text: string; timestamp: number };

export default function Overlay() {
  const router = useRouter();
  const { query, isReady } = router;
  const session = useMemo(() => {
    if (typeof query.session === "string") return query.session;
    if (typeof query.session_id === "string") return query.session_id;
    return "";
  }, [query.session, query.session_id]);
  const target = useMemo(() => (typeof query.target === "string" ? query.target : "hi-IN"), [query.target]);
  const backendUrl = useMemo(() => (typeof query.backend === "string" ? query.backend : "http://localhost:8080"), [query.backend]);
  const [lastChunk, setLastChunk] = useState<ChunkMeta | null>(null);
  const [status, setStatus] = useState("idle");

  useEffect(() => {
    if (!session) return;
    const wsUrl = `${backendUrl.replace("http", "ws")}/out/${session}/${target}`;
    const ws = new WebSocket(wsUrl);
    setStatus("connecting");
    ws.onopen = () => setStatus("open");
    ws.onerror = () => setStatus("error");
    ws.onclose = () => setStatus("closed");
    ws.onmessage = (event) => {
      if (typeof event.data !== "string") return;
      const meta = JSON.parse(event.data);
      if (!meta.text) return;
      const ts = meta.timestamp ? Number(meta.timestamp) : Date.now();
      const chunkId = meta.chunk_id ?? meta.session_id ?? crypto.randomUUID();
      setLastChunk({ chunk_id: chunkId, text: meta.text, timestamp: ts });
    };
    return () => ws.close();
  }, [backendUrl, session, target]);

  if (!isReady || !session) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "transparent", color: "#fff", fontFamily: "'Inter', system-ui, sans-serif" }}>
        Waiting for session...
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "flex-end", justifyContent: "center", padding: "24px 32px", background: "transparent", color: "#fff", fontFamily: "'Inter', system-ui, sans-serif" }}>
      <div style={{ maxWidth: 1200, width: "100%", textAlign: "center", fontSize: 36, fontWeight: 700, lineHeight: 1.3, textShadow: "0 6px 24px rgba(0,0,0,0.45)" }}>
        {lastChunk?.text ?? (status === "open" ? "Listening…" : "Connecting…")}
      </div>
    </div>
  );
}
