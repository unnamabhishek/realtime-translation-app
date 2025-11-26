import { useEffect, useMemo, useRef, useState } from "react";

type ChunkMeta = { chunk_id: string; text: string; timestamp: number };
type Props = { session: string; target: string; backendUrl: string };

export default function AudioPlayer({ session, target, backendUrl }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const metaRef = useRef<ChunkMeta | null>(null);
  const [status, setStatus] = useState("idle");
  const [chunks, setChunks] = useState<ChunkMeta[]>([]);
  const [activeChunk, setActiveChunk] = useState<string | null>(null);
  const [currentAudioChunk, setCurrentAudioChunk] = useState<string | null>(null);
  const [waveform, setWaveform] = useState<number[]>(() => new Array(20).fill(0.1));
  const analyserRef = useRef<AnalyserNode | null>(null);
  const rafRef = useRef<number | null>(null);

  // Init analyser once to animate waveform from the audio element.
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const ctx = new AudioContext();
    const source = ctx.createMediaElementSource(audio);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 64;
    analyser.smoothingTimeConstant = 0.85;
    source.connect(analyser);
    analyser.connect(ctx.destination);
    analyserRef.current = analyser;
    const freq = new Uint8Array(analyser.frequencyBinCount);
    const BAR_COUNT = 20;
    const update = () => {
      analyser.getByteFrequencyData(freq);
      const slice = Math.max(1, Math.floor(freq.length / BAR_COUNT));
      const values = new Array(BAR_COUNT).fill(0).map((_, i) => {
        const start = i * slice;
        const window = freq.slice(start, start + slice);
        const avg = window.reduce((acc, v) => acc + v, 0) / Math.max(1, window.length) / 255;
        return avg;
      });
      setWaveform(values);
      rafRef.current = requestAnimationFrame(update);
    };
    update();
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      source.disconnect();
      analyser.disconnect();
      ctx.close();
    };
  }, []);

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
      audioRef.current.src = URL.createObjectURL(blob);
      audioRef.current.play().catch((err) => {
        console.error("audio play failed", err);
        setStatus("play-error");
      });
      setActiveChunk(chunkId);
    };
    return () => ws.close();
  }, [backendUrl, session, target]);

  // When audio actually starts playing, update that chunk's timestamp to the playback start time.
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const handlePlay = () => {
      if (!currentAudioChunk) return;
      const playedAt = Date.now();
      setChunks((prev) =>
        prev.map((chunk) => (chunk.chunk_id === currentAudioChunk ? { ...chunk, timestamp: playedAt } : chunk))
      );
    };
    audio.addEventListener("play", handlePlay);
    return () => audio.removeEventListener("play", handlePlay);
  }, [currentAudioChunk]);

  const orderedChunks = useMemo(() => [...chunks].reverse(), [chunks]);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(320px, 380px) 1fr", gap: 16, width: "100%" }}>
      <div style={{ border: "1px solid #eceff7", borderRadius: 12, padding: 16, background: "#f7f9ff" }}>
        <p style={{ margin: "0 0 8px", color: "#6a6f86", fontSize: 13 }}>Live audio</p>
        <audio ref={audioRef} autoPlay controls style={{ width: "100%" }} />
        <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 120, marginTop: 12 }}>
          {waveform.map((v, i) => (
            <span key={i} style={{ flex: 1, height: `${Math.max(10, v * 100)}%`, borderRadius: 4, background: "linear-gradient(180deg,#9cadff 0%,#7284ff 100%)", opacity: activeChunk ? 1 : 0.6 }} />
          ))}
        </div>
        <div style={{ fontSize: 12, color: "#555", marginTop: 6 }}>
          Status: {status} {activeChunk ? `| chunk: ${activeChunk}` : ""}
        </div>
      </div>

      <div style={{ border: "1px solid #eceff7", borderRadius: 12, padding: 12, background: "#fdfdff", display: "flex", flexDirection: "column", gap: 8, minHeight: 240, maxHeight: 420, overflow: "hidden" }}>
        <div style={{ padding: "4px 8px", borderBottom: "1px solid #eceff7", color: "#6a6f86", fontSize: 14 }}>Transcript</div>
        <div style={{ overflowY: "auto", display: "flex", flexDirection: "column", gap: 8, padding: "0 4px 8px", flex: 1 }}>
          {orderedChunks.length === 0 && <div style={{ color: "#999db8", fontStyle: "italic" }}>Waiting for audio…</div>}
          {orderedChunks.map((chunk) => {
            const isActive = chunk.chunk_id === activeChunk;
            return (
              <div
                key={chunk.chunk_id}
                style={{
                  border: `1px solid ${isActive ? "rgba(90,107,255,0.6)" : "rgba(90,107,255,0.12)"}`,
                  background: isActive ? "#eef1ff" : "#fff",
                  boxShadow: isActive ? "0 6px 24px rgba(90,107,255,0.2)" : "0 1px 4px rgba(16,24,40,0.05)",
                  borderRadius: 10,
                  padding: 10,
                }}
              >
                <div style={{ fontSize: 12, color: "#6d7085", marginBottom: 4 }}>
                  {new Date(chunk.timestamp).toLocaleTimeString()} • {chunk.chunk_id}
                </div>
                <div style={{ fontSize: 15, color: "#1f2233", lineHeight: 1.4 }}>{chunk.text || "(no text)"}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
