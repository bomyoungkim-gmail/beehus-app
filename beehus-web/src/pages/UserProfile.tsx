import { useEffect, useState } from 'react';
import axios from 'axios';
import Layout from '../components/Layout';
import { formatDateTime } from '../utils/datetime';
import { useAuth } from '../context/AuthContext';

const apiBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function UserProfile() {
  const { user, fetchCurrentUser } = useAuth();
  const [fullName, setFullName] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (user?.full_name) {
      setFullName(user.full_name);
    }
  }, [user]);

  const handleProfileSave = async () => {
    setMessage('');
    setError('');
    try {
      await axios.patch(`${apiBaseUrl}/users/me`, { full_name: fullName });
      await fetchCurrentUser();
      setMessage('Profile updated.');
    } catch (err) {
      setError('Failed to update profile.');
    }
  };

  const handlePasswordChange = async () => {
    setMessage('');
    setError('');
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    try {
      await axios.patch(`${apiBaseUrl}/users/me`, {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setMessage('Password updated.');
    } catch (err) {
      setError('Failed to update password.');
    }
  };

  return (
    <Layout>
      <div className="p-8 max-w-4xl mx-auto space-y-6">
        <header>
          <h2 className="text-2xl font-bold text-white">My Profile</h2>
          <p className="text-slate-400">Manage your account details.</p>
        </header>

        {message && <div className="p-3 rounded bg-green-500/20 text-green-300 text-sm">{message}</div>}
        {error && <div className="p-3 rounded bg-red-500/20 text-red-300 text-sm">{error}</div>}

        <div className="glass rounded-xl border border-white/5 p-6 space-y-4">
          <h3 className="text-lg font-semibold text-white">Profile Information</h3>
          <div className="grid md:grid-cols-2 gap-4 text-sm text-slate-300">
            <div>
              <p className="text-xs uppercase text-slate-500">Email</p>
              <p>{user?.email}</p>
            </div>
            <div>
              <p className="text-xs uppercase text-slate-500">Role</p>
              <p>{user?.role}</p>
            </div>
            <div>
              <p className="text-xs uppercase text-slate-500">Created</p>
              <p>{user?.created_at ? formatDateTime(user.created_at) : 'N/A'}</p>
            </div>
            <div>
              <p className="text-xs uppercase text-slate-500">Last Login</p>
              <p>{user?.last_login ? formatDateTime(user.last_login) : 'Never'}</p>
            </div>
          </div>
        </div>

        <div className="glass rounded-xl border border-white/5 p-6 space-y-4">
          <h3 className="text-lg font-semibold text-white">Edit Profile</h3>
          <input
            type="text"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            className="w-full px-4 py-3 bg-dark-bg/50 border border-dark-border rounded-lg text-white"
            placeholder="Full name"
          />
          <button
            onClick={handleProfileSave}
            className="px-4 py-2 rounded bg-brand-600 text-white text-sm font-semibold"
          >
            Save Changes
          </button>
        </div>

        <div className="glass rounded-xl border border-white/5 p-6 space-y-4">
          <h3 className="text-lg font-semibold text-white">Change Password</h3>
          <input
            type="password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            className="w-full px-4 py-3 bg-dark-bg/50 border border-dark-border rounded-lg text-white"
            placeholder="Current password"
          />
          <input
            type="password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            className="w-full px-4 py-3 bg-dark-bg/50 border border-dark-border rounded-lg text-white"
            placeholder="New password"
          />
          <input
            type="password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            className="w-full px-4 py-3 bg-dark-bg/50 border border-dark-border rounded-lg text-white"
            placeholder="Confirm new password"
          />
          <button
            onClick={handlePasswordChange}
            className="px-4 py-2 rounded bg-brand-600 text-white text-sm font-semibold"
          >
            Update Password
          </button>
        </div>
      </div>
    </Layout>
  );
}
