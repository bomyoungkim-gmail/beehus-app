import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useSearchParams, useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import ConfirmModal from '../components/ui/ConfirmModal';
import { useToast } from '../context/ToastContext';

interface Job {
    id: string;
    workspace_id: string;
    name: string;
    connector: string;
    params: Record<string, any>;
    schedule?: string;
    status: string;
}

interface Workspace {
    id: string;
    name: string;
    description?: string;
}

interface Credential {
    id: string;
    workspace_id: string;
    label: string;
    username: string;
}

// Schedule presets for easy selection
const SCHEDULE_PRESETS = [
    { label: 'No schedule (manual only)', value: '' },
    { label: 'Every 3 minutes', value: '*/3 * * * *' },
    { label: 'Every 5 minutes', value: '*/5 * * * *' },
    { label: 'Every 15 minutes', value: '*/15 * * * *' },
    { label: 'Every 30 minutes', value: '*/30 * * * *' },
    { label: 'Every hour', value: '0 * * * *' },
    { label: 'Every 6 hours', value: '0 */6 * * *' },
    { label: 'Daily at midnight', value: '0 0 * * *' },
    { label: 'Daily at 9 AM', value: '0 9 * * *' },
    { label: 'Weekdays at 9 AM', value: '0 9 * * 1-5' },
    { label: 'Weekly (Monday 9 AM)', value: '0 9 * * 1' },
    { label: 'Custom cron expression', value: 'custom' }
];

export default function Jobs() {
    const [jobs, setJobs] = useState<Job[]>([]);
    const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
    const [credentials, setCredentials] = useState<Credential[]>([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [creating, setCreating] = useState(false);
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const [scheduleType, setScheduleType] = useState('');
    const [customCron, setCustomCron] = useState('');
    const [jsonMode, setJsonMode] = useState(false);
    const [jsonParams, setJsonParams] = useState('{}');
    
    // UI State for Delete Modal
    const [deleteModal, setDeleteModal] = useState<{ isOpen: boolean; id: string; name: string }>({ 
        isOpen: false, id: '', name: '' 
    });
    const [deleteAllModal, setDeleteAllModal] = useState(false);

    const { showToast } = useToast();

    // Get workspace specific jobs if workspace_id is present
    const workspaceId = searchParams.get('workspace');
    
    const [formData, setFormData] = useState<{
        workspace_id: string;
        name: string;
        connector: string;
        credential_id?: string;
        params: { username?: string; password?: string; url?: string; selector?: string; [key: string]: any };
        schedule: string;
    }>({
        workspace_id: workspaceId || '',
        name: '',
        connector: 'jpmorgan_login',
        credential_id: '',
        params: { username: '', password: '' },  // Dynamic based on connector
        schedule: ''
    });

    const fetchJobs = async () => {
        try {
            const res = await axios.get(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/jobs`);
            setJobs(res.data);
        } catch (error) {
            console.error('Failed to fetch jobs:', error);
        } finally {
            setLoading(false);
        }
    };

    const fetchWorkspaces = async () => {
        try {
            const res = await axios.get(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/workspaces`);
            setWorkspaces(res.data);
        } catch (error) {
            console.error('Failed to fetch workspaces:', error);
        }
    };

    const fetchCredentials = async () => {
        try {
            const res = await axios.get(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/credentials`);
            setCredentials(res.data);
        } catch (error) {
            console.error('Failed to fetch credentials:', error);
        }
    };

    useEffect(() => {
        fetchJobs();
        fetchWorkspaces();
        fetchCredentials();
    }, []);

    // Update params when connector changes
    useEffect(() => {
        if (formData.connector === 'jpmorgan_login') {
            setFormData(prev => ({ ...prev, params: { username: '', password: '' } }));
        } else if (formData.connector === 'itau_onshore_login') {
            setFormData(prev => ({
                ...prev,
                params: { username: '', password: '', use_business_day: false, business_day: '' }
            }));
        } else if (formData.connector === 'generic_scraper') {
            setFormData(prev => ({ ...prev, params: { url: '', selector: '' } }));
        }
    }, [formData.connector]);

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        setCreating(true);

        try {
            // Parse JSON params if in JSON mode
            let finalParams = formData.params;
            if (jsonMode) {
                try {
                    finalParams = JSON.parse(jsonParams);
                } catch (err) {
                    alert('Invalid JSON in params field');
                    setCreating(false);
                    return;
                }
            }
            
            // Determine final schedule value and normalize (remove extra spaces)
        let finalSchedule = scheduleType === 'custom' ? customCron : scheduleType;
        if (finalSchedule) {
            // Normalize: remove extra spaces between cron parts
            finalSchedule = finalSchedule.split(/\s+/).filter(p => p).join(' ');
        }
            
            await axios.post(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/jobs`, {
                ...formData,
                params: finalParams,
                schedule: finalSchedule || undefined
            });
            
            setShowModal(false);
            setFormData({
                workspace_id: '',
                name: '',
                connector: 'jpmorgan_login',
                params: { username: '', password: '' },
                schedule: ''
            });
            setScheduleType('');
            setCustomCron('');
            setJsonMode(false);
            setJsonParams('{}');
            fetchJobs();
        } catch (error) {
            alert('Error creating job');
            console.error(error);
        } finally {
            setCreating(false);
        }
    };

    const triggerJob = async (jobId: string) => {
        try {
            const res = await axios.post(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/jobs/${jobId}/run`);
            showToast(`Job triggered! Run ID: ${res.data.id}`, 'success');
            navigate(`/live/${res.data.id}`);
        } catch (error) {
            showToast('Error triggering job', 'error');
            console.error(error);
        }
    };

    const deleteJob = (jobId: string, jobName: string) => {
        setDeleteModal({ isOpen: true, id: jobId, name: jobName });
    };

    const handleConfirmDelete = async () => {
        try {
            await axios.delete(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/jobs/${deleteModal.id}`);
            showToast('Job deleted successfully', 'success');
            fetchJobs();
        } catch (error) {
            showToast('Error deleting job', 'error');
            console.error(error);
        } finally {
            setDeleteModal(prev => ({ ...prev, isOpen: false }));
        }
    };

    const getStatusBadge = (status: string) => {
        const badges = {
            active: 'bg-green-500/20 text-green-400 border-green-500/30',
            paused: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
            inactive: 'bg-slate-500/20 text-slate-400 border-slate-500/30'
        };
        return badges[status as keyof typeof badges] || badges.inactive;
    };

    const getScheduleLabel = (cronExpr?: string) => {
        if (!cronExpr) return null;
        const preset = SCHEDULE_PRESETS.find(p => p.value === cronExpr);
        return preset ? preset.label : cronExpr;
    };

    const deleteAllJobs = () => {
        setDeleteAllModal(true);
    };

    const handleConfirmDeleteAll = async () => {
        try {
            const res = await axios.delete(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/jobs`);
            showToast(res.data.message || 'All jobs deleted', 'success');
            fetchJobs();
        } catch (error) {
            showToast('Error deleting jobs', 'error');
            console.error(error);
        } finally {
            setDeleteAllModal(false);
        }
    };

    return (
        <Layout>
            <div className="p-8 max-w-7xl mx-auto space-y-8">
                <header className="flex justify-between items-center">
                    <div>
                        <h2 className="text-2xl font-bold text-white">Scrape Jobs</h2>
                        <p className="text-slate-400">Manage your automated scraping jobs</p>
                    </div>
                    <div className="flex gap-3">
                        <button 
                            onClick={deleteAllJobs}
                            className="bg-red-600/10 hover:bg-red-600/30 text-red-500 border border-red-500/30 px-6 py-2.5 rounded-lg font-medium transition-all flex items-center space-x-2"
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                            <span>Delete All</span>
                        </button>
                        <button 
                            onClick={() => setShowModal(true)}
                            className="bg-brand-600 hover:bg-brand-500 text-white px-6 py-2.5 rounded-lg font-medium shadow-lg shadow-brand-500/20 transition-all flex items-center space-x-2"
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path></svg>
                            <span>New Job</span>
                        </button>
                    </div>
                </header>

                {/* Jobs Table */}
                <div className="glass rounded-xl overflow-hidden border border-white/5">
                    <table className="w-full text-left">
                        <thead className="bg-white/5 text-slate-400 uppercase text-xs">
                            <tr>
                                <th className="px-6 py-4">Job Name</th>
                                <th className="px-6 py-4">Connector</th>
                                <th className="px-6 py-4">Schedule</th>
                                <th className="px-6 py-4">Status</th>
                                <th className="px-6 py-4">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5 text-sm">
                            {loading ? (
                                <tr>
                                    <td colSpan={5} className="px-6 py-8 text-center text-slate-400">
                                        Loading jobs...
                                    </td>
                                </tr>
                            ) : jobs.length === 0 ? (
                                <tr>
                                    <td colSpan={5} className="px-6 py-8 text-center text-slate-500">
                                        No jobs yet. Create your first job!
                                    </td>
                                </tr>
                            ) : (
                                jobs.map((job) => (
                                    <tr key={job.id} className="hover:bg-white/5 transition-colors">
                                        <td className="px-6 py-4">
                                            <div>
                                                <p className="font-semibold text-white">{job.name}</p>
                                                <p className="text-xs text-slate-500 font-mono">#{job.id.slice(0, 8)}</p>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 text-slate-300">{job.connector}</td>
                                        <td className="px-6 py-4">
                                            {job.schedule ? (
                                                <div>
                                                    <p className="text-sm text-slate-300">{getScheduleLabel(job.schedule)}</p>
                                                    <code className="text-xs text-slate-500 font-mono">{job.schedule}</code>
                                                </div>
                                            ) : (
                                                <span className="text-slate-500 text-xs">Manual only</span>
                                            )}
                                        </td>
                                        <td className="px-6 py-4">
                                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${getStatusBadge(job.status)}`}>
                                                {job.status.charAt(0).toUpperCase() + job.status.slice(1)}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="flex items-center space-x-3">
                                                <button 
                                                    onClick={() => triggerJob(job.id)}
                                                    className="text-brand-400 hover:text-brand-300 font-medium flex items-center"
                                                >
                                                    <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path>
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                                                    </svg>
                                                    Run
                                                </button>
                                                <button 
                                                    onClick={() => deleteJob(job.id, job.name)}
                                                    className="text-red-400 hover:text-red-300 font-medium flex items-center"
                                                >
                                                    <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                                    </svg>
                                                    Delete
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                {/* Create Modal */}
                {showModal && (
                    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
                        <div className="glass p-8 rounded-xl border border-white/10 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
                            <h3 className="text-xl font-bold text-white mb-6">Create Job</h3>
                            <form onSubmit={handleCreate} className="space-y-5">
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-sm font-medium text-slate-400 mb-2">Workspace</label>
                                        <select
                                            value={formData.workspace_id}
                                            onChange={(e) => setFormData({...formData, workspace_id: e.target.value})}
                                            className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                                            required
                                        >
                                            <option value="" disabled>Select a workspace</option>
                                            {workspaces.map(ws => (
                                                <option key={ws.id} value={ws.id}>
                                                    {ws.name} ({ws.id.slice(0, 8)}...)
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-slate-400 mb-2">Job Name</label>
                                        <input
                                            type="text"
                                            value={formData.name}
                                            onChange={(e) => setFormData({...formData, name: e.target.value})}
                                            className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                                            placeholder="My Scraping Job"
                                            required
                                        />
                                    </div>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-slate-400 mb-2">Connector</label>
                                    <select
                                        value={formData.connector}
                                        onChange={(e) => setFormData({...formData, connector: e.target.value})}
                                        className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                                    >
                                        <option value="jpmorgan_login">JPMorgan Login</option>
                                        <option value="itau_onshore_login">Itau Onshore Login</option>
                                        <option value="itau_offshore_login">Itau Offshore Login</option>
                                        <option value="btg_onshore_login">BTG Onshore Login</option>
                                        <option value="btg_offshore_login">BTG Offshore Login</option>
                                        <option value="morgan_stanley_login">Morgan Stanley Login</option>
                                        <option value="jefferies_login">Jefferies Login</option>
                                        <option value="generic_scraper">Generic Scraper</option>
                                    </select>
                                </div>

                                {/* Dynamic Params Section */}
                                <div className="border-t border-white/10 pt-4">
                                    <div className="flex items-center justify-between mb-3">
                                        <h4 className="text-sm font-semibold text-slate-300">Parameters</h4>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                if (!jsonMode) {
                                                    // Switching TO JSON mode: convert form to JSON
                                                    setJsonParams(JSON.stringify(formData.params, null, 2));
                                                }
                                                setJsonMode(!jsonMode);
                                            }}
                                            className="text-xs px-3 py-1 rounded-lg border border-white/10 hover:bg-white/5 transition-colors flex items-center space-x-1"
                                        >
                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path>
                                            </svg>
                                            <span className="text-slate-400">{jsonMode ? 'Form Mode' : 'JSON Mode'}</span>
                                        </button>
                                    </div>

                                    {jsonMode ? (
                                        <div>
                                            <textarea
                                                value={jsonParams}
                                                onChange={(e) => setJsonParams(e.target.value)}
                                                className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500 font-mono text-sm"
                                                rows={8}
                                                placeholder='{\n  "key": "value"\n}'
                                            />
                                            <p className="text-xs text-slate-500 mt-2">
                                                Enter JSON object with params for the connector
                                            </p>
                                        </div>
                                    ) : (
                                        <>
                                            {['jpmorgan_login', 'itau_onshore_login', 'itau_offshore_login', 'btg_onshore_login', 'btg_offshore_login', 'morgan_stanley_login', 'jefferies_login'].includes(formData.connector) ? (
                                                <div className="space-y-4">
                                                    {/* Credential Selector */}
                                                    <div>
                                                        <label className="block text-sm text-slate-400 mb-2">
                                                            Authentication Method
                                                        </label>
                                                        <select
                                                            value={formData.credential_id || 'manual'}
                                                            onChange={(e) => {
                                                                const value = e.target.value;
                                                                if (value === 'manual') {
                                                                    setFormData({ ...formData, credential_id: '' });
                                                                } else {
                                                                    setFormData({ ...formData, credential_id: value, params: {} });
                                                                }
                                                            }}
                                                            className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                                                        >
                                                            <option value="manual">Manual (enter username/password)</option>
                                                            <optgroup label="Saved Credentials">
                                                                {credentials
                                                                    .filter(c => c.workspace_id === formData.workspace_id)
                                                                    .map(cred => (
                                                                        <option key={cred.id} value={cred.id}>
                                                                            🔐 {cred.label} ({cred.username})
                                                                        </option>
                                                                    ))}
                                                            </optgroup>
                                                        </select>
                                                        {credentials.filter(c => c.workspace_id === formData.workspace_id).length === 0 && formData.workspace_id && (
                                                            <p className="text-xs text-slate-500 mt-1">
                                                                No credentials found for this workspace. <a href="/credentials" className="text-brand-400 hover:underline">Create one</a>
                                                            </p>
                                                        )}
                                                    </div>

                                                    {/* Manual Entry Fields (only if no credential selected) */}
                                                    {!formData.credential_id && (
                                                        <div className="grid grid-cols-2 gap-4">
                                                            <div>
                                                                <label className="block text-sm text-slate-400 mb-2">Username</label>
                                                                <input
                                                                    type="text"
                                                                    value={(formData.params as any).username || ''}
                                                                    onChange={(e) => setFormData({
                                                                        ...formData,
                                                                        params: { ...formData.params, username: e.target.value }
                                                                    })}
                                                                    className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                                                                    placeholder="user@example.com"
                                                                />
                                                            </div>
                                                            <div>
                                                                <label className="block text-sm text-slate-400 mb-2">Password</label>
                                                                <input
                                                                    type="password"
                                                                    value={(formData.params as any).password || ''}
                                                                    onChange={(e) => setFormData({
                                                                        ...formData,
                                                                        params: { ...formData.params, password: e.target.value }
                                                                    })}
                                                                    className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                                                                    placeholder="••••••••"
                                                                />
                                                            </div>
                                                        </div>
                                                    )}

                                                    <div className="space-y-3">
                                                        <label className="flex items-center space-x-2 text-sm text-slate-400">
                                                            <input
                                                                type="checkbox"
                                                                checked={(formData.params as any).use_business_day || false}
                                                                onChange={(e) => setFormData({
                                                                    ...formData,
                                                                    params: {
                                                                        ...formData.params,
                                                                        use_business_day: e.target.checked
                                                                    }
                                                                })}
                                                                className="rounded border-white/10 bg-dark-surface"
                                                            />
                                                            <span>Use specific report date</span>
                                                        </label>
                                                        <input
                                                            type="date"
                                                            value={(formData.params as any).business_day || ''}
                                                            onChange={(e) => setFormData({
                                                                ...formData,
                                                                params: {
                                                                    ...formData.params,
                                                                    business_day: e.target.value
                                                                }
                                                            })}
                                                            disabled={!(formData.params as any).use_business_day}
                                                            className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500 disabled:opacity-50"
                                                        />
                                                        <p className="text-xs text-slate-500">
                                                            When enabled, this date overrides the default business day.
                                                        </p>
                                                    </div>
                                                </div>
                                            ) : (
                                                <div className="space-y-3">
                                                    <div>
                                                        <label className="block text-sm text-slate-400 mb-2">Target URL</label>
                                                        <input
                                                            type="url"
                                                            value={(formData.params as any).url || ''}
                                                            onChange={(e) => setFormData({
                                                                ...formData,
                                                                params: { ...formData.params, url: e.target.value }
                                                            })}
                                                            className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                                                            placeholder="https://example.com"
                                                        />
                                                    </div>
                                                    <div>
                                                        <label className="block text-sm text-slate-400 mb-2">CSS Selector</label>
                                                        <input
                                                            type="text"
                                                            value={(formData.params as any).selector || ''}
                                                            onChange={(e) => setFormData({
                                                                ...formData,
                                                                params: { ...formData.params, selector: e.target.value }
                                                            })}
                                                            className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500 font-mono text-sm"
                                                            placeholder=".product-title"
                                                        />
                                                    </div>
                                                </div>
                                            )}

                                        </>
                                    )}
                                </div>

                                {/* Schedule Section */}
                                <div className="border-t border-white/10 pt-4">
                                    <h4 className="text-sm font-semibold text-slate-300 mb-3">Schedule (Optional)</h4>
                                    <select
                                        value={scheduleType}
                                        onChange={(e) => setScheduleType(e.target.value)}
                                        className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500 mb-3"
                                    >
                                        {SCHEDULE_PRESETS.map(preset => (
                                            <option key={preset.value} value={preset.value}>
                                                {preset.label}
                                            </option>
                                        ))}
                                    </select>

                                    {scheduleType === 'custom' && (
                                        <div>
                                            <input
                                                type="text"
                                                value={customCron}
                                                onChange={(e) => setCustomCron(e.target.value)}
                                                className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500 font-mono text-sm"
                                                placeholder="*/5 * * * *"
                                            />
                                            <p className="text-xs text-slate-500 mt-2">
                                                Format: <code className="text-brand-400">minute hour day month day_of_week</code>
                                                <br />
                                                Use <a href="https://crontab.guru" target="_blank" rel="noopener" className="text-brand-400 hover:underline">crontab.guru</a> for help
                                            </p>
                                        </div>
                                    )}

                                    {scheduleType && scheduleType !== '' && scheduleType !== 'custom' && (
                                        <div className="bg-brand-500/10 border border-brand-500/20 rounded-lg p-3">
                                            <p className="text-xs text-brand-300">
                                                <span className="font-semibold">Cron expression:</span>{' '}
                                                <code className="bg-dark-surface px-2 py-0.5 rounded">{scheduleType}</code>
                                            </p>
                                        </div>
                                    )}
                                </div>

                                <div className="flex space-x-3 pt-4 border-t border-white/10">
                                    <button
                                        type="button"
                                        onClick={() => setShowModal(false)}
                                        className="flex-1 bg-white/5 hover:bg-white/10 text-white px-6 py-2.5 rounded-lg font-medium transition-all"
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={creating}
                                        className="flex-1 bg-brand-600 hover:bg-brand-500 text-white px-6 py-2.5 rounded-lg font-medium shadow-lg shadow-brand-500/20 transition-all disabled:opacity-50"
                                    >
                                        {creating ? 'Creating...' : 'Create'}
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}

            </div>

            {/* Single Delete Modal */}
            <ConfirmModal
                isOpen={deleteModal.isOpen}
                title="Delete Job?"
                message={`Are you sure you want to delete job "${deleteModal.name}"? This cannot be undone.`}
                confirmText="Delete Job"
                isDanger={true}
                onConfirm={handleConfirmDelete}
                onCancel={() => setDeleteModal(prev => ({ ...prev, isOpen: false }))}
            />

            {/* Delete All Modal */}
            <ConfirmModal
                isOpen={deleteAllModal}
                title="Delete ALL Jobs?"
                message="DANGER: This will delete ALL jobs in ALL workspaces. This action allows you to purge the entire database of scraping tasks. This cannot be undone."
                confirmText="DELETE EVERYTHING"
                isDanger={true}
                onConfirm={handleConfirmDeleteAll}
                onCancel={() => setDeleteAllModal(false)}
            />
        </Layout>
    );
}
