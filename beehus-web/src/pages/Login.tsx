import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    
    try {
      // For MVP, we point to localhost:8000. In prod, use env var.
      // Use FormData for OAuth2PasswordRequestForm
      const formData = new URLSearchParams();
      formData.append('username', email);
      formData.append('password', password);

      const response = await axios.post('http://localhost:8000/auth/login', formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      });
      
      const { access_token } = response.data;
      login(access_token);
      navigate('/');
    } catch (err: any) {
      console.error(err);
      setError('Invalid email or password');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[url('https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=2072&auto=format&fit=crop')] bg-cover bg-center">
      <div className="absolute inset-0 bg-dark-bg/90 backdrop-blur-sm"></div>
      
      <div className="relative w-full max-w-md p-8 glass rounded-2xl shadow-2xl border border-white/10 mx-4">
        <div className="text-center mb-8">
            <div className="w-16 h-16 bg-brand-500 rounded-xl mx-auto flex items-center justify-center shadow-lg shadow-brand-500/30 mb-4">
                <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
            </div>
            <h1 className="text-3xl font-bold text-white tracking-tight">Beehus Console</h1>
            <p className="text-slate-400 mt-2">Secure Automation Platform</p>
        </div>
        
        <form onSubmit={handleSubmit} className="space-y-6">
            {error && (
                <div className="p-3 rounded bg-red-500/20 text-red-300 text-sm text-center border border-red-500/30">{error}</div>
            )}
            <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">Workspace Email</label>
                <input 
                    type="email" 
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full px-4 py-3 bg-dark-bg/50 border border-dark-border rounded-lg focus:ring-2 focus:ring-brand-500 text-white outline-none transition-all" 
                    placeholder="name@company.com" 
                />
            </div>
            <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">Passkey</label>
                <input 
                    type="password" 
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full px-4 py-3 bg-dark-bg/50 border border-dark-border rounded-lg focus:ring-2 focus:ring-brand-500 text-white outline-none transition-all" 
                    placeholder="••••••••" 
                />
            </div>
            <button type="submit" className="w-full py-3.5 bg-brand-600 hover:bg-brand-500 text-white rounded-lg font-semibold shadow-lg shadow-brand-500/30 transition-all transform hover:scale-[1.02] active:scale-95">
                Enter Console
            </button>
        </form>
        
        <div className="mt-6 text-center">
            <p className="text-xs text-slate-500">Protected by Beehus Guard™ v2.0</p>
        </div>
      </div>
    </div>
  );
}
