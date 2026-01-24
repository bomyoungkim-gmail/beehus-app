import { useEffect, useState } from 'react';
import Layout from '../components/Layout';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { useToast } from '../context/ToastContext';

interface Run {
    run_id: string;
    job_id: string;
    connector: string;
    status: string;
    report_date?: string;
    history_date?: string;
    node: string;
    created_at?: string;
}

export default function Runs() {
    const [runs, setRuns] = useState<Run[]>([]);
    const [loading, setLoading] = useState(true);
    const [stoppingRunId, setStoppingRunId] = useState<string | null>(null);
    const { showToast } = useToast();

    useEffect(() => {
        let isMounted = true;
        let ws: WebSocket | null = null;
        let retryCount = 0;
        const maxRetries = 5;

        // Fetch initial state
        const fetchRuns = async () => {
            try {
                const res = await axios.get(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/dashboard/recent-runs?limit=100`);
                if (isMounted) {
                    setRuns(res.data);
                    setLoading(false);
                }
            } catch (error) {
                console.error('Failed to fetch runs:', error);
                if (isMounted) {
                    setLoading(false);
                }
            }
        };

        const connectWebSocket = () => {
            const wsUrl = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace('http', 'ws') + '/ws/runs';
            ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                console.log('✅ Connected to Real-time Run Updates');
                retryCount = 0; // Reset retries on success
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    // Update state if run exists
                    setRuns(prevRuns => {
                        return prevRuns.map(run => {
                           if (run.run_id === data.run_id) {
                               return { 
                                   ...run, 
                                   status: data.status,
                                   // Update node if provided
                                   ...(data.node && { node: data.node })
                               };
                           }
                           
                           // If it's a new run creation event (not yet in list), we could add it
                           // For now, let's just update existing ones to be safe
                           return run;
                        });
                    });
                } catch (e) {
                    console.error('Failed to parse WS message:', e);
                }
            };
            
            ws.onclose = () => {
                console.log('🔴 WebSocket Disconnected');
                // Simple exponential backoff for reconnection
                if (isMounted && retryCount < maxRetries) {
                    const timeout = Math.min(1000 * (2 ** retryCount), 10000);
                    setTimeout(() => {
                        console.log(`♻️ Reconnecting in ${timeout}ms...`);
                        retryCount++;
                        connectWebSocket();
                    }, timeout);
                }
            };

            ws.onerror = (err) => {
                console.error('WebSocket Error:', err);
                ws?.close();
            };
        };

        fetchRuns();
        connectWebSocket();

        return () => {
            isMounted = false;
            // Clean close
            if (ws) {
                ws.onclose = null; // Prevent reconnection attempt on unmount
                ws.close();
            }
        };
    }, []);

    const getStatusBadge = (status: string) => {
        const badges = {
            running: 'bg-brand-500/20 text-brand-400 border-brand-500/30',
            success: 'bg-green-500/20 text-green-400 border-green-500/30',
            failed: 'bg-red-500/20 text-red-400 border-red-500/30',
            queued: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
        };
        return badges[status as keyof typeof badges] || badges.queued;
    };

    const handleStop = async (runId: string) => {
        console.log('handleStop called for runId:', runId);
        if (!confirm('Are you sure you want to stop this run?')) return;
        
        setStoppingRunId(runId);
        try {
            await axios.post(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/runs/${runId}/stop`);
            showToast('Run stopped successfully', 'success');
            
            // Update the run status in the list
            setRuns(runs.map(run => 
                run.run_id === runId 
                    ? { ...run, status: 'failed' } 
                    : run
            ));
        } catch (error) {
            console.error('Failed to stop run:', error);
            showToast('Failed to stop run', 'error');
        } finally {
            setStoppingRunId(null);
        }
    };

    return (
        <Layout>
            <div className="p-8 max-w-7xl mx-auto space-y-8">
                <header>
                    <h2 className="text-2xl font-bold text-white">Execution History</h2>
                    <p className="text-slate-400">View all job execution logs</p>
                </header>

                <div className="glass rounded-xl overflow-hidden border border-white/5">
                    <table className="w-full text-left">
                        <thead className="bg-white/5 text-slate-400 uppercase text-xs">
                            <tr>
                                <th className="px-6 py-4">Executed At</th>
                                <th className="px-6 py-4">Position Date</th>
                                <th className="px-6 py-4">History Date</th>
                                <th className="px-6 py-4">Run ID</th>
                                <th className="px-6 py-4">Connector</th>
                                <th className="px-6 py-4">Status</th>
                                <th className="px-6 py-4">Node</th>
                                <th className="px-6 py-4">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5 text-sm">
                            {loading ? (
                                <tr>
                                    <td colSpan={7} className="px-6 py-8 text-center text-slate-400">Loading history...</td>
                                </tr>
                            ) : runs.length === 0 ? (
                                <tr>
                                    <td colSpan={7} className="px-6 py-8 text-center text-slate-500">No execution history found.</td>
                                </tr>
                            ) : (
                                runs.map((run) => (
                                    <tr key={run.run_id} className="hover:bg-white/5 transition-colors">
                                        <td className="px-6 py-4 text-slate-300">
                                            {run.created_at ? new Date(run.created_at).toLocaleString('pt-BR', {
                                                day: '2-digit',
                                                month: '2-digit',
                                                year: 'numeric',
                                                hour: '2-digit',
                                                minute: '2-digit',
                                                second: '2-digit'
                                            }) : '-'}
                                        </td>
                                        <td className="px-6 py-4 text-slate-300">{run.report_date || '-'}</td>
                                        <td className="px-6 py-4 text-slate-300">{run.history_date || '-'}</td>
                                        <td className="px-6 py-4 font-mono text-slate-300">#{run.run_id.slice(0, 8)}</td>
                                        <td className="px-6 py-4 text-white">{run.connector}</td>
                                        <td className="px-6 py-4">
                                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${getStatusBadge(run.status)}`}>
                                                {run.status === 'running' && <span className="w-1.5 h-1.5 bg-brand-400 rounded-full mr-1.5 animate-pulse"></span>}
                                                {run.status.charAt(0).toUpperCase() + run.status.slice(1)}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 text-slate-400">{run.node}</td>
                                        <td className="px-6 py-4">
                                            <div className="flex items-center gap-2">
                                                <Link to={`/live/${run.run_id}`} className="text-brand-400 hover:text-brand-300 font-medium flex items-center">
                                                    <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path></svg>
                                                    Watch
                                                </Link>
                                                {(run.status === 'running' || run.status === 'queued') && (
                                                    <button
                                                        onClick={() => handleStop(run.run_id)}
                                                        disabled={stoppingRunId === run.run_id}
                                                        className="text-red-400 hover:text-red-300 font-medium flex items-center disabled:opacity-50 disabled:cursor-not-allowed"
                                                    >
                                                        <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z"></path></svg>
                                                        {stoppingRunId === run.run_id ? 'Stopping...' : 'Stop'}
                                                    </button>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </Layout>
    );
}
