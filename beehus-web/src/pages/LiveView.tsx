import { useNavigate, useParams } from 'react-router-dom';
import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';

interface RunData {
    id: str;
    status: str;
    logs: string[];
    error_summary?: string;
}

export default function LiveView() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [run, setRun] = useState<RunData | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Poll for Run Data
  useEffect(() => {
    if (!runId) return;

    const fetchRun = async () => {
        try {
            // Using localhost:8000 directly for now (should vary by env)
            const response = await axios.get(`http://localhost:8000/runs/${runId}`);
            setRun(response.data);
        } catch (err) {
            console.error("Failed to fetch run", err);
            if (axios.isAxiosError(err) && err.response?.status === 401) {
                logout();
                navigate('/login');
            }
        }
    };

    fetchRun(); // Initial fetch
    const interval = setInterval(fetchRun, 2000); // Poll every 2s

    return () => clearInterval(interval);
  }, [runId, navigate, logout]);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [run?.logs]);

  return (
    <div className="flex flex-col h-screen bg-black/50 backdrop-blur-3xl">
        {/* Toolbar */}
        <div className="h-16 border-b border-dark-border flex items-center justify-between px-6 bg-dark-bg/80 shrink-0">
            <div className="flex items-center space-x-4">
                <button onClick={() => navigate('/')} className="text-slate-400 hover:text-white transition-colors">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7"></path></svg>
                </button>
                <div>
                    <h2 className="font-bold text-white flex items-center">
                        Job Execution <span className="ml-3 px-2 py-0.5 rounded text-xs bg-brand-500 text-white">LIVE</span>
                    </h2>
                    <p className="text-xs text-brand-400 font-mono">Run ID: {runId}</p>
                </div>
            </div>
            <div className="flex items-center space-x-3">
                <span className="text-xs text-slate-400 flex items-center">
                    <span className={`w-2 h-2 rounded-full mr-2 ${run?.status === 'running' ? 'bg-green-500 animate-pulse' : 'bg-slate-500'}`}></span>
                    {run?.status?.toUpperCase() || 'CONNECTING...'}
                </span>
                <div className="h-6 w-px bg-white/10 mx-2"></div>
                {/* VNC Link hint */}
                <a 
                    href="http://localhost:7900" 
                    target="_blank" 
                    rel="noreferrer"
                    className="text-xs text-brand-500 hover:underline"
                >
                    Open Full VNC
                </a>
            </div>
        </div>

        {/* Split View */}
        <div className="flex-1 flex overflow-hidden">
            {/* Logs Panel (Left) */}
            <div className="w-1/3 border-r border-dark-border bg-dark-surface/50 flex flex-col min-w-[300px]">
                <div className="p-3 bg-dark-surface/80 text-xs font-semibold text-slate-400 uppercase tracking-wider border-b border-dark-border flex justify-between">
                    <span>Execution Logs</span>
                    <span className="text-brand-500">{run?.logs?.length || 0} lines</span>
                </div>
                <div className="flex-1 overflow-y-auto p-4 space-y-1 font-mono text-xs font-medium text-slate-300">
                    {run?.logs?.length === 0 && (
                        <div className="text-slate-500 italic">Waiting for logs...</div>
                    )}
                    {run?.logs?.map((log, idx) => (
                        <div key={idx} className="hover:bg-white/5 px-2 py-0.5 rounded border-l-2 border-transparent hover:border-brand-500 break-words whitespace-pre-wrap">
                            {log}
                        </div>
                    ))}
                    <div ref={logsEndRef} />
                </div>
            </div>

            {/* Browser Viewport (Right) */}
            <div className="flex-1 bg-black relative flex flex-col justify-center items-center p-4">
                 
                 <div className="w-full h-full bg-slate-900 rounded-lg overflow-hidden border border-slate-700 shadow-2xl relative">
                    {/* VNC Iframe */}
                    {/* Pointing to localhost:7900 (noVNC default port exposed from docker) */}
                    <iframe 
                        src="http://localhost:7900/?autoconnect=true&resize=scale&password=secret" 
                        className="w-full h-full border-0"
                        title="Selenium VNC"
                        allowFullScreen
                    />
                    
                    {/* Overlay if not running */}
                    {run?.status !== 'running' && run?.status !== 'queued' && (
                        <div className="absolute inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-10 pointer-events-none">
                            <div className="text-center p-6 bg-dark-surface/90 rounded-xl border border-white/10 shadow-2xl">
                                <p className="text-xl font-bold text-white mb-2">Execution {run?.status}</p>
                                <p className="text-slate-400 text-sm">Session ended.</p>
                            </div>
                        </div>
                    )}
                 </div>

                 <p className="mt-2 text-xs text-slate-500">
                    Viewing Selenium Grid Node (Port 7900)
                 </p>
            </div>
        </div>
    </div>
  );
}
