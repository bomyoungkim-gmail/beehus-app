import React, { useEffect, useState } from "react";
import axios from "axios";
import Editor from "react-simple-code-editor";
import { highlight, languages } from "prismjs";
import "prismjs/components/prism-python";
import "prismjs/themes/prism-tomorrow.css";
import Layout from "../components/Layout";
import ConfirmModal from "../components/ui/ConfirmModal";
import { useToast } from "../context/ToastContext";
import { processorsApi } from "../api/processors";
import type { Processor } from "../api/processors";
import { formatDate, formatDateTime } from "../utils/datetime";

interface Credential {
  id: string;
  workspace_id: string;
  label: string;
  username: string;
  metadata: Record<string, any>;
  carteira?: string | null;
  enable_processing?: boolean;
  created_at: string;
  updated_at: string;
}

interface Workspace {
  id: string;
  name: string;
}

export default function Credentials() {
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deleteModal, setDeleteModal] = useState<{
    isOpen: boolean;
    id: string;
    label: string;
  }>({
    isOpen: false,
    id: "",
    label: "",
  });

  const { showToast } = useToast();

  const [processorScript, setProcessorScript] = useState("");
  const [processorName, setProcessorName] = useState("");
  const [processors, setProcessors] = useState<Processor[]>([]);
  const [showProcessorHistory, setShowProcessorHistory] = useState(false);
  const [loadingProcessors, setLoadingProcessors] = useState(false);
  const [showScriptEditorModal, setShowScriptEditorModal] = useState(false);

  const [formData, setFormData] = useState<{
    workspace_id: string;
    label: string;
    username: string;
    password: string;
    metadata: Record<string, any>;
    carteira: string;
    enable_processing: boolean;
  }>({
    workspace_id: "",
    label: "",
    username: "",
    password: "",
    metadata: {},
    carteira: "",
    enable_processing: false,
  });

  const fetchCredentials = async () => {
    try {
      const res = await axios.get(
        `${import.meta.env.VITE_API_URL || "http://localhost:8000"}/credentials`,
      );
      setCredentials(res.data);
    } catch (error) {
      console.error("Failed to fetch credentials:", error);
    } finally {
      setLoading(false);
    }
  };

  const fetchWorkspaces = async () => {
    try {
      const res = await axios.get(
        `${import.meta.env.VITE_API_URL || "http://localhost:8000"}/workspaces`,
      );
      setWorkspaces(res.data);
    } catch (error) {
      console.error("Failed to fetch workspaces:", error);
    }
  };

  const resetProcessorState = () => {
    setProcessorScript("");
    setProcessorName("");
    setProcessors([]);
    setShowProcessorHistory(false);
    setLoadingProcessors(false);
    setShowScriptEditorModal(false);
  };

  const loadProcessors = async (credentialId: string) => {
    setLoadingProcessors(true);
    try {
      const procs = await processorsApi.listByCredential(credentialId);
      setProcessors(procs);

      const active = procs.find((proc) => proc.is_active);
      if (active) {
        const full = await processorsApi.get(active.id);
        setProcessorScript(full.script_content || "");
        setProcessorName(full.name);
      } else {
        setProcessorScript("");
        setProcessorName("");
      }
    } catch (error) {
      console.error("Failed to load processors:", error);
    } finally {
      setLoadingProcessors(false);
    }
  };

  const saveProcessor = async () => {
    if (!editingId) {
      return;
    }

    try {
      if (processors.length === 0) {
        await processorsApi.create({
          credential_id: editingId,
          name: processorName || `${formData.label || "Credential"} Processor`,
          script_content: processorScript,
        });
      } else {
        const active = processors.find((proc) => proc.is_active);
        if (active) {
          await processorsApi.update(active.id, {
            name: processorName,
            script_content: processorScript,
          });
        }
      }

      showToast("Processor saved successfully", "success");
      await loadProcessors(editingId);
    } catch (error) {
      showToast("Failed to save processor", "error");
    }
  };

  useEffect(() => {
    fetchCredentials();
    fetchWorkspaces();
  }, []);

  useEffect(() => {
    if (editingId) {
      loadProcessors(editingId);
    } else {
      resetProcessorState();
    }
  }, [editingId]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);

    try {
      if (editingId) {
        // Update existing credential
        await axios.put(
          `${import.meta.env.VITE_API_URL || "http://localhost:8000"}/credentials/${editingId}`,
          formData,
        );
        showToast("Credential updated successfully", "success");
      } else {
        // Create new credential
        await axios.post(
          `${import.meta.env.VITE_API_URL || "http://localhost:8000"}/credentials`,
          formData,
        );
        showToast("Credential created successfully", "success");
      }

      setShowModal(false);
      setFormData({
        workspace_id: "",
        label: "",
        username: "",
        password: "",
        metadata: {},
        carteira: "",
        enable_processing: false,
      });
      setEditingId(null);
      resetProcessorState();
      fetchCredentials();
    } catch (error) {
      showToast(
        editingId ? "Error updating credential" : "Error creating credential",
        "error",
      );
      console.error(error);
    } finally {
      setCreating(false);
    }
  };

  const handleEdit = (credential: Credential) => {
    setFormData({
      workspace_id: credential.workspace_id,
      label: credential.label,
      username: credential.username,
      password: "", // Don't populate password for security
      metadata: credential.metadata,
      carteira: credential.carteira || "",
      enable_processing: credential.enable_processing || false,
    });
    setEditingId(credential.id);
    setShowModal(true);
  };

  const handleDelete = (id: string, label: string) => {
    setDeleteModal({ isOpen: true, id, label });
  };

  const confirmDelete = async () => {
    try {
      await axios.delete(
        `${import.meta.env.VITE_API_URL || "http://localhost:8000"}/credentials/${deleteModal.id}`,
      );
      showToast("Credential deleted successfully", "success");
      fetchCredentials();
    } catch (error) {
      showToast("Error deleting credential", "error");
      console.error(error);
    } finally {
      setDeleteModal({ isOpen: false, id: "", label: "" });
    }
  };

  const getWorkspaceName = (workspaceId: string) => {
    const workspace = workspaces.find((w) => w.id === workspaceId);
    return workspace ? workspace.name : workspaceId.slice(0, 8);
  };

  return (
    <Layout>
      <div className="p-8 max-w-7xl mx-auto space-y-8">
        <header className="flex justify-between items-center">
          <div>
            <h2 className="text-2xl font-bold text-white">Credential Vault</h2>
            <p className="text-slate-400">
              Manage secure credentials for scraping jobs
            </p>
          </div>
          <button
            onClick={() => {
              setEditingId(null);
              setFormData({
                workspace_id: "",
                label: "",
                username: "",
                password: "",
                metadata: {},
                carteira: "",
                enable_processing: false,
              });
              resetProcessorState();
              setShowModal(true);
            }}
            className="bg-brand-600 hover:bg-brand-500 text-white px-6 py-2.5 rounded-lg font-medium shadow-lg shadow-brand-500/20 transition-all flex items-center space-x-2"
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M12 6v6m0 0v6m0-6h6m-6 0H6"
              ></path>
            </svg>
            <span>New Credential</span>
          </button>
        </header>

        {/* Credentials Table */}
        <div className="glass rounded-xl overflow-hidden border border-white/5">
          <table className="w-full text-left">
            <thead className="bg-white/5 text-slate-400 uppercase text-xs">
              <tr>
                <th className="px-6 py-4">Label</th>
                <th className="px-6 py-4">Username</th>
                <th className="px-6 py-4">Workspace</th>
                <th className="px-6 py-4">Created</th>
                <th className="px-6 py-4">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 text-sm">
              {loading ? (
                <tr>
                  <td
                    colSpan={5}
                    className="px-6 py-8 text-center text-slate-400"
                  >
                    Loading credentials...
                  </td>
                </tr>
              ) : credentials.length === 0 ? (
                <tr>
                  <td
                    colSpan={5}
                    className="px-6 py-8 text-center text-slate-500"
                  >
                    No credentials yet. Create your first credential!
                  </td>
                </tr>
              ) : (
                credentials.map((cred) => (
                  <tr
                    key={cred.id}
                    className="hover:bg-white/5 transition-colors"
                  >
                    <td className="px-6 py-4">
                      <div>
                        <p className="font-semibold text-white">{cred.label}</p>
                        <p className="text-xs text-slate-500 font-mono">
                          #{cred.id.slice(0, 8)}
                        </p>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-slate-300 font-mono text-sm">
                      {cred.username}
                    </td>
                    <td className="px-6 py-4 text-slate-300">
                      {getWorkspaceName(cred.workspace_id)}
                    </td>
                    <td className="px-6 py-4 text-slate-400 text-xs">
                      {formatDate(cred.created_at)}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center space-x-3">
                        <button
                          onClick={() => handleEdit(cred)}
                          className="text-brand-400 hover:text-brand-300 font-medium flex items-center"
                        >
                          <svg
                            className="w-4 h-4 mr-1"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth="2"
                              d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                            ></path>
                          </svg>
                          Edit
                        </button>
                        <button
                          onClick={() => handleDelete(cred.id, cred.label)}
                          className="text-red-400 hover:text-red-300 font-medium flex items-center"
                        >
                          <svg
                            className="w-4 h-4 mr-1"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth="2"
                              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                            ></path>
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

        {/* Create/Edit Modal */}
        {showModal && (
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div className="glass p-8 rounded-xl border border-white/10 w-full max-w-lg max-h-[90vh] overflow-y-auto">
              <h3 className="text-xl font-bold text-white mb-6">
                {editingId ? "Edit Credential" : "Create Credential"}
              </h3>
              <form onSubmit={handleCreate} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Workspace
                  </label>
                  <select
                    value={formData.workspace_id}
                    onChange={(e) =>
                      setFormData({ ...formData, workspace_id: e.target.value })
                    }
                    className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                    required
                    disabled={!!editingId}
                  >
                    <option value="" disabled>
                      Select a workspace
                    </option>
                    {workspaces.map((ws) => (
                      <option key={ws.id} value={ws.id}>
                        {ws.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Label
                  </label>
                  <input
                    type="text"
                    value={formData.label}
                    onChange={(e) =>
                      setFormData({ ...formData, label: e.target.value })
                    }
                    className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                    placeholder="e.g., BTG Account - Main"
                    required
                  />
                  <p className="text-xs text-slate-500 mt-1">
                    Friendly name to identify this credential
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Username
                  </label>
                  <input
                    type="text"
                    value={formData.username}
                    onChange={(e) =>
                      setFormData({ ...formData, username: e.target.value })
                    }
                    className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                    placeholder="user@example.com"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Password{" "}
                    {editingId && (
                      <span className="text-xs text-slate-500">
                        (leave blank to keep current)
                      </span>
                    )}
                  </label>
                  <input
                    type="password"
                    value={formData.password}
                    onChange={(e) =>
                      setFormData({ ...formData, password: e.target.value })
                    }
                    className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                    placeholder="••••••••"
                    required={!editingId}
                  />
                  <p className="text-xs text-slate-500 mt-1">
                    <svg
                      className="w-3 h-3 inline mr-1"
                      fill="currentColor"
                      viewBox="0 0 20 20"
                    >
                      <path
                        fillRule="evenodd"
                        d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z"
                        clipRule="evenodd"
                      ></path>
                    </svg>
                    Password is encrypted and stored securely
                  </p>
                </div>

                {/* Optional Banking Information */}
                <div className="border-t border-white/10 pt-4">
                  <h4 className="text-sm font-semibold text-slate-300 mb-3">
                    Banking Information (Optional)
                  </h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-400 mb-2">
                        Agência (AG)
                      </label>
                      <input
                        type="text"
                        value={formData.metadata?.agencia || ""}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            metadata: {
                              ...formData.metadata,
                              agencia: e.target.value,
                            },
                          })
                        }
                        className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                        placeholder="0001"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-400 mb-2">
                        Conta Corrente (CC)
                      </label>
                      <input
                        type="text"
                        value={formData.metadata?.conta_corrente || ""}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            metadata: {
                              ...formData.metadata,
                              conta_corrente: e.target.value,
                            },
                          })
                        }
                        className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                        placeholder="12345-6"
                      />
                    </div>
                  </div>
                  <p className="text-xs text-slate-500 mt-2">
                    These fields are optional and can be used by connectors that
                    require banking details
                  </p>
                </div>

                <div className="border-t border-white/10 pt-4">
                  <h4 className="text-sm font-semibold text-slate-300 mb-3">
                    Processing Settings
                  </h4>

                  <div>
                    <label className="block text-sm font-medium text-slate-400 mb-2">
                      Carteira (Portfolio)
                    </label>
                    <input
                      type="text"
                      value={formData.carteira}
                      onChange={(e) =>
                        setFormData({ ...formData, carteira: e.target.value })
                      }
                      className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                      placeholder="e.g., Portfolio ABC"
                    />
                    <p className="text-xs text-slate-500 mt-1">
                      Available to processors as the{" "}
                      <span className="font-mono">carteira</span> variable
                    </p>
                  </div>

                  <div className="mt-4">
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        id="enable-processing"
                        checked={formData.enable_processing}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            enable_processing: e.target.checked,
                          })
                        }
                        className="w-4 h-4"
                      />
                      <label
                        htmlFor="enable-processing"
                        className="text-sm font-medium cursor-pointer text-slate-300"
                      >
                        Process files automatically after download
                      </label>
                    </div>

                    {formData.enable_processing ? (
                      <div className="mt-2 p-3 border rounded bg-blue-50/10 border-blue-400/20">
                        <p className="text-sm text-blue-200">
                          Files will be processed automatically using the script
                          below
                        </p>
                      </div>
                    ) : (
                      <div className="mt-2 p-3 border rounded bg-white/5 border-white/10">
                        <p className="text-sm text-slate-400">
                          Only original files will be stored (no processing)
                        </p>
                      </div>
                    )}
                  </div>

                  {formData.enable_processing && (
                    <div className="mt-6 border-t border-white/10 pt-6">
                      {!editingId ? (
                        <div className="p-3 border rounded bg-white/5 border-white/10">
                          <p className="text-sm text-slate-400">
                            Save the credential first to create a processor
                            script.
                          </p>
                        </div>
                      ) : (
                        <div className="space-y-4">
                          <div className="p-4 border rounded bg-white/5 border-white/10 space-y-3">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <p className="text-sm font-semibold text-slate-200">
                                  Python Processor Script
                                </p>
                                <p className="text-xs text-slate-500 mt-1">
                                  Edite o script em um modal dedicado para melhor
                                  visualizacao.
                                </p>
                              </div>
                              <button
                                type="button"
                                onClick={() => setShowScriptEditorModal(true)}
                                className="px-4 py-2 bg-brand-600 text-white rounded hover:bg-brand-500 text-sm font-medium"
                              >
                                Open Script Editor
                              </button>
                            </div>
                            <p className="text-xs text-slate-400 font-mono break-all">
                              {processorName
                                ? `Processor: ${processorName}`
                                : "No processor name defined yet"}
                            </p>
                            <p className="text-xs text-slate-500">
                              {processorScript.trim()
                                ? "Script loaded and ready to save."
                                : "No script content yet."}
                            </p>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div className="flex space-x-3 pt-4 border-t border-white/10">
                  <button
                    type="button"
                    onClick={() => {
                      setShowModal(false);
                      setEditingId(null);
                      setFormData({
                        workspace_id: "",
                        label: "",
                        username: "",
                        password: "",
                        metadata: {},
                        carteira: "",
                        enable_processing: false,
                      });
                      resetProcessorState();
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
                    {creating
                      ? editingId
                        ? "Updating..."
                        : "Creating..."
                      : editingId
                        ? "Update"
                        : "Create"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>

      {showModal && formData.enable_processing && editingId && showScriptEditorModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-[60] p-4">
          <div className="glass p-6 rounded-xl border border-white/10 w-full max-w-5xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-start justify-between gap-4 mb-4">
              <div>
                <h4 className="text-xl font-bold text-white">
                  Python Script Editor
                </h4>
                <p className="text-sm text-slate-400">
                  Edit and version your processor script for this credential.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowScriptEditorModal(false)}
                className="px-3 py-2 bg-white/10 text-white rounded hover:bg-white/20 text-sm"
              >
                Close
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-400 mb-2">
                  Processor Name
                </label>
                <input
                  type="text"
                  className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                  placeholder="e.g., Itau Onshore Position Extractor"
                  value={processorName}
                  onChange={(e) => setProcessorName(e.target.value)}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-400 mb-2">
                  Python Script
                  <span className="ml-2 text-xs text-slate-500">
                    (runs on the server after each download)
                  </span>
                </label>

                <div className="border rounded overflow-hidden border-white/10">
                  <Editor
                    value={processorScript}
                    onValueChange={setProcessorScript}
                    highlight={(code) =>
                      highlight(code, languages.python, "python")
                    }
                    padding={12}
                    placeholder={`# Python script to process files
# Available variables:
# - original_dir: path to original files
# - processed_dir: path to save processed files
# - carteira: credential carteira field
# - metadata: credential metadata dict
# - run_id: current run ID
# - credential_label: credential label

from pathlib import Path

for file_path in Path(original_dir).glob('*.xlsx'):
    print(f'Found: {file_path.name}')
`}
                    style={{
                      fontFamily: '"Fira Code", "Fira Mono", monospace',
                      fontSize: 14,
                      backgroundColor: "#1e1e1e",
                      minHeight: "380px",
                      maxHeight: "65vh",
                      overflow: "auto",
                    }}
                    className="font-mono text-sm"
                  />
                </div>

                <p className="text-xs text-slate-500 mt-2">
                  Tip: Use pandas or openpyxl if available on the server.
                </p>
              </div>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={saveProcessor}
                  className="px-4 py-2 bg-brand-600 text-white rounded hover:bg-brand-500 disabled:opacity-50"
                  disabled={!processorScript.trim() || loadingProcessors}
                >
                  Save Processor
                </button>

                {processors.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setShowProcessorHistory(!showProcessorHistory)}
                    className="px-4 py-2 bg-white/10 text-white rounded hover:bg-white/20"
                  >
                    {showProcessorHistory ? "Hide" : "Show"} History (
                    {processors.length})
                  </button>
                )}
              </div>

              {showProcessorHistory && (
                <div className="border rounded p-4 bg-white/5 border-white/10">
                  <h5 className="font-semibold mb-3 text-white">
                    Processor History
                  </h5>
                  <div className="space-y-2">
                    {processors.map((proc) => (
                      <div
                        key={proc.id}
                        className="flex items-center justify-between p-3 bg-dark-surface rounded border border-white/10"
                      >
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-white">
                              {proc.name}
                            </span>
                            <span className="text-xs text-slate-400">
                              v{proc.version}
                            </span>
                            {proc.is_active && (
                              <span className="px-2 py-1 bg-green-500/20 text-green-200 text-xs rounded font-medium">
                                Active
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-slate-500 mt-1">
                            Created: {formatDateTime(proc.created_at)}
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={async () => {
                            const full = await processorsApi.get(proc.id);
                            setProcessorScript(full.script_content || "");
                            setProcessorName(full.name);
                            showToast(`Loaded version ${proc.version}`, "info");
                          }}
                          className="ml-4 px-3 py-1 text-brand-400 hover:bg-brand-500/10 rounded text-sm"
                        >
                          Load
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Delete Modal */}
      <ConfirmModal
        isOpen={deleteModal.isOpen}
        title="Delete Credential?"
        message={`Are you sure you want to delete credential "${deleteModal.label}"? Jobs using this credential will fail. This cannot be undone.`}
        confirmText="Delete Credential"
        isDanger={true}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteModal({ isOpen: false, id: "", label: "" })}
      />
    </Layout>
  );
}
