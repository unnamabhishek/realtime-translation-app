import { MutableRefObject, useEffect, useRef } from "react";

type Props = { audioRef: MutableRefObject<HTMLAudioElement | null>; height?: number };

// Lightweight plasma-like visual driven by the audio element's analyser.
export default function PlasmaVisualizer({ audioRef, height = 140 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const dataArrayRef = useRef<Uint8Array | null>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    let ctx: CanvasRenderingContext2D | null = canvas.getContext("2d");
    if (!ctx) return;

    let audioCtx: AudioContext | null = null;
    let source: MediaElementAudioSourceNode | MediaStreamAudioSourceNode | null = null;

    const resize = () => {
      const { clientWidth, clientHeight } = canvas;
      canvas.width = clientWidth * window.devicePixelRatio;
      canvas.height = clientHeight * window.devicePixelRatio;
      ctx = canvas.getContext("2d");
    };
    resize();
    window.addEventListener("resize", resize);

    const setupAnalyser = () => {
      const el = audioRef.current;
      if (!el) return;
      if (analyserRef.current) return;
      audioCtx = new AudioContext();
      if (el.captureStream) {
        const stream = el.captureStream();
        if (stream.getAudioTracks().length > 0) {
          source = audioCtx.createMediaStreamSource(stream);
        }
      }
      if (!source) {
        source = audioCtx.createMediaElementSource(el);
      }
      analyserRef.current = audioCtx.createAnalyser();
      analyserRef.current.fftSize = 64;
      analyserRef.current.smoothingTimeConstant = 0.8;
      source.connect(analyserRef.current);
      analyserRef.current.connect(audioCtx.destination);
      const bufferLength = analyserRef.current.frequencyBinCount;
      dataArrayRef.current = new Uint8Array(bufferLength);
    };

    const getEnergy = () => {
      if (!analyserRef.current || !dataArrayRef.current) return 0.12;
      analyserRef.current.getByteFrequencyData(dataArrayRef.current);
      const avg = dataArrayRef.current.reduce((sum, v) => sum + v, 0) / dataArrayRef.current.length;
      return avg / 255;
    };

    const draw = (ts: number) => {
      if (!ctx || !canvas) return;
      const t = ts / 1000;
      const energy = getEnergy();
      const width = canvas.width;
      const heightPx = canvas.height;

      const gradient = ctx.createLinearGradient(0, 0, 0, heightPx);
      gradient.addColorStop(0, "rgba(143, 160, 255, 0.25)");
      gradient.addColorStop(1, "rgba(96, 196, 255, 0.25)");
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, width, heightPx);

      const bands = 48;
      for (let y = 0; y < bands; y++) {
        const yPos = (y / bands) * heightPx;
        const phase = t * 1.2 + (y / bands) * Math.PI * 2;
        const wave = Math.sin(phase) * 0.5 + 0.5;
        const hue = 220 + wave * 40;
        const alpha = 0.08 + energy * 0.25;
        ctx.fillStyle = `hsla(${hue}, 100%, 70%, ${alpha})`;
        const xOffset = Math.sin(phase * 1.7) * 12 * energy;
        ctx.fillRect(xOffset, yPos, width - xOffset * 2, 2);
      }

      const dotCount = 26;
      const dotSpacing = width / (dotCount + 1);
      const dotY = heightPx * 0.65;
      const baseRadius = Math.max(4, Math.min(10, 6 + energy * 12));
      ctx.fillStyle = `rgba(110, 131, 255, ${0.45 + energy * 0.3})`;
      for (let i = 0; i < dotCount; i++) {
        const x = dotSpacing * (i + 1);
        const pulse = Math.sin(t * 3 + i * 0.6) * 0.5 + 0.5;
        const r = baseRadius * (0.9 + pulse * 0.3);
        ctx.beginPath();
        ctx.arc(x, dotY, r, 0, Math.PI * 2);
        ctx.fill();
      }

      rafRef.current = requestAnimationFrame(draw);
    };

    setupAnalyser();
    rafRef.current = requestAnimationFrame(draw);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      window.removeEventListener("resize", resize);
      analyserRef.current?.disconnect();
      source?.disconnect();
      if (audioCtx) audioCtx.close();
    };
  }, [audioRef]);

  return (
    <div style={{ width: "100%", height, borderRadius: 12, overflow: "hidden", background: "linear-gradient(180deg, rgba(115,131,255,0.08) 0%, rgba(80,198,255,0.12) 100%)" }}>
      <canvas ref={canvasRef} style={{ width: "100%", height: "100%", display: "block" }} />
    </div>
  );
}
