import { useEffect, useMemo, useRef, useState } from "react";
import CircularWaveform from "./circular-waveform";

type ChunkMeta = { chunk_id: string; text: string; timestamp: number };
type Props = { session: string; target: string; backendUrl: string };

const LANGUAGE_LABELS: Record<string, string> = { "hi-IN": "Hindi" };

const MuteIcon = ({ muted }: { muted: boolean }) => {
  if (muted) {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M9 9v6l-2.5-2.5H4V11h2.5z" />
        <path d="m9 9 6-5v6" />
        <path d="M15 11v7" />
        <path d="m4 4 16 16" />
      </svg>
    );
  }
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9 9v6l-2.5-2.5H4V11h2.5z" />
      <path d="m9 9 6-5v16l-6-5" />
      <path d="M18 9a3 3 0 0 1 0 6" />
      <path d="M21 7a6 6 0 0 1 0 10" />
    </svg>
  );
};

export default function AudioPlayer({ session, target, backendUrl }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const metaRef = useRef<ChunkMeta | null>(null);
  const [status, setStatus] = useState("idle");
  const [chunks, setChunks] = useState<ChunkMeta[]>([]);
  const [activeChunk, setActiveChunk] = useState<string | null>(null);
  const [currentAudioChunk, setCurrentAudioChunk] = useState<string | null>(null);
  const [hasAudio, setHasAudio] = useState(false);
  const [muted, setMuted] = useState(false);
  const [connectionMeta, setConnectionMeta] = useState<string | null>(null);
  const targetName = LANGUAGE_LABELS[target] ?? target;

  useEffect(() => {
    if (!session) {
      setStatus("no-session");
      return;
    }
    const wsUrl = `${backendUrl.replace("http", "ws")}/out/${session}/${target}`;
    const ws = new WebSocket(wsUrl);
    setStatus("connecting");
    ws.onopen = () => setStatus("open");
    ws.onerror = (e) => {
      console.error("ws error", e);
      setStatus("error");
    };
    ws.onclose = () => setStatus("closed");
    ws.onmessage = async (event) => {
      if (typeof event.data === "string") {
        try {
          const meta = JSON.parse(event.data);
          const ts = meta.timestamp ? Number(meta.timestamp) : Date.now();
          const chunkId = meta.chunk_id ?? meta.session_id ?? crypto.randomUUID();
          metaRef.current = { chunk_id: chunkId, text: meta.text ?? "", timestamp: ts };
          if (meta.text) {
            setChunks((prev) => [...prev.slice(-50), metaRef.current as ChunkMeta]);
            setActiveChunk(chunkId);
          }
          if (meta.sample_rate) setConnectionMeta(`${targetName} • ${meta.sample_rate} Hz`);
        } catch {
          /* ignore non-JSON text */
        }
        return;
      }

      setStatus("receiving");
      const arrayBuffer = await (event.data as Blob).arrayBuffer();
      const blob = new Blob([arrayBuffer], { type: "audio/wav" });
      if (!audioRef.current) return;
      const chunkId = metaRef.current?.chunk_id ?? crypto.randomUUID();
      setCurrentAudioChunk(chunkId);
      setHasAudio(true);
      audioRef.current.src = URL.createObjectURL(blob);
      audioRef.current.play().catch((err) => {
        console.error("audio play failed", err);
        setStatus("play-error");
      });
      setActiveChunk(chunkId);
    };
    return () => ws.close();
  }, [backendUrl, session, target, targetName]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.muted = muted;
  }, [muted]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const handlePlay = () => {
      if (!currentAudioChunk) return;
      const playedAt = Date.now();
      setChunks((prev) => prev.map((chunk) => (chunk.chunk_id === currentAudioChunk ? { ...chunk, timestamp: playedAt } : chunk)));
    };
    audio.addEventListener("play", handlePlay);
    return () => audio.removeEventListener("play", handlePlay);
  }, [currentAudioChunk]);

  const orderedChunks = useMemo(() => [...chunks].reverse(), [chunks]);
  const statusLabel = useMemo(() => {
    if (status === "connecting") return "Connecting…";
    if (status === "open") return hasAudio ? "Live" : "Connected — waiting for session to start";
    if (status === "receiving") return "Receiving audio";
    if (status === "error") return "Connection error";
    if (status === "closed") return "Disconnected";
    if (status === "play-error") return "Audio playback blocked";
    if (status === "no-session") return "Enter a session id to start";
    return status;
  }, [hasAudio, status]);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(320px, 400px) 1fr", gap: 18, width: "100%", alignItems: "stretch" }}>
      <div style={{ border: "1px solid #dde6ff", borderRadius: 16, padding: 16, background: "linear-gradient(180deg, #f3f6ff 0%, #eef3ff 100%)", boxShadow: "0 12px 40px rgba(93, 112, 255, 0.14)", minHeight: 460, height: 520 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <div style={{ color: "#4f5676", fontSize: 13, fontWeight: 700, textTransform: "uppercase" }}>Live audio</div>
          <span style={{ padding: "6px 10px", borderRadius: 10, background: hasAudio ? "rgba(76,190,120,0.12)" : "rgba(255,184,97,0.16)", color: hasAudio ? "#208654" : "#b6791b", fontSize: 12, fontWeight: 600 }}>{statusLabel}</span>
        </div>
        <div style={{ border: "1px solid #dee5ff", borderRadius: 12, padding: 12, background: "#fff", display: "flex", flexDirection: "column", gap: 10 }}>
          <audio ref={audioRef} autoPlay controls style={{ width: "100%", borderRadius: 10 }} />
          <div style={{ display: "flex", gap: 10, alignItems: "center", justifyContent: "space-between" }}>
            <button aria-label={muted ? "Unmute audio" : "Mute audio"} onClick={() => setMuted((prev) => !prev)} style={{ padding: "10px 12px", borderRadius: 12, border: "1px solid #d9def0", background: "#f7f8ff", color: "#27304f", fontWeight: 700, cursor: "pointer", boxShadow: "0 6px 16px rgba(31,49,110,0.08)", display: "inline-flex", alignItems: "center", gap: 8 }}>
              <MuteIcon muted={muted} />
              <span>{muted ? "Muted" : "Mute"}</span>
            </button>
            <div style={{ fontSize: 12, color: "#5d6688" }}>{connectionMeta ?? `${targetName}`}</div>
          </div>
        </div>
        <CircularWaveform audioRef={audioRef} size={240} />
      </div>

      <div style={{ border: "1px solid #dde6ff", borderRadius: 16, padding: 16, background: "linear-gradient(180deg, #f3f6ff 0%, #eef3ff 100%)", boxShadow: "0 12px 40px rgba(31, 49, 110, 0.08)", display: "flex", flexDirection: "column", gap: 10, minHeight: 460, height: 520, maxHeight: 520, overflow: "hidden" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ padding: "6px 10px", borderRadius: 10, background: "#f6f7ff", color: "#5d678a", fontWeight: 700, fontSize: 13 }}>Live transcript</div>
          <span style={{ fontSize: 12, color: "#7b84a7" }}>{hasAudio ? "Streaming" : "Listening"}</span>
        </div>
        <div style={{ overflowY: "auto", display: "flex", flexDirection: "column", gap: 10, padding: "0 4px 8px", flex: 1, minHeight: 0 }}>
          {orderedChunks.length === 0 && (
            <div style={{ color: "#96a1c7", fontStyle: "italic", background: "#f8f9ff", border: "1px dashed #d8def7", borderRadius: 12, padding: 12 }}>
              Waiting for session to start. You are subscribed and will hear the stream as soon as it begins.
            </div>
          )}
          {orderedChunks.map((chunk, idx) => {
            const isActive = chunk.chunk_id === activeChunk;
            const label = `Segment ${orderedChunks.length - idx}`;
            return (
              <div key={chunk.chunk_id} style={{ border: `1px solid ${isActive ? "rgba(92,107,255,0.6)" : "#e6eaf8"}`, background: isActive ? "linear-gradient(180deg,#f3f4ff 0%,#eef2ff 100%)" : "#fff", boxShadow: isActive ? "0 10px 24px rgba(92,107,255,0.18)" : "0 6px 16px rgba(31,49,110,0.05)", borderRadius: 12, padding: 12 }}>
                <div style={{ fontSize: 12, color: "#6d7594", marginBottom: 4 }}>
                  {label} • {new Date(chunk.timestamp).toLocaleTimeString()}
                </div>
                <div style={{ fontSize: 15, color: "#15192c", lineHeight: 1.5 }}>{chunk.text || "(no text)"}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
