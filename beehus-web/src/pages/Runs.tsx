import { useCallback, useEffect, useRef, useState } from 'react';
import Layout from '../components/Layout';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { useToast } from '../context/ToastContext';
import { formatDateTime } from '../utils/datetime';

interface Run {
    run_id: string;
    job_id: string;
    job_name?: string;
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
    const [wsConnected, setWsConnected] = useState(false);
    const [wsConnecting, setWsConnecting] = useState(false);
    const [wsError, setWsError] = useState<string | null>(null);
    const { showToast } = useToast();
    const wsRef = useRef<WebSocket | null>(null);
    const retryCountRef = useRef(0);
    const reconnectTimeoutRef = useRef<number | null>(null);
    const initialConnectTimeoutRef = useRef<number | null>(null);
    const shouldReconnectRef = useRef(true);
    const intentionalCloseRef = useRef(false);

    const connectWebSocket = useCallback(() => {
        const maxRetries = 5;
        const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
        const wsUrl = `${apiUrl.replace(/^http/, 'ws')}/ws/runs`;

        if (wsRef.current) {
            intentionalCloseRef.current = true;
            wsRef.current.onopen = null;
            wsRef.current.onmessage = null;
            wsRef.current.onerror = null;
            wsRef.current.onclose = null;
            wsRef.current.close();
            wsRef.current = null;
        }

        if (reconnectTimeoutRef.current) {
            window.clearTimeout(reconnectTimeoutRef.current);
            reconnectTimeoutRef.current = null;
        }

        setWsConnecting(true);
        setWsError(null);
        intentionalCloseRef.current = false;

        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
            if (ws !== wsRef.current) return;
            console.log('✅ Connected to Real-time Run Updates');
            retryCountRef.current = 0;
            setWsConnected(true);
            setWsConnecting(false);
            setWsError(null);
        };

        ws.onmessage = (event) => {
            if (ws !== wsRef.current) return;
            try {
                const data = JSON.parse(event.data);
                setRuns(prevRuns => {
                    return prevRuns.map(run => {
                       if (run.run_id === data.run_id) {
                           return { 
                               ...run, 
                               status: data.status,
                               ...(data.node && { node: data.node })
                           };
                       }
                       return run;
                    });
                });
            } catch (e) {
                console.error('Failed to parse WS message:', e);
            }
        };

        ws.onclose = () => {
            if (ws !== wsRef.current) return;
            console.log('🔴 WebSocket Disconnected');
            setWsConnected(false);
            setWsConnecting(false);

            if (!shouldReconnectRef.current || intentionalCloseRef.current) {
                return;
            }

            if (retryCountRef.current < maxRetries) {
                const timeout = Math.min(1000 * (2 ** retryCountRef.current), 10000);
                reconnectTimeoutRef.current = window.setTimeout(() => {
                    console.log(`♻️ Reconnecting in ${timeout}ms...`);
                    retryCountRef.current += 1;
                    connectWebSocket();
                }, timeout);
            }
        };

        ws.onerror = (err) => {
            if (ws !== wsRef.current) return;
            if (!shouldReconnectRef.current || intentionalCloseRef.current) {
                return;
            }
            console.error('WebSocket Error:', err);
            setWsError('WebSocket error');
            ws.close();
        };
    }, []);

    useEffect(() => {
        let isMounted = true;
        shouldReconnectRef.current = true;

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

        fetchRuns();
        initialConnectTimeoutRef.current = window.setTimeout(() => {
            connectWebSocket();
        }, 0);

        return () => {
            isMounted = false;
            shouldReconnectRef.current = false;
            intentionalCloseRef.current = true;
            // Clean close
            if (wsRef.current) {
                wsRef.current.onopen = null;
                wsRef.current.onmessage = null;
                wsRef.current.onerror = null;
                wsRef.current.onclose = null;
                wsRef.current.close();
                wsRef.current = null;
            }
            if (initialConnectTimeoutRef.current) {
                window.clearTimeout(initialConnectTimeoutRef.current);
                initialConnectTimeoutRef.current = null;
            }
            if (reconnectTimeoutRef.current) {
                window.clearTimeout(reconnectTimeoutRef.current);
                reconnectTimeoutRef.current = null;
            }
        };
    }, [connectWebSocket]);

    const handleWsRetry = () => {
        retryCountRef.current = 0;
        connectWebSocket();
    };

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
                <header className="flex items-start justify-between gap-4">
                    <div>
                        <h2 className="text-2xl font-bold text-white">Execution History</h2>
                        <p className="text-slate-400">View all job execution logs</p>
                    </div>
                    <div className="flex items-center gap-3">
                        <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${wsConnected ? 'bg-green-500/20 text-green-300 border-green-500/30' : 'bg-red-500/20 text-red-300 border-red-500/30'}`}>
                            <span className={`h-2 w-2 rounded-full ${wsConnected ? 'bg-green-400' : 'bg-red-400'}`}></span>
                            {wsConnecting ? 'WS connecting…' : wsConnected ? 'WS connected' : 'WS disconnected'}
                        </span>
                        {!wsConnected && (
                            <button
                                onClick={handleWsRetry}
                                className="text-xs font-medium text-brand-300 hover:text-brand-200 border border-brand-500/30 rounded-full px-3 py-1"
                                title={wsError || 'Retry WebSocket'}
                            >
                                Retry
                            </button>
                        )}
                    </div>
                </header>

                <div className="glass rounded-xl overflow-hidden border border-white/5">
                    <table className="w-full text-left">
                        <thead className="bg-white/5 text-slate-400 uppercase text-xs">
                            <tr>
                                <th className="px-6 py-4">Executed At</th>
                                <th className="px-6 py-4">Position Date</th>
                                <th className="px-6 py-4">History Date</th>
                                <th className="px-6 py-4">Run ID</th>
                                <th className="px-6 py-4">Job Name</th>
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
                                            {run.created_at ? formatDateTime(run.created_at, {
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
                                        <td className="px-6 py-4 text-white">{run.job_name || run.connector}</td>
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
