import { useEffect, useRef, useState } from 'react';
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
  const [filterStatus, setFilterStatus] = useState<'all' | 'running' | 'queued'>('all');
  const fetchInFlightRef = useRef(false);
  
  // Modal state


  useEffect(() => {
    const fetchData = async () => {
      if (fetchInFlightRef.current) {
        return;
      }
      if (document.hidden) {
        return;
      }
      fetchInFlightRef.current = true;
      try {
        const [statsRes, runsRes] = await Promise.all([
          axios.get(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/dashboard/stats`),
          axios.get(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/dashboard/recent-runs?limit=5`)
        ]);
        setStats(statsRes.data);
        setRecentRuns(runsRes.data);
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error);
      } finally {
        setLoading(false);
        fetchInFlightRef.current = false;
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 15000); // Refresh every 15s

    const onVisibilityChange = () => {
      if (!document.hidden) {
        fetchData();
      }
    };
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisibilityChange);
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

  return (
    <Layout>
        <div className="p-8 max-w-7xl mx-auto space-y-8">
            <header className="flex justify-between items-center">
                <div>
                    <h2 className="text-2xl font-bold text-white">Dashboard Overview</h2>
                    <p className="text-slate-400">System health and recent activities</p>
                </div>
            </header>

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
                    <div className="flex items-center space-x-4">
                        <h3 className="font-semibold text-lg text-white">Live Executions</h3>
                        <div className="flex bg-white/5 rounded-lg p-1 space-x-1">
                            {/* Filter Buttons */}
                            {(['all', 'running', 'queued'] as const).map((status) => (
                                <button
                                    key={status}
                                    onClick={() => setFilterStatus(status)}
                                    className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
                                        filterStatus === status 
                                            ? 'bg-brand-500 text-white shadow-lg shadow-brand-500/20' 
                                            : 'text-slate-400 hover:text-white hover:bg-white/5'
                                    }`}
                                >
                                    {status.charAt(0).toUpperCase() + status.slice(1)}
                                    {status === 'all' ? '' : (status === 'running' ? ' (Active)' : '')}
                                </button>
                            ))}
                        </div>
                    </div>
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
                        {recentRuns
                            .filter(run => filterStatus === 'all' || run.status === filterStatus)
                            .length === 0 ? (
                            <tr>
                                <td colSpan={5} className="px-6 py-8 text-center text-slate-500">
                                    {filterStatus === 'all' 
                                        ? "No recent runs." 
                                        : `No ${filterStatus} runs found.`}
                                </td>
                            </tr>
                        ) : (
                            recentRuns
                                .filter(run => filterStatus === 'all' || run.status === filterStatus)
                                .map((run) => (
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
