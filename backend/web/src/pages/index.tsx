import { useState } from "react";
import AudioPlayer from "../components/AudioPlayer";

export default function Home() {
  const [session, setSession] = useState("");
  const [target, setTarget] = useState("hi-IN");
  const [backendUrl, setBackendUrl] = useState("http://localhost:8080");

  return (
    <div style={{ padding: 24, fontFamily: "Inter, sans-serif" }}>
      <h3>Realtime Translate</h3>
      <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
        <input placeholder="Session ID" value={session} onChange={(e) => setSession(e.target.value)} />
        <input placeholder="Backend URL" value={backendUrl} onChange={(e) => setBackendUrl(e.target.value)} />
        <select value={target} onChange={(e) => setTarget(e.target.value)}>
          <option value="hi-IN">Hindi</option>
          <option value="mr-IN">Marathi</option>
        </select>
      </div>
      {session && <AudioPlayer session={session} target={target} backendUrl={backendUrl} />}
      {!session && <div>Enter a session id to start listening.</div>}
    </div>
  );
}
