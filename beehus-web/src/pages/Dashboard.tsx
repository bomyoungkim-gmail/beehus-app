import React, { useEffect, useState } from 'react';
import Layout from '../components/Layout';
import { Link } from 'react-router-dom';
import axios from 'axios';

interface DashboardStats {
    successful_runs: number;
    failed_runs: number;
    running_runs: number;
    active_workers: number;
    browser_sessions: number;
    success_trend: number;
}

interface RecentRun {
    run_id: string;
    job_id: string;
    connector: string;
    status: string;
    node: string;
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentRuns, setRecentRuns] = useState<RecentRun[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [credentials, setCredentials] = useState({ user: '', password: '' });
  const [testLoading, setTestLoading] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statsRes, runsRes] = await Promise.all([
          axios.get('http://localhost:8000/dashboard/stats'),
          axios.get('http://localhost:8000/dashboard/recent-runs?limit=5')
        ]);
        setStats(statsRes.data);
        setRecentRuns(runsRes.data);
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 5000); // Refresh every 5s
    return () => clearInterval(interval);
  }, []);

  const handleTestSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setTestLoading(true);
    
    try {
      const res = await axios.post('http://localhost:8000/test/jpmorgan', null, {
        params: {
          user: credentials.user,
          password: credentials.password
        }
      });
      setShowModal(false);
      setCredentials({ user: '', password: '' });
      alert(`Test Started! Run ID: ${res.data.run_id}`);
      window.location.href = `/live/${res.data.run_id}`;
    } catch (e) {
      alert('Error triggering test');
      console.error(e);
    } finally {
      setTestLoading(false);
    }
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

  return (
    <Layout>
        <div className="p-8 max-w-7xl mx-auto space-y-8">
            <header className="flex justify-between items-center">
                <div>
                    <h2 className="text-2xl font-bold text-white">Dashboard Overview</h2>
                    <p className="text-slate-400">System health and recent activities</p>
                </div>
                <button className="bg-brand-600 hover:bg-brand-500 text-white px-6 py-2.5 rounded-lg font-medium shadow-lg shadow-brand-500/20 transition-all flex items-center space-x-2">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path></svg>
                    <span>New Job</span>
                </button>
            </header>

            {/* Test Actions */}
            <div className="flex space-x-4">
                <button 
                    onClick={() => setShowModal(true)}
                    className="bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 border border-blue-500/30 px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center space-x-2"
                >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                    <span>Test JPMorgan Login</span>
                </button>
            </div>

            {/* Modal */}
            {showModal && (
                <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
                    <div className="glass p-8 rounded-xl border border-white/10 w-full max-w-md">
                        <h3 className="text-xl font-bold text-white mb-4">JPMorgan Test Credentials</h3>
                        <form onSubmit={handleTestSubmit} className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-400 mb-2">Username</label>
                                <input
                                    type="text"
                                    value={credentials.user}
                                    onChange={(e) => setCredentials({...credentials, user: e.target.value})}
                                    className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                                    placeholder="Enter username"
                                    required
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-400 mb-2">Password</label>
                                <input
                                    type="password"
                                    value={credentials.password}
                                    onChange={(e) => setCredentials({...credentials, password: e.target.value})}
                                    className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                                    placeholder="Enter password"
                                    required
                                />
                            </div>
                            <div className="flex space-x-3 pt-2">
                                <button
                                    type="button"
                                    onClick={() => {
                                        setShowModal(false);
                                        setCredentials({ user: '', password: '' });
                                    }}
                                    className="flex-1 bg-white/5 hover:bg-white/10 text-slate-300 px-4 py-2.5 rounded-lg font-medium transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={testLoading}
                                    className="flex-1 bg-brand-600 hover:bg-brand-500 text-white px-4 py-2.5 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    {testLoading ? 'Starting...' : 'Start Test'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* Stats Grid */}
            {loading ? (
                <div className="text-center text-slate-400 py-12">Loading stats...</div>
            ) : stats && (
                <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                    <div className="glass p-6 rounded-xl border-l-4 border-green-500">
                        <p className="text-slate-400 text-sm font-medium">Successful Runs</p>
                        <p className="text-3xl font-bold text-white mt-1">{stats.successful_runs.toLocaleString()}</p>
                        <p className={`text-xs mt-2 flex items-center ${stats.success_trend >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            <svg className="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d={stats.success_trend >= 0 ? "M5 10l7-7m0 0l7 7m-7-7v18" : "M19 14l-7 7m0 0l-7-7m7 7V3"}></path>
                            </svg>
                            {stats.success_trend >= 0 ? '+' : ''}{stats.success_trend}% this week
                        </p>
                    </div>
                    <div className="glass p-6 rounded-xl border-l-4 border-red-500">
                        <p className="text-slate-400 text-sm font-medium">Failed Jobs</p>
                        <p className="text-3xl font-bold text-white mt-1">{stats.failed_runs.toLocaleString()}</p>
                        <p className="text-red-400 text-xs mt-2">Total failures</p>
                    </div>
                    <div className="glass p-6 rounded-xl border-l-4 border-brand-500">
                        <p className="text-slate-400 text-sm font-medium">Active Workers</p>
                        <p className="text-3xl font-bold text-white mt-1">{stats.active_workers}</p>
                        <p className="text-brand-400 text-xs mt-2">{stats.active_workers > 0 ? 'Running now' : 'Idle'}</p>
                    </div>
                    <div className="glass p-6 rounded-xl border-l-4 border-purple-500">
                        <p className="text-slate-400 text-sm font-medium">Browser Sessions</p>
                        <p className="text-3xl font-bold text-white mt-1">{stats.browser_sessions}</p>
                        <p className="text-purple-400 text-xs mt-2">Selenium Grid</p>
                    </div>
                </div>
            )}

            {/* Recent Runs Table */}
            <div className="glass rounded-xl overflow-hidden border border-white/5">
                <div className="p-6 border-b border-white/5 flex justify-between items-center">
                    <h3 className="font-semibold text-lg text-white">Live Executions</h3>
                    <Link to="/runs" className="text-sm text-brand-400 hover:text-brand-300">View All</Link>
                </div>
                <table className="w-full text-left">
                    <thead className="bg-white/5 text-slate-400 uppercase text-xs">
                        <tr>
                            <th className="px-6 py-4">Run ID</th>
                            <th className="px-6 py-4">Connector</th>
                            <th className="px-6 py-4">Status</th>
                            <th className="px-6 py-4">Node</th>
                            <th className="px-6 py-4">Action</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5 text-sm">
                        {recentRuns.length === 0 ? (
                            <tr>
                                <td colSpan={5} className="px-6 py-8 text-center text-slate-500">
                                    No recent runs. Click "Test JPMorgan Login" to start one!
                                </td>
                            </tr>
                        ) : (
                            recentRuns.map((run) => (
                                <tr key={run.run_id} className="hover:bg-white/5 transition-colors">
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
                                        <Link to={`/live/${run.run_id}`} className="text-white hover:text-brand-400 font-medium flex items-center">
                                            <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path></svg>
                                            Watch
                                        </Link>
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
