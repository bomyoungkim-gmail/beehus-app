import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import Layout from '../components/Layout';
import { formatDateTime } from '../utils/datetime';

interface User {
  id: string;
  email: string;
  full_name?: string | null;
  role: string;
  is_active: boolean;
  created_at: string;
  last_login?: string | null;
}

const apiBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function Users() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [roleFilter, setRoleFilter] = useState<'all' | 'admin' | 'user'>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all');
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteFullName, setInviteFullName] = useState('');
  const [inviteRole, setInviteRole] = useState<'admin' | 'user'>('user');
  const [inviteResult, setInviteResult] = useState<{ link: string; emailSent: boolean } | null>(null);
  const [editUser, setEditUser] = useState<User | null>(null);
  const [editRole, setEditRole] = useState<'admin' | 'user'>('user');
  const [error, setError] = useState('');

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${apiBaseUrl}/users`);
      setUsers(response.data);
    } catch (err) {
      setError('Failed to load users.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const filteredUsers = useMemo(() => {
    return users.filter((user) => {
      if (roleFilter !== 'all' && user.role !== roleFilter) return false;
      if (statusFilter !== 'all') {
        const isActive = user.is_active ? 'active' : 'inactive';
        if (isActive !== statusFilter) return false;
      }
      return true;
    });
  }, [users, roleFilter, statusFilter]);

  const handleInvite = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    setInviteResult(null);
    try {
      const response = await axios.post(`${apiBaseUrl}/users/invite`, {
        email: inviteEmail,
        full_name: inviteFullName || null,
        role: inviteRole,
      });
      setInviteResult({
        link: response.data.invitation_link,
        emailSent: response.data.email_sent,
      });
      setInviteEmail('');
      setInviteFullName('');
      setInviteRole('user');
      fetchUsers();
    } catch (err) {
      setError('Failed to send invitation.');
    }
  };

  const handleUpdateUser = async () => {
    if (!editUser) return;
    setError('');
    try {
      await axios.patch(`${apiBaseUrl}/users/${editUser.id}`, {
        role: editRole,
      });
      setEditUser(null);
      fetchUsers();
    } catch (err) {
      setError('Failed to update user.');
    }
  };

  const handleToggleActive = async (user: User) => {
    const action = user.is_active ? 'deactivate' : 'activate';
    const confirm = window.confirm(`Are you sure you want to ${action} ${user.email}?`);
    if (!confirm) return;
    try {
      if (user.is_active) {
        await axios.delete(`${apiBaseUrl}/users/${user.id}`);
      } else {
        await axios.post(`${apiBaseUrl}/users/${user.id}/activate`);
      }
      fetchUsers();
    } catch (err) {
      setError(`Failed to ${action} user.`);
    }
  };

  return (
    <Layout>
      <div className="p-8 max-w-6xl mx-auto space-y-6">
        <header className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-white">User Management</h2>
            <p className="text-slate-400">Invite and manage collaborators.</p>
          </div>
          <button
            onClick={() => setInviteOpen(true)}
            className="px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-500 text-white text-sm font-semibold"
          >
            Invite User
          </button>
        </header>

        {error && (
          <div className="p-3 rounded bg-red-500/20 text-red-300 text-sm border border-red-500/30">
            {error}
          </div>
        )}

        <div className="flex flex-wrap gap-3">
          <select
            value={roleFilter}
            onChange={(event) => setRoleFilter(event.target.value as 'all' | 'admin' | 'user')}
            className="px-3 py-2 rounded bg-dark-surface border border-dark-border text-sm text-slate-200"
          >
            <option value="all">All Roles</option>
            <option value="admin">Admins</option>
            <option value="user">Users</option>
          </select>
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as 'all' | 'active' | 'inactive')}
            className="px-3 py-2 rounded bg-dark-surface border border-dark-border text-sm text-slate-200"
          >
            <option value="all">All Status</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </div>

        <div className="glass rounded-xl border border-white/5 overflow-hidden">
          <table className="w-full text-left">
            <thead className="bg-white/5 text-slate-400 uppercase text-xs">
              <tr>
                <th className="px-6 py-4">User</th>
                <th className="px-6 py-4">Role</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4">Last Login</th>
                <th className="px-6 py-4">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 text-sm">
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-slate-500">
                    Loading users...
                  </td>
                </tr>
              ) : filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-slate-500">
                    No users match the selected filters.
                  </td>
                </tr>
              ) : (
                filteredUsers.map((user) => (
                  <tr key={user.id} className="hover:bg-white/5">
                    <td className="px-6 py-4">
                      <div className="text-white font-medium">{user.full_name || user.email}</div>
                      <div className="text-xs text-slate-400">{user.email}</div>
                    </td>
                    <td className="px-6 py-4">
                      <span className="px-2.5 py-1 rounded-full text-xs bg-white/10 text-slate-200">
                        {user.role}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`px-2.5 py-1 rounded-full text-xs ${
                          user.is_active ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                        }`}
                      >
                        {user.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-slate-400">
                      {user.last_login ? formatDateTime(user.last_login) : 'Never'}
                    </td>
                    <td className="px-6 py-4 space-x-2">
                      <button
                        onClick={() => {
                          setEditUser(user);
                          setEditRole(user.role as 'admin' | 'user');
                        }}
                        className="text-brand-400 hover:text-brand-300 text-sm"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleToggleActive(user)}
                        className="text-slate-400 hover:text-white text-sm"
                      >
                        {user.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {inviteOpen && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-dark-surface border border-white/10 rounded-xl p-6 w-full max-w-md">
            <h3 className="text-lg font-semibold text-white mb-4">Invite User</h3>
            <form className="space-y-4" onSubmit={handleInvite}>
              <input
                type="email"
                value={inviteEmail}
                onChange={(event) => setInviteEmail(event.target.value)}
                className="w-full px-3 py-2 rounded bg-dark-bg border border-dark-border text-white"
                placeholder="Email"
                required
              />
              <input
                type="text"
                value={inviteFullName}
                onChange={(event) => setInviteFullName(event.target.value)}
                className="w-full px-3 py-2 rounded bg-dark-bg border border-dark-border text-white"
                placeholder="Full name (optional)"
              />
              <select
                value={inviteRole}
                onChange={(event) => setInviteRole(event.target.value as 'admin' | 'user')}
                className="w-full px-3 py-2 rounded bg-dark-bg border border-dark-border text-white"
              >
                <option value="user">User</option>
                <option value="admin">Admin</option>
              </select>
              {inviteResult && (
                <div className="text-xs text-slate-300 space-y-2">
                  <p>
                    Invitation link:
                    <a className="text-brand-400 break-all block" href={inviteResult.link}>
                      {inviteResult.link}
                    </a>
                  </p>
                  <p>{inviteResult.emailSent ? 'Invitation email sent.' : 'Email not sent.'}</p>
                </div>
              )}
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setInviteOpen(false);
                    setInviteResult(null);
                  }}
                  className="px-4 py-2 text-sm text-slate-300 hover:text-white"
                >
                  Cancel
                </button>
                <button type="submit" className="px-4 py-2 rounded bg-brand-600 text-white text-sm">
                  Send Invite
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editUser && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-dark-surface border border-white/10 rounded-xl p-6 w-full max-w-sm">
            <h3 className="text-lg font-semibold text-white mb-2">Edit User</h3>
            <p className="text-sm text-slate-400 mb-4">{editUser.email}</p>
            <select
              value={editRole}
              onChange={(event) => setEditRole(event.target.value as 'admin' | 'user')}
              className="w-full px-3 py-2 rounded bg-dark-bg border border-dark-border text-white"
            >
              <option value="user">User</option>
              <option value="admin">Admin</option>
            </select>
            <div className="flex justify-end gap-2 mt-4">
              <button
                type="button"
                onClick={() => setEditUser(null)}
                className="px-4 py-2 text-sm text-slate-300 hover:text-white"
              >
                Cancel
              </button>
              <button type="button" onClick={handleUpdateUser} className="px-4 py-2 rounded bg-brand-600 text-white text-sm">
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </Layout>
  );
}
