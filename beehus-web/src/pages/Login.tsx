import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Link, useNavigate } from 'react-router-dom';
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

      const response = await axios.post(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/auth/login`, formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      });
      
      const { access_token, refresh_token } = response.data;
      await login(access_token, refresh_token);
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
            <img
                src="/beehus_branco.png"
                alt="Beehus"
                className="w-72 max-w-full h-auto mx-auto mb-4"
                onError={(e) => {
                  e.currentTarget.onerror = null;
                  e.currentTarget.src = "/beehus-logo.svg";
                }}
            />
            <h1 className="text-3xl font-bold text-white tracking-tight sr-only">Beehus Console</h1>
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

        <div className="mt-4 text-center">
            <Link to="/forgot-password" className="text-sm text-brand-500 hover:text-brand-400">
                Forgot password?
            </Link>
        </div>
        
        <div className="mt-6 text-center">
            <p className="text-xs text-slate-500">Protected by Beehus Guard™ v2.0</p>
        </div>
      </div>
    </div>
  );
}
