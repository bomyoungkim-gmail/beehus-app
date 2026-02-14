import { useNavigate, useParams } from 'react-router-dom';
import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';

interface RunData {
    id: string;
    status: string;
    logs: string[];
    error_summary?: string;
    connector?: string;
    vnc_url?: string;
}

export default function LiveView() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [run, setRun] = useState<RunData | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const [logsCollapsed, setLogsCollapsed] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Poll for Run Data
  useEffect(() => {
    if (!runId) {
        setError("Run ID is missing.");
        return;
    }

    const fetchRun = async () => {
        try {
            // Fetch run details
            const runRes = await axios.get(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/runs/${runId}`);
            setRun(runRes.data);
            setLogs(runRes.data.logs || []);
        } catch (err) {
            console.error("Error fetching run:", err);
            if (axios.isAxiosError(err) && err.response?.status === 401) {
                logout();
                navigate('/login');
            } else {
                setError("Failed to load run details");
            }
        }
    };

    fetchRun(); // Initial fetch

    const interval = setInterval(async () => {
        try {
            const pollRes = await axios.get(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/runs/${runId}`);
            setRun(pollRes.data);
            setLogs(pollRes.data.logs || []);
            if (['success', 'failed'].includes(pollRes.data.status)) {
                clearInterval(interval);
            }
        } catch (err) {
            console.error("Error polling run:", err);
            if (axios.isAxiosError(err) && err.response?.status === 401) {
                logout();
                navigate('/login');
            }
            // Don't set global error for polling, just log
        }
    }, 2000);

    return () => clearInterval(interval);
  }, [runId, navigate, logout]);

  // Scroll to bottom of logs
  useEffect(() => {
      if (logsEndRef.current) {
          logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
      }
  }, [logs]);



  // The original code did not have a Layout component.
  // For this to be syntactically correct, I'm wrapping the content directly.
  // If `Layout` is a custom component, it needs to be imported or defined.
  if (error) return (
      <div className="p-8 text-red-400">{error}</div>
  );

  if (!run) return (
      <div className="p-8 text-slate-400">Loading run details...</div>
  );

  const isLocalEvasion = run?.connector?.includes('jpmorgan');
  const baseUrl = import.meta.env.VITE_VNC_URL_BASE || 'http://localhost';
  const vncPassword = import.meta.env.VITE_VNC_PASSWORD || 'secret';

  const fallbackVncPort = isLocalEvasion ? '7901' : null; // Local worker only
  const fallbackVncUrl = fallbackVncPort
      ? `${baseUrl}:${fallbackVncPort}/?autoconnect=true&resize=scale&password=${vncPassword}`
      : null;

  const runVncUrl = run?.vnc_url ? `${run.vnc_url}/?autoconnect=true&resize=scale&password=${vncPassword}` : null;
  const vncUrl = runVncUrl || fallbackVncUrl;
  const fullVncUrl = import.meta.env.VITE_VNC_URL || vncUrl || undefined;

  const vncPort = (() => {
    try {
      return new URL(vncUrl || '').port || fallbackVncPort || '';
    } catch {
      return fallbackVncPort || '';
    }
  })();

  return (
    <div className="flex flex-col h-screen bg-black/50 backdrop-blur-3xl">
         {/* Header */}
         <header className="h-16 glass border-b border-dark-border flex items-center justify-between px-6 sticky top-0 z-10">
            <div className="flex items-center space-x-4">
                <button onClick={() => navigate(-1)} className="text-slate-400 hover:text-white transition-colors">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
                </button>
                <div>
                    <div className="flex items-center space-x-3">
                        <h1 className="text-xl font-bold text-white">Job Execution</h1>
                        <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wider ${
                            run.status === 'running' ? 'bg-brand-500/20 text-brand-400 animate-pulse' : 
                            run.status === 'success' ? 'bg-green-500/20 text-green-400' :
                            run.status === 'failed' ? 'bg-red-500/20 text-red-400' :
                            'bg-yellow-500/20 text-yellow-400'
                        }`}>
                            {run.status === 'running' ? 'LIVE' : run.status}
                        </span>
                    </div>
                    <p className="text-xs text-slate-400 font-mono mt-0.5">Run ID: {run.id}</p>
                </div>
            </div>
            <div className="flex items-center space-x-3">
                <a 
                    href={fullVncUrl} 
                    target="_blank" 
                    rel="noreferrer"
                    className={`text-xs ${fullVncUrl ? 'text-brand-500 hover:underline' : 'text-slate-500 cursor-not-allowed'}`}
                    onClick={(event) => {
                      if (!fullVncUrl) {
                        event.preventDefault();
                      }
                    }}
                >
                    Open Full VNC
                </a>
            </div>
        </header>

        <div className="flex h-[calc(100vh-64px)]">
            {/* Logs Sidebar */}
            <div className={`${logsCollapsed ? 'w-12 min-w-[3rem]' : 'w-1/3 min-w-[350px]'} border-r border-dark-border bg-dark-surface/50 flex flex-col transition-all duration-300 relative`}>
                
                {/* Toggle Button */}
                <button 
                    onClick={() => setLogsCollapsed(!logsCollapsed)}
                    className="absolute -right-3 top-2 w-6 h-6 bg-dark-surface border border-dark-border rounded-full flex items-center justify-center text-slate-400 hover:text-white hover:border-brand-500 transition-all z-20 shadow-lg"
                    title={logsCollapsed ? "Expand Logs" : "Collapse Logs"}
                >
                     <svg className={`w-3 h-3 transition-transform duration-300 ${logsCollapsed ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7"></path></svg>
                </button>

                {/* Header */}
                <div className="p-3 bg-dark-surface/80 text-xs font-semibold text-slate-400 uppercase tracking-wider border-b border-dark-border flex justify-between items-center h-12">
                    {!logsCollapsed && (
                        <>
                            <span>Execution Logs</span>
                            <span className="text-brand-500">{logs.length} lines</span>
                        </>
                    )}
                    {logsCollapsed && (
                        <div className="w-full flex justify-center">
                            <span className="text-brand-500 text-[10px]">{logs.length}</span>
                        </div>
                    )}
                </div>

                {/* Log Content */}
                {!logsCollapsed && (
                    <div className="flex-1 overflow-y-auto p-4 space-y-1 font-mono text-xs font-medium text-slate-300">
                        {logs.length === 0 ? (
                            <div className="text-slate-500 italic text-center mt-10">Waiting for logs...</div>
                        ) : (
                            logs.map((log, i) => (
                                <div key={i} className="hover:bg-white/5 px-2 py-0.5 rounded border-l-2 border-transparent hover:border-brand-500 break-words whitespace-pre-wrap">
                                    {log}
                                </div>
                            ))
                        )}
                        <div ref={logsEndRef} />
                    </div>
                )}
                
                {/* Collapsed Vertical Text */}
                {logsCollapsed && (
                    <div className="flex-1 flex items-center justify-center">
                        <div className="transform -rotate-90 whitespace-nowrap text-xs font-bold text-slate-500 uppercase tracking-widest">
                            Execution Logs
                        </div>
                    </div>
                )}
            </div>

            {/* Main Content (Hybrid Stream) */}
            <div className="flex-1 bg-black relative flex flex-col justify-center items-center p-4">
                 
                 {/* Determine VNC URL based on connector (Hybrid Architecture) */}
                 {(() => {
                    return (
                        <>
                        <div className="w-full h-full bg-slate-900 rounded-lg overflow-hidden border border-slate-700 shadow-2xl relative">
                        {vncUrl ? (
                            <iframe 
                                src={vncUrl} 
                                className="w-full h-full border-0"
                                title={isLocalEvasion ? "Local Worker VNC" : "Selenium Grid VNC"}
                                allowFullScreen
                            />
                        ) : (
                            <div className="w-full h-full flex items-center justify-center text-slate-500 text-sm">
                                VNC indisponível: aguardando URL do node
                            </div>
                        )}
                            
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
                            Viewing: <span className="text-brand-400 font-bold">{isLocalEvasion ? 'Worker Display (Local Evasion)' : 'Selenium Grid (Standard)'}</span>{vncPort ? ` • Port ${vncPort}` : ''}
                         </p>
                         </>
                    );
                 })()}
        </div>
    </div>
    </div>
  );
}
