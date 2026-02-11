import { useEffect, useState } from 'react';
import Layout from '../components/Layout';
import axios from 'axios';
import { useToast } from '../context/ToastContext';

interface FileMetadata {
    file_type: string;
    filename: string;
    path: string;
    size_bytes?: number;
    status: string;
}

interface DownloadItem {
    run_id: string;
    job_id: string;
    job_name?: string;
    connector?: string;
    status: string;
    created_at: string;
    files: FileMetadata[];
}

export default function Downloads() {
    const [downloads, setDownloads] = useState<DownloadItem[]>([]);
    const [loading, setLoading] = useState(true);
    const { showToast } = useToast();

    useEffect(() => {
        fetchDownloads();
    }, []);

    const fetchDownloads = async () => {
        try {
            const res = await axios.get(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/downloads/`);
            setDownloads(res.data);
            setLoading(false);
        } catch (error) {
            console.error('Failed to fetch downloads:', error);
            showToast('Failed to load downloads', 'error');
            setLoading(false);
        }
    };

    const handleDownload = async (runId: string, fileType: string, filename: string) => {
        try {
            const url = `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/downloads/${runId}/${fileType}?filename=${encodeURIComponent(filename)}`;
            
            // Create a temporary link and trigger download
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            showToast('Download started', 'success');
        } catch (error) {
            console.error('Download failed:', error);
            showToast('Download failed', 'error');
        }
    };

    const getStatusBadge = (status: string) => {
        const badges = {
            ready: 'bg-green-500/20 text-green-400 border-green-500/30',
            processing: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
            error: 'bg-red-500/20 text-red-400 border-red-500/30'
        };
        return badges[status as keyof typeof badges] || badges.ready;
    };

    const formatFileSize = (bytes?: number) => {
        if (!bytes) return '-';
        const kb = bytes / 1024;
        if (kb < 1024) return `${kb.toFixed(1)} KB`;
        return `${(kb / 1024).toFixed(1)} MB`;
    };

    return (
        <Layout>
            <div className="p-8 max-w-7xl mx-auto space-y-8">
                <header>
                    <h2 className="text-2xl font-bold text-white">Downloads & Reports</h2>
                    <p className="text-slate-400">Access downloaded and processed files</p>
                </header>

                <div className="glass rounded-xl overflow-hidden border border-white/5">
                    <table className="w-full text-left">
                        <thead className="bg-white/5 text-slate-400 uppercase text-xs">
                            <tr>
                                <th className="px-6 py-4">Date</th>
                                <th className="px-6 py-4">Job Name</th>
                                <th className="px-6 py-4">Status</th>
                                <th className="px-6 py-4">Original File</th>
                                <th className="px-6 py-4">Processed File</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5 text-sm">
                            {loading ? (
                                <tr>
                                    <td colSpan={5} className="px-6 py-8 text-center text-slate-400">Loading downloads...</td>
                                </tr>
                            ) : downloads.length === 0 ? (
                                <tr>
                                    <td colSpan={5} className="px-6 py-8 text-center text-slate-500">No downloads available yet.</td>
                                </tr>
                            ) : (
                                downloads.map((item) => {
                                    const originalFiles = item.files.filter(f => f.file_type === 'original');
                                    const processedFiles = item.files.filter(f => f.file_type === 'processed');
                                    
                                    return (
                                        <tr key={item.run_id} className="hover:bg-white/5 transition-colors">
                                            <td className="px-6 py-4 text-slate-300">
                                                {new Date(item.created_at).toLocaleString('pt-BR', {
                                                    day: '2-digit',
                                                    month: '2-digit',
                                                    year: 'numeric',
                                                    hour: '2-digit',
                                                    minute: '2-digit'
                                                })}
                                            </td>
                                            <td className="px-6 py-4 text-white">{item.job_name || 'Unknown'}</td>
                                            <td className="px-6 py-4">
                                                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${getStatusBadge(item.status)}`}>
                                                    {item.status === 'success' ? 'Ready' : item.status}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4">
                                                {originalFiles.length > 0 ? (
                                                    <div className="flex flex-col gap-2">
                                                        {originalFiles.map((file) => (
                                                            <button
                                                                key={file.path}
                                                                onClick={() => handleDownload(item.run_id, 'original', file.filename)}
                                                                className="text-brand-400 hover:text-brand-300 font-medium flex items-center gap-2"
                                                            >
                                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                                                                </svg>
                                                                <div className="text-left">
                                                                    <div>{file.filename}</div>
                                                                    <div className="text-xs text-slate-500">{formatFileSize(file.size_bytes)}</div>
                                                                </div>
                                                            </button>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <span className="text-slate-500">-</span>
                                                )}
                                            </td>
                                            <td className="px-6 py-4">
                                                {processedFiles.length > 0 ? (
                                                    <div className="flex flex-col gap-2">
                                                        {processedFiles.map((file) => (
                                                            <button
                                                                key={file.path}
                                                                onClick={() => handleDownload(item.run_id, 'processed', file.filename)}
                                                                className="text-green-400 hover:text-green-300 font-medium flex items-center gap-2"
                                                            >
                                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                                                                </svg>
                                                                <div className="text-left">
                                                                    <div>{file.filename}</div>
                                                                    <div className="text-xs text-slate-500">{formatFileSize(file.size_bytes)}</div>
                                                                </div>
                                                            </button>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <span className="text-slate-500">-</span>
                                                )}
                                            </td>
                                        </tr>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </Layout>
    );
}
