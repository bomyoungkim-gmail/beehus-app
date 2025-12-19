import React, { useEffect, useState } from 'react';
import Layout from '../components/Layout';
import axios from 'axios';
import { Link } from 'react-router-dom';

interface Workspace {
    id: string;
    name: string;
    description?: string;
    created_at?: string;
}

export default function Workspaces() {
    const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [creating, setCreating] = useState(false);
    const [formData, setFormData] = useState({
        name: '',
        description: ''
    });

    const fetchWorkspaces = async () => {
        try {
            const res = await axios.get('http://localhost:8000/workspaces');
            setWorkspaces(res.data);
        } catch (error) {
            console.error('Failed to fetch workspaces:', error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchWorkspaces();
    }, []);

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        setCreating(true);

        try {
            await axios.post('http://localhost:8000/workspaces', formData);
            setShowModal(false);
            setFormData({ name: '', description: '' });
            fetchWorkspaces();
        } catch (error) {
            alert('Error creating workspace');
            console.error(error);
        } finally {
            setCreating(false);
        }
    };

    const deleteWorkspace = async (id: string, name: string) => {
        console.log('Attempting to delete workspace:', id, name);
        if (!window.confirm(`Delete workspace "${name}"? This will also delete all associated jobs.`)) {
            console.log('Delete cancelled by user');
            return;
        }
        
        try {
            console.log('Sending delete request...');
            await axios.delete(`http://localhost:8000/workspaces/${id}`);
            console.log('Delete successful, refreshing...');
            fetchWorkspaces();
        } catch (error) {
            alert('Error deleting workspace (check console)');
            console.error('Delete failed:', error);
        }
    };

    const copyToClipboard = async (text: string) => {
        console.log('Copying to clipboard:', text);
        try {
            // Try modern API first
            if (navigator.clipboard) {
                await navigator.clipboard.writeText(text);
                console.log('Copied via Navigator API');
                alert('✅ ID copied to clipboard!');
                return;
            }
            throw new Error('Navigator API unavailable');
        } catch (err) {
            console.warn('Navigator API failed, trying fallback:', err);
            // Fallback
            try {
                const textArea = document.createElement('textarea');
                textArea.value = text;
                textArea.style.position = 'fixed'; // Avoid scrolling to bottom
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();
                const success = document.execCommand('copy');
                document.body.removeChild(textArea);
                if (success) {
                    console.log('Copied via execCommand');
                    alert('✅ ID copied to clipboard!');
                    return;
                }
            } catch (fallbackErr) {
                console.error('Fallback failed:', fallbackErr);
            }
            
            // Final fallback
            prompt('Copy this ID:', text);
        }
    };

    return (
        <Layout>
            <div className="p-8 max-w-7xl mx-auto space-y-8">
                <header className="flex justify-between items-center">
                    <div>
                        <h2 className="text-2xl font-bold text-white">Workspaces</h2>
                        <p className="text-slate-400">Organize your scraping jobs into isolated workspaces</p>
                    </div>
                    <button 
                        onClick={() => setShowModal(true)}
                        className="bg-brand-600 hover:bg-brand-500 text-white px-6 py-2.5 rounded-lg font-medium shadow-lg shadow-brand-500/20 transition-all flex items-center space-x-2"
                    >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path></svg>
                        <span>New Workspace</span>
                    </button>
                </header>

                {/* Workspaces Grid */}
                {loading ? (
                    <div className="text-center text-slate-400 py-12">
                        <svg className="animate-spin h-8 w-8 mx-auto mb-4" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Loading workspaces...
                    </div>
                ) : workspaces.length === 0 ? (
                    <div className="glass rounded-xl p-12 text-center border border-white/5">
                        <svg className="w-16 h-16 mx-auto mb-4 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"></path>
                        </svg>
                        <p className="text-slate-400 text-lg mb-2">No workspaces yet</p>
                        <p className="text-slate-500 text-sm">Create your first workspace to organize your jobs</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {workspaces.map((ws) => (
                            <div key={ws.id} className="glass p-6 rounded-xl border border-white/5 hover:border-brand-500/30 transition-all group">
                                <div className="flex items-start justify-between mb-4">
                                    <div className="flex-1">
                                        <h3 className="text-lg font-semibold text-white mb-1">{ws.name}</h3>
                                        {ws.description && (
                                            <p className="text-sm text-slate-400 mb-3">{ws.description}</p>
                                        )}
                                        <div className="flex items-center space-x-2">
                                            <code className="text-xs bg-dark-surface px-2 py-1 rounded text-slate-500 font-mono">
                                                {ws.id.slice(0, 12)}...
                                            </code>
                                            <button
                                                onClick={() => copyToClipboard(ws.id)}
                                                className="text-slate-500 hover:text-brand-400 transition-colors"
                                                title="Copy full ID"
                                            >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
                                                </svg>
                                            </button>
                                        </div>
                                    </div>
                                    <svg className="w-8 h-8 text-brand-500 opacity-50 group-hover:opacity-100 transition-opacity" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
                                    </svg>
                                </div>

                                <div className="flex items-center justify-between pt-4 border-t border-white/5">
                                    <Link 
                                        to={`/jobs?workspace=${ws.id}`}
                                        className="text-brand-400 hover:text-brand-300 font-medium text-sm flex items-center"
                                    >
                                        <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"></path>
                                        </svg>
                                        View Jobs
                                    </Link>
                                    <button
                                        onClick={() => deleteWorkspace(ws.id, ws.name)}
                                        className="text-red-400 hover:text-red-300 text-sm flex items-center"
                                    >
                                        <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                        </svg>
                                        Delete
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {/* Create Modal */}
                {showModal && (
                    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
                        <div className="glass p-8 rounded-xl border border-white/10 w-full max-w-md">
                            <h3 className="text-xl font-bold text-white mb-6">Create Workspace</h3>
                            <form onSubmit={handleCreate} className="space-y-5">
                                <div>
                                    <label className="block text-sm font-medium text-slate-400 mb-2">Workspace Name</label>
                                    <input
                                        type="text"
                                        value={formData.name}
                                        onChange={(e) => setFormData({...formData, name: e.target.value})}
                                        className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                                        placeholder="Production"
                                        required
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-400 mb-2">Description (Optional)</label>
                                    <textarea
                                        value={formData.description}
                                        onChange={(e) => setFormData({...formData, description: e.target.value})}
                                        className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500 resize-none"
                                        placeholder="Main production environment for live scraping jobs"
                                        rows={3}
                                    />
                                </div>
                                <div className="flex space-x-3 pt-4 border-t border-white/10">
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setShowModal(false);
                                            setFormData({ name: '', description: '' });
                                        }}
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
        </Layout>
    );
}
