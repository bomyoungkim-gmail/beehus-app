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
    processing_status?: string;
    selected_filename?: string | null;
    selected_sheet?: string | null;
    processing_error?: string | null;
}

interface ProcessingFileOption {
    filename: string;
    size_bytes?: number | null;
    is_excel: boolean;
    sheet_options: string[];
}

export default function Runs() {
    const [runs, setRuns] = useState<Run[]>([]);
    const [loading, setLoading] = useState(true);
    const [stoppingRunId, setStoppingRunId] = useState<string | null>(null);
    const [processingRunId, setProcessingRunId] = useState<string | null>(null);
    const [fileModalRun, setFileModalRun] = useState<Run | null>(null);
    const [sheetModalRun, setSheetModalRun] = useState<Run | null>(null);
    const [fileOptions, setFileOptions] = useState<ProcessingFileOption[]>([]);
    const [sheetOptions, setSheetOptions] = useState<string[]>([]);
    const [selectedFile, setSelectedFile] = useState<string>('');
    const [selectedSheet, setSelectedSheet] = useState<string>('');
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

    const fetchRuns = useCallback(async () => {
        try {
            const res = await axios.get(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/dashboard/recent-runs?limit=100`);
            setRuns(res.data);
        } catch (error) {
            console.error('Failed to fetch runs:', error);
        } finally {
            setLoading(false);
        }
    }, []);

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
        fetchRuns();
        initialConnectTimeoutRef.current = window.setTimeout(() => {
            connectWebSocket();
        }, 0);
        const pollId = window.setInterval(() => {
            if (isMounted) {
                fetchRuns();
            }
        }, 15000);

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
            window.clearInterval(pollId);
        };
    }, [connectWebSocket, fetchRuns]);

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

    const getProcessingBadge = (status?: string) => {
        const badges = {
            not_required: 'bg-slate-500/20 text-slate-300 border-slate-500/30',
            processing: 'bg-brand-500/20 text-brand-300 border-brand-500/30',
            processed: 'bg-green-500/20 text-green-300 border-green-500/30',
            pending_reprocess: 'bg-cyan-500/20 text-cyan-200 border-cyan-500/30',
            pending_file_selection: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
            pending_sheet_selection: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
            failed: 'bg-red-500/20 text-red-300 border-red-500/30',
        };
        const key = (status || 'not_required') as keyof typeof badges;
        return badges[key] || badges.not_required;
    };

    const openFileSelection = async (run: Run) => {
        try {
            const res = await axios.get<ProcessingFileOption[]>(
                `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/downloads/${run.run_id}/processing/options`,
            );
            setFileOptions(res.data);
            const preferred =
                run.selected_filename && res.data.some((opt) => opt.filename === run.selected_filename)
                    ? run.selected_filename
                    : res.data[0]?.filename || '';
            setSelectedFile(preferred);
            setFileModalRun(run);
        } catch (error) {
            console.error('Failed to load processing options:', error);
            showToast('Failed to load files for processing', 'error');
        }
    };

    const openSheetSelection = async (run: Run, filename?: string) => {
        const targetFile = filename || run.selected_filename;
        if (!targetFile) {
            await openFileSelection(run);
            return;
        }
        try {
            const res = await axios.get<string[]>(
                `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/downloads/${run.run_id}/processing/excel-options`,
                { params: { filename: targetFile } },
            );
            setSheetOptions(res.data);
            setSelectedSheet(res.data[0] || '');
            setSelectedFile(targetFile);
            setSheetModalRun(run);
        } catch (error) {
            console.error('Failed to load sheet options:', error);
            showToast('Failed to load Excel sheet options', 'error');
        }
    };

    const confirmFileSelection = async () => {
        if (!fileModalRun || !selectedFile) return;
        setProcessingRunId(fileModalRun.run_id);
        try {
            const res = await axios.post(
                `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/downloads/${fileModalRun.run_id}/processing/select-file`,
                { filename: selectedFile },
            );
            setFileModalRun(null);
            const status = res.data?.status;
            if (status === 'pending_sheet_selection') {
                await openSheetSelection(fileModalRun, selectedFile);
            } else {
                showToast('File selection saved. Click Reprocess to execute.', 'success');
            }
            await fetchRuns();
        } catch (error) {
            console.error('Failed to select file:', error);
            showToast('Failed to select file', 'error');
        } finally {
            setProcessingRunId(null);
        }
    };

    const confirmSheetSelection = async () => {
        if (!sheetModalRun || !selectedFile || !selectedSheet) return;
        setProcessingRunId(sheetModalRun.run_id);
        try {
            await axios.post(
                `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/downloads/${sheetModalRun.run_id}/processing/select-sheet`,
                { filename: selectedFile, selected_sheet: selectedSheet },
            );
            setSheetModalRun(null);
            showToast('Sheet selection saved. Click Reprocess to execute.', 'success');
            await fetchRuns();
        } catch (error) {
            console.error('Failed to select sheet:', error);
            showToast('Failed to select sheet', 'error');
        } finally {
            setProcessingRunId(null);
        }
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

    const handleReprocess = async (run: Run) => {
        setProcessingRunId(run.run_id);
        try {
            const payload: { filename?: string; selected_sheet?: string } = {};
            if (run.selected_filename) payload.filename = run.selected_filename;
            if (run.selected_sheet) payload.selected_sheet = run.selected_sheet;

            const res = await axios.post(
                `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/downloads/${run.run_id}/processing/process`,
                payload,
            );
            const status = res.data?.status;
            if (status === 'pending_file_selection') {
                await openFileSelection(run);
            } else if (status === 'pending_sheet_selection') {
                await openSheetSelection(run, res.data?.selected_filename || run.selected_filename || undefined);
            } else {
                showToast('Reprocessing started', 'success');
            }
            await fetchRuns();
        } catch (error) {
            console.error('Failed to reprocess run:', error);
            showToast('Failed to reprocess run', 'error');
        } finally {
            setProcessingRunId(null);
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
                                <th className="px-6 py-4">Processing</th>
                                <th className="px-6 py-4">Node</th>
                                <th className="px-6 py-4">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5 text-sm">
                            {loading ? (
                                <tr>
                                    <td colSpan={9} className="px-6 py-8 text-center text-slate-400">Loading history...</td>
                                </tr>
                            ) : runs.length === 0 ? (
                                <tr>
                                    <td colSpan={9} className="px-6 py-8 text-center text-slate-500">No execution history found.</td>
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
                                        <td className="px-6 py-4">
                                            <div className="space-y-1">
                                                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${getProcessingBadge(run.processing_status)}`}>
                                                    {(run.processing_status || 'not_required').replaceAll('_', ' ')}
                                                </span>
                                                {run.selected_filename && (
                                                    <p className="text-xs text-slate-500">{run.selected_filename}</p>
                                                )}
                                                {run.selected_sheet && (
                                                    <p className="text-xs text-slate-500">Sheet: {run.selected_sheet}</p>
                                                )}
                                            </div>
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
                                                {run.processing_status !== 'not_required' && (
                                                    <button
                                                        onClick={() => openFileSelection(run)}
                                                        className="text-yellow-300 hover:text-yellow-200 font-medium"
                                                    >
                                                        {run.selected_filename ? 'Change File' : 'Select File'}
                                                    </button>
                                                )}
                                                {run.processing_status !== 'not_required' &&
                                                    run.selected_filename &&
                                                    /\.xls(x|m)?$/i.test(run.selected_filename) && (
                                                    <button
                                                        onClick={() => openSheetSelection(run)}
                                                        className="text-yellow-300 hover:text-yellow-200 font-medium"
                                                    >
                                                        {run.selected_sheet ? 'Change Sheet' : 'Select Sheet'}
                                                    </button>
                                                )}
                                                {run.processing_status !== 'not_required' &&
                                                    (run.processing_status === 'processed' ||
                                                        run.processing_status === 'pending_reprocess' ||
                                                        run.processing_status === 'failed' ||
                                                        run.status === 'success') && (
                                                    <button
                                                        onClick={() => handleReprocess(run)}
                                                        disabled={processingRunId === run.run_id}
                                                        className="text-green-300 hover:text-green-200 font-medium disabled:opacity-50"
                                                    >
                                                        {processingRunId === run.run_id ? 'Reprocessing...' : 'Reprocess'}
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

            {fileModalRun && (
                <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
                    <div className="glass rounded-xl border border-white/10 p-6 w-full max-w-lg space-y-4">
                        <h3 className="text-lg font-semibold text-white">Select File for Processing</h3>
                        <p className="text-sm text-slate-400">Run #{fileModalRun.run_id.slice(0, 8)}</p>
                        <select
                            value={selectedFile}
                            onChange={(e) => setSelectedFile(e.target.value)}
                            className="w-full bg-dark-surface border border-white/10 rounded px-3 py-2 text-white"
                        >
                            {fileOptions.map((option) => (
                                <option key={option.filename} value={option.filename}>
                                    {option.filename} {option.is_excel ? '(Excel)' : ''}
                                </option>
                            ))}
                        </select>
                        <div className="flex justify-end gap-2">
                            <button
                                onClick={() => setFileModalRun(null)}
                                className="px-4 py-2 text-sm text-slate-300 hover:text-white"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={confirmFileSelection}
                                disabled={!selectedFile || processingRunId === fileModalRun.run_id}
                                className="px-4 py-2 rounded bg-brand-600 text-white text-sm disabled:opacity-60"
                            >
                                {processingRunId === fileModalRun.run_id ? 'Saving...' : 'Confirm'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {sheetModalRun && (
                <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
                    <div className="glass rounded-xl border border-white/10 p-6 w-full max-w-lg space-y-4">
                        <h3 className="text-lg font-semibold text-white">Select Excel Sheet</h3>
                        <p className="text-sm text-slate-400">{selectedFile}</p>
                        <select
                            value={selectedSheet}
                            onChange={(e) => setSelectedSheet(e.target.value)}
                            className="w-full bg-dark-surface border border-white/10 rounded px-3 py-2 text-white"
                        >
                            {sheetOptions.map((sheet) => (
                                <option key={sheet} value={sheet}>{sheet}</option>
                            ))}
                        </select>
                        <div className="flex justify-end gap-2">
                            <button
                                onClick={() => setSheetModalRun(null)}
                                className="px-4 py-2 text-sm text-slate-300 hover:text-white"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={confirmSheetSelection}
                                disabled={!selectedSheet || processingRunId === sheetModalRun.run_id}
                                className="px-4 py-2 rounded bg-brand-600 text-white text-sm disabled:opacity-60"
                            >
                                {processingRunId === sheetModalRun.run_id ? 'Processing...' : 'Confirm'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </Layout>
    );
}
