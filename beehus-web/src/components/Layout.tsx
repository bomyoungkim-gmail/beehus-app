import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useEffect, useMemo, useState } from 'react';

export default function Layout({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const { logout, isAdmin } = useAuth();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(new Date());
    }, 1000);

    return () => window.clearInterval(timer);
  }, []);

  const timezone = useMemo(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone,
    [],
  );

  const formatDateTime = (date: Date) => {
    const day = String(date.getDate()).padStart(2, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const year = date.getFullYear();
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    return `${day}/${month}/${year} - ${hours}:${minutes}:${seconds}`;
  };

  const isActive = (path: string) => 
    pathname === path 
      ? 'bg-brand-500/10 text-brand-500 border border-brand-500/20' 
      : 'text-slate-400 hover:bg-dark-surface hover:text-white';

  return (
    <div className="flex h-screen bg-dark-bg text-slate-200">
      {/* SIDEBAR */}
      <aside className={`glass border-r border-dark-border flex flex-col z-20 transition-all duration-300 ${isCollapsed ? 'w-20' : 'w-64'}`}>
        <div className="p-6 flex items-center space-x-3 border-b border-dark-border/50 relative">
          <img
            src="/beehus-logo.svg"
            alt="Beehus logo"
            className="w-8 h-8 rounded-md bg-white/90 p-0.5 shadow-lg shadow-brand-500/20 shrink-0"
          />
          {!isCollapsed && <span className="font-bold text-lg tracking-tight whitespace-nowrap overflow-hidden transition-opacity duration-300">Beehus</span>}
          
          <button 
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="absolute -right-3 top-1/2 transform -translate-y-1/2 w-6 h-6 bg-dark-surface border border-dark-border rounded-full flex items-center justify-center text-slate-400 hover:text-white hover:border-brand-500 transition-all shadow-lg hover:shadow-brand-500/20 z-50 cursor-pointer"
          >
             <svg className={`w-3 h-3 transition-transform duration-300 ${isCollapsed ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7"></path></svg>
          </button>
        </div>
        
        <nav className="flex-1 p-4 space-y-2 overflow-hidden">
          <Link to="/" className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${isActive('/')} ${isCollapsed ? 'justify-center px-2' : ''}`} title={isCollapsed ? "Dashboard" : ""}>
            <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"></path></svg>
            {!isCollapsed && <span className="font-medium whitespace-nowrap">Dashboard</span>}
          </Link>
          <Link to="/workspaces" className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${isActive('/workspaces')} ${isCollapsed ? 'justify-center px-2' : ''}`} title={isCollapsed ? "Workspaces" : ""}>
            <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
            {!isCollapsed && <span>Workspaces</span>}
          </Link>
          <Link to="/credentials" className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${isActive('/credentials')} ${isCollapsed ? 'justify-center px-2' : ''}`} title={isCollapsed ? "Credential Vault" : ""}>
            <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z"></path></svg>
            {!isCollapsed && <span>Credentials</span>}
          </Link>
          <Link to="/jobs" className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${isActive('/jobs')} ${isCollapsed ? 'justify-center px-2' : ''}`} title={isCollapsed ? "Scrape Jobs" : ""}>
            <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
            {!isCollapsed && <span>Scrape Jobs</span>}
          </Link>
          <div className={`my-2 border-t border-dark-border/70 ${isCollapsed ? 'mx-1' : 'mx-2'}`} />
            <Link to="/runs" className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${isActive('/runs')} ${isCollapsed ? 'justify-center px-2' : ''}`} title={isCollapsed ? "Execution History" : ""}>
                <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                {!isCollapsed && <span>Runs</span>}
            </Link>
          <Link to="/downloads" className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${isActive('/downloads')} ${isCollapsed ? 'justify-center px-2' : ''}`} title={isCollapsed ? "Downloads" : ""}>
            <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
            {!isCollapsed && <span>Downloads</span>}
          </Link>
          <div className={`my-2 border-t border-dark-border/70 ${isCollapsed ? 'mx-1' : 'mx-2'}`} />
          {isAdmin && (
            <Link to="/users" className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${isActive('/users')} ${isCollapsed ? 'justify-center px-2' : ''}`} title={isCollapsed ? "Users" : ""}>
              <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 20h5v-2a4 4 0 00-5-3.87M7 20H2v-2a4 4 0 015-3.87m10-3.13a4 4 0 11-8 0 4 4 0 018 0zM9 7a4 4 0 108 0 4 4 0 00-8 0z"></path></svg>
              {!isCollapsed && <span>Users</span>}
            </Link>
          )}
        </nav>
        
        <div className="p-4 border-t border-dark-border/50 overflow-hidden">
          <div className={`flex items-center ${isCollapsed ? 'justify-center' : 'justify-between'}`}>
            <div className={`flex items-center ${isCollapsed ? '' : 'space-x-3'}`}>
                <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-purple-500 to-pink-500 border-2 border-white/10 shrink-0"></div>
                {!isCollapsed && (
                    <div className="transition-opacity duration-300">
                        <p className="text-sm font-semibold text-white">User</p>
                        <p className="text-xs text-brand-500">Online</p>
                        <p className="text-[11px] text-slate-400">{formatDateTime(now)} ({timezone})</p>
                    </div>
                )}
            </div>
            {!isCollapsed && (
                <button onClick={logout} className="text-slate-500 hover:text-white transition-opacity duration-300">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
                </button>
            )}
          </div>
        </div>
      </aside>

      {/* CONTENT AREA */}
      <main className="flex-1 overflow-auto bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-slate-900 via-dark-bg to-black relative">
        {children}
      </main>
    </div>
  );
}
