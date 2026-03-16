import { useState } from 'react';
import axios from 'axios';
import Layout from '../components/Layout';
import { useToast } from '../context/ToastContext';

const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function withTimestamp(message: string): string {
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, '0');
  const mm = String(now.getMinutes()).padStart(2, '0');
  const ss = String(now.getSeconds()).padStart(2, '0');
  return `[${hh}:${mm}:${ss}] ${message}`;
}

function buildVncUrl(base: string, port: number, password: string): string {
  const baseUrl = base.includes('://') ? base : `http://${base}`;
  const url = new URL(baseUrl);
  url.port = String(port);
  url.pathname = '/';
  url.search = '';
  url.searchParams.set('autoconnect', 'true');
  url.searchParams.set('resize', 'scale');
  url.searchParams.set('path', 'websockify');
  url.searchParams.set('password', password);
  return url.toString();
}

export default function ConferenciaAtivo() {
  const [file, setFile] = useState<File | null>(null);
  const [processing, setProcessing] = useState(false);
  const [useSelenium, setUseSelenium] = useState(true);
  const [headless, setHeadless] = useState(true);
  const [logs, setLogs] = useState<string[]>([]);
  const [completed, setCompleted] = useState(false);
  const [processedRows, setProcessedRows] = useState<number | null>(null);
  const [lastTraceId, setLastTraceId] = useState<string | null>(null);
  const { showToast } = useToast();

  const envVncBase = import.meta.env.VITE_VNC_URL_BASE || '';
  const pageHost = window.location.hostname;
  const isLocalPage = pageHost === 'localhost' || pageHost === '127.0.0.1';
  const envLooksLocalhost = /localhost|127\.0\.0\.1/i.test(envVncBase);
  const baseUrl = !isLocalPage && envLooksLocalhost
    ? window.location.origin
    : (envVncBase || window.location.origin);
  const defaultHostPortBase =
    isLocalPage
      ? 17901
      : 7901;
  const parsedHostPortBase = Number(import.meta.env.VITE_VNC_HOST_PORT_BASE || defaultHostPortBase);
  const hostPortBase = (() => {
    const candidate = Number.isFinite(parsedHostPortBase) ? parsedHostPortBase : defaultHostPortBase;
    if (!isLocalPage && candidate >= 17901 && candidate <= 17909) {
      return 7901 + (candidate - 17901);
    }
    return candidate;
  })();
  const vncPassword = import.meta.env.VITE_VNC_PASSWORD || 'secret';
  const gridVncUrls = [
    buildVncUrl(baseUrl, hostPortBase + 1, vncPassword),
    buildVncUrl(baseUrl, hostPortBase + 2, vncPassword),
  ];

  const pushLog = (message: string) => {
    setLogs((prev) => [...prev, withTimestamp(message)]);
  };

  const downloadBlobAsCsv = (blob: Blob, filename: string) => {
    const downloadUrl = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(downloadUrl);
  };

  const recoverResult = async (traceId: string) => {
    const response = await axios.get(`${apiBase}/conferencia-ativo/result/${encodeURIComponent(traceId)}`, {
      responseType: 'blob',
      timeout: 0,
    });

    const disposition = response.headers['content-disposition'] as string | undefined;
    const filenameMatch = disposition?.match(/filename="?([^"]+)"?/i);
    const filename = filenameMatch?.[1] || `conferencia_ativo_resultado_${traceId}.csv`;
    const blob = new Blob([response.data], { type: 'text/csv;charset=utf-8;' });
    const csvText = await blob.text();
    const lines = csvText.split(/\r?\n/).filter((line) => line.trim() !== '');
    const rowCount = Math.max(lines.length - 1, 0);
    setProcessedRows(rowCount);
    setCompleted(true);
    downloadBlobAsCsv(blob, filename);
    pushLog(`Resultado recuperado (trace_id=${traceId})`);
    showToast(`Resultado recuperado (${rowCount} linhas).`, 'success');
  };

  const recoverResultWithRetry = async (traceId: string, attempts = 90, delayMs = 2000) => {
    let lastError: unknown = null;
    for (let i = 1; i <= attempts; i += 1) {
      try {
        await recoverResult(traceId);
        return;
      } catch (error) {
        lastError = error;
        try {
          const progressRes = await axios.get(`${apiBase}/conferencia-ativo/progress/${traceId}`, {
            timeout: 5000,
          });
          const payload = progressRes.data || {};
          if (Array.isArray(payload.logs)) {
            setLogs(payload.logs);
          }
          const status = String(payload.status || '').toLowerCase();
          if (status === 'error') {
            throw error;
          }
        } catch {
          // Ignore transient progress failures and keep retrying.
        }
        pushLog(`Aguardando resultado final... tentativa ${i}/${attempts}`);
        await new Promise((resolve) => window.setTimeout(resolve, delayMs));
      }
    }
    throw lastError || new Error('Falha ao recuperar resultado');
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!file) {
      showToast('Selecione um arquivo CSV', 'error');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);
    setProcessing(true);
    setLogs([]);
    setCompleted(false);
    setProcessedRows(null);
    const traceId = `conf_${Date.now()}_${Math.floor(Math.random() * 1_000_000)}`;
    setLastTraceId(traceId);
    pushLog('Iniciando processamento do CSV...');
    pushLog(`Configuracao: selenium=${useSelenium} headless=${headless}`);
    if (useSelenium && !headless) {
      pushLog('Painel VNC habilitado para acompanhamento visual.');
    }

    let pollTimer: number | null = null;
    pollTimer = window.setInterval(async () => {
      try {
        const progressRes = await axios.get(`${apiBase}/conferencia-ativo/progress/${traceId}`, {
          timeout: 5000,
        });
        const payload = progressRes.data || {};
        if (Array.isArray(payload.logs)) {
          setLogs(payload.logs);
        }
        if (payload.status === 'done' || payload.status === 'error') {
          if (pollTimer) {
            window.clearInterval(pollTimer);
            pollTimer = null;
          }
        }
      } catch {
        // Keep polling; request may fail transiently during long backend work.
      }
    }, 1000);

    try {
      const url =
        `${apiBase}/conferencia-ativo/process-csv` +
        `?use_selenium=${useSelenium}` +
        `&headless=${headless}` +
        `&save_every=10` +
        `&trace_id=${encodeURIComponent(traceId)}`;
      pushLog('Enviando arquivo para o backend...');

      const response = await axios.post(url, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        responseType: 'blob',
        timeout: 0,
      });
      pushLog('Processamento concluido no backend. Preparando download...');

      const disposition = response.headers['content-disposition'] as string | undefined;
      const filenameMatch = disposition?.match(/filename="?([^"]+)"?/i);
      const filename = filenameMatch?.[1] || `conferencia_ativo_resultado.csv`;

      const blob = new Blob([response.data], { type: 'text/csv;charset=utf-8;' });
      const csvText = await blob.text();
      const lines = csvText.split(/\r?\n/).filter((line) => line.trim() !== '');
      const rowCount = Math.max(lines.length - 1, 0);
      setProcessedRows(rowCount);
      setCompleted(true);
      downloadBlobAsCsv(blob, filename);
      pushLog(`Download iniciado: ${filename}`);

      showToast(`Processamento concluido (${rowCount} linhas). Download iniciado.`, 'success');
    } catch (error) {
      console.error('Conferencia ativo processing failed:', error);
      pushLog('Falha na requisicao principal. Tentando recuperar resultado...');
      try {
        await recoverResultWithRetry(traceId);
      } catch {
        pushLog('Nao foi possivel recuperar resultado automaticamente.');
        showToast('Falha ao processar o CSV na conferencia de ativos', 'error');
      }
    } finally {
      if (pollTimer) {
        window.clearInterval(pollTimer);
      }
      setProcessing(false);
      pushLog('Fluxo finalizado.');
    }
  };

  return (
    <Layout>
      <div className="p-8 max-w-4xl mx-auto space-y-8">
        <header>
          <h2 className="text-2xl font-bold text-white">Conferencia Ativo</h2>
          <p className="text-slate-400">
            Envie um CSV com a coluna "Ativo Original" para enriquecer com Codigo Ativo, Taxa e Data Vencimento.
          </p>
        </header>

        <form onSubmit={handleSubmit} className="glass rounded-xl border border-white/10 p-6 space-y-6">
          <div className="space-y-2">
            <label className="block text-sm font-medium text-slate-300">Arquivo CSV</label>
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="block w-full text-sm text-slate-300 file:mr-4 file:rounded-md file:border-0 file:bg-brand-500/20 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-brand-200 hover:file:bg-brand-500/30"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={useSelenium}
                onChange={(e) => setUseSelenium(e.target.checked)}
                className="rounded border-slate-600 bg-slate-900 text-brand-500 focus:ring-brand-500"
              />
              Consultar ANBIMA com Selenium
            </label>

            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={headless}
                onChange={(e) => setHeadless(e.target.checked)}
                className="rounded border-slate-600 bg-slate-900 text-brand-500 focus:ring-brand-500"
                disabled={!useSelenium}
              />
              Rodar navegador em modo headless
            </label>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={processing}
              className="px-4 py-2 rounded-lg bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {processing ? 'Processando...' : 'Processar CSV'}
            </button>
            {completed && (
              <span className="inline-flex items-center px-3 py-2 rounded-lg text-sm font-medium border border-green-500/40 bg-green-500/10 text-green-300">
                Concluido{processedRows !== null ? ` (${processedRows} linhas)` : ''}
              </span>
            )}
          </div>
        </form>

        {(processing || logs.length > 0) && (
          <section className="glass rounded-xl border border-white/10 p-6 space-y-4">
            <h3 className="text-lg font-semibold text-white">Acompanhamento</h3>

            <div className="bg-slate-900/80 border border-white/10 rounded-lg p-3 h-40 overflow-y-auto font-mono text-xs text-slate-300 space-y-1">
              {logs.length === 0 ? (
                <div className="text-slate-500">Aguardando eventos...</div>
              ) : (
                logs.map((line, idx) => <div key={idx}>{line}</div>)
              )}
            </div>

            {useSelenium && !headless && (
              <div className="space-y-3">
                <p className="text-sm text-slate-300">
                  Visualizacao VNC automatica (Selenium Grid). Abra o node com atividade.
                  {!processing ? ' Execucao finalizada ou aguardando novo processamento.' : ''}
                </p>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {gridVncUrls.map((url, idx) => (
                    <div key={idx} className="space-y-2">
                      <div className="flex items-center justify-between text-xs text-slate-400">
                        <span>Node {idx + 1}</span>
                        <a
                          href={url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-brand-400 hover:underline"
                        >
                          Open Full VNC
                        </a>
                      </div>
                      <iframe
                        src={url}
                        title={`Conferencia Ativo VNC Node ${idx + 1}`}
                        className="w-full h-[360px] border border-slate-700 rounded-lg bg-black"
                        allowFullScreen
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}
            {!processing && lastTraceId && (
              <div className="pt-2">
                <button
                  type="button"
                  onClick={() => recoverResult(lastTraceId)}
                  className="px-3 py-2 rounded-lg border border-white/20 text-sm text-slate-200 hover:bg-white/10"
                >
                  Recuperar Resultado (trace_id)
                </button>
              </div>
            )}
          </section>
        )}
      </div>
    </Layout>
  );
}
