import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useSearchParams, useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';
import ConfirmModal from '../components/ui/ConfirmModal';
import { useToast } from '../context/ToastContext';

interface Job {
    id: string;
    workspace_id: string;
    name: string;
    connector: string;
    credential_id?: string;
    params: Record<string, any>;
    schedule?: string;
    status: string;
    
    // Export options
    export_holdings?: boolean;
    export_history?: boolean;
    
    // Date configuration
    date_mode?: string;
    holdings_lag_days?: number;
    history_lag_days?: number;
    holdings_date?: string;
    history_date?: string;
    enable_processing?: boolean;
    processing_config_json?: JobProcessingConfig;
    processing_script?: string;
}

interface JobProcessingConfig {
    mode: 'visual' | 'advanced';
    visual_config?: Partial<VisualProcessorConfig>;
    advanced_script?: string;
}

interface Workspace {
    id: string;
    name: string;
    description?: string;
}

interface Credential {
    id: string;
    workspace_id: string;
    label: string;
    username: string;
}

interface DownloadFileMetadata {
    file_type: string;
    filename: string;
}

interface DownloadRow {
    run_id: string;
    job_id: string;
    files: DownloadFileMetadata[];
}

// Schedule presets for easy selection
const SCHEDULE_PRESETS = [
    { label: 'No schedule (manual only)', value: '' },
    { label: 'Every 3 minutes', value: '*/3 * * * *' },
    { label: 'Every 5 minutes', value: '*/5 * * * *' },
    { label: 'Every 15 minutes', value: '*/15 * * * *' },
    { label: 'Every 30 minutes', value: '*/30 * * * *' },
    { label: 'Every hour', value: '0 * * * *' },
    { label: 'Every 6 hours', value: '0 */6 * * *' },
    { label: 'Daily at midnight', value: '0 0 * * *' },
    { label: 'Daily at 9 AM', value: '0 9 * * *' },
    { label: 'Weekdays at 9 AM', value: '0 9 * * 1-5' },
    { label: 'Weekly (Monday 9 AM)', value: '0 9 * * 1' },
    { label: 'Custom cron expression', value: 'custom' }
];

const DEFAULT_PROCESSING_SCRIPT = `# process_file(df_input, arquivo, aba, carteira, original_dir, processado_dir)
# Return a DataFrame with output columns.
def process_file(df_input, arquivo, aba, carteira, original_dir, processado_dir):
    out = df_input.copy()
    if "Carteira" not in out.columns:
        out["Carteira"] = carteira
    return out
`;

interface VisualProcessorConfig {
    ativo_mode: 'direct' | 'compose';
    ativo_direct_cols: string;
    ativo_comp_base_cols: string;
    ativo_comp_part2_cols: string;
    ativo_comp_part3_cols: string;
    ativo_comp_part4_primary_cols: string;
    ativo_comp_part4_fallback_cols: string;
    ativo_separator: string;
    quant_cols: string;
    pu_cols: string;
    saldo_bruto_cols: string;
    caixa_cols: string;
    moeda_fixa: string;
    filter_zero_enabled: boolean;
    filter_zero_cols: string;
    filter_empty_enabled: boolean;
    filter_empty_cols: string;
    only_enabled: boolean;
    only_cols: string;
    only_mode: 'sim' | 'nao';
    only_true_values: string;
}

const DEFAULT_VISUAL_CONFIG: VisualProcessorConfig = {
    ativo_mode: 'direct',
    ativo_direct_cols: 'Ativo, Nome Ativo',
    ativo_comp_base_cols: 'Ativo Base, Ativo',
    ativo_comp_part2_cols: 'Operacao, Operação',
    ativo_comp_part3_cols: 'Emissor',
    ativo_comp_part4_primary_cols: 'Vencimento',
    ativo_comp_part4_fallback_cols: 'Codigo, Código',
    ativo_separator: ' - ',
    quant_cols: 'q, Quant, Quantidade',
    pu_cols: 'pu, PU, Preco Unitario',
    saldo_bruto_cols: 'sb, SaldoBruto, Saldo Bruto',
    caixa_cols: 'Caixa, Eh Caixa, e_caixa',
    moeda_fixa: 'BRL',
    filter_zero_enabled: false,
    filter_zero_cols: 'sb, SaldoBruto, Saldo Bruto',
    filter_empty_enabled: false,
    filter_empty_cols: 'Ativo, Nome Ativo',
    only_enabled: false,
    only_cols: 'Caixa, Eh Caixa, e_caixa',
    only_mode: 'sim',
    only_true_values: '1, true, sim, s, yes, y',
};

function buildVisualProcessorScript(cfg: VisualProcessorConfig): string {
    const q = JSON.stringify;
    const aliases = (value: string) =>
        value
            .split(',')
            .map((x) => x.trim())
            .filter(Boolean);
    return `# VISUAL_BUILDER_JOB_V1
df = df_input.copy() if df_input is not None else pd.DataFrame()
df.columns = [str(c).strip() for c in df.columns]

def pick_col(candidates):
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for name in candidates:
        key = str(name).strip().lower()
        if key in lower_map:
            return lower_map[key]
    return None

def txt(candidates, default=""):
    col = pick_col(candidates)
    if col:
        return df[col].astype(str).fillna("").str.strip()
    return pd.Series([default] * len(df), index=df.index)

def num(candidates, default=0.0):
    col = pick_col(candidates)
    if col:
        raw = df[col]
        parsed = pd.to_numeric(raw, errors="coerce")
        if parsed.notna().any():
            return parsed.fillna(default)
        return raw.apply(ptbr_to_float).fillna(default)
    return pd.Series([default] * len(df), index=df.index)

ativo_direct = txt(${q(aliases(cfg.ativo_direct_cols))})
ativo_base = txt(${q(aliases(cfg.ativo_comp_base_cols))})
ativo_p2 = txt(${q(aliases(cfg.ativo_comp_part2_cols))})
ativo_p3 = txt(${q(aliases(cfg.ativo_comp_part3_cols))})
ativo_p4_primary = txt(${q(aliases(cfg.ativo_comp_part4_primary_cols))})
ativo_p4_fallback = txt(${q(aliases(cfg.ativo_comp_part4_fallback_cols))})
qtd = num(${q(aliases(cfg.quant_cols))}, 0.0)
pu = num(${q(aliases(cfg.pu_cols))}, 0.0)
sb = num(${q(aliases(cfg.saldo_bruto_cols))}, 0.0)
caixa_raw = txt(${q(aliases(cfg.caixa_cols))}).str.lower()
caixa = caixa_raw.isin(["1", "true", "sim", "s", "yes", "y"])
caixa = caixa | caixa_raw.str.contains("caixa|conta corrente|saldo em conta", na=False)
ativo_hint = ativo_direct.str.lower()
caixa = caixa | ativo_hint.str.contains("conta corrente|saldo em conta", na=False)
data_ref = report_date or data_do_arquivo(arquivo)

def _clean_text(v):
    s = str(v).strip()
    if s.lower() in ["", "-", "nan", "none"]:
        return ""
    return s

def _join_non_empty(parts, sep):
    vals = [_clean_text(x) for x in parts]
    vals = [v for v in vals if v]
    return sep.join(vals)

if ${q(cfg.ativo_mode)} == "compose":
    p4 = ativo_p4_primary.where(ativo_p4_primary.astype(str).str.strip().ne(""), ativo_p4_fallback)
    ativo = pd.DataFrame({
        "a": ativo_base,
        "b": ativo_p2,
        "c": ativo_p3,
        "d": p4,
    }).apply(lambda r: _join_non_empty([r["a"], r["b"], r["c"], r["d"]], ${q(cfg.ativo_separator || " - ")}), axis=1)
else:
    ativo = ativo_direct

out = pd.DataFrame({
    "Data": data_ref,
    "Carteira": carteira,
    "Ativo": ativo,
    "Quant": qtd.where(~caixa, sb),
    "PU": pu.where(~caixa, 1.0),
    "SaldoBruto": sb,
    "Caixa": caixa.map({True: "Sim", False: "Não"}),
    "Moeda": ${q(cfg.moeda_fixa || "BRL")},
})

mask = pd.Series([True] * len(out), index=out.index)
${cfg.filter_zero_enabled ? `fz = num(${q(aliases(cfg.filter_zero_cols))}, 0.0)\nmask &= fz.ne(0)` : "# sem filtro de zero"}
${cfg.filter_empty_enabled ? `fe = txt(${q(aliases(cfg.filter_empty_cols))})\nmask &= fe.astype(str).str.strip().ne("")` : "# sem filtro de vazio"}
${cfg.only_enabled ? `only_raw = txt(${q(aliases(cfg.only_cols))}).str.lower()\nonly_true = [x.strip().lower() for x in ${q(aliases(cfg.only_true_values))}]\nonly_flag = only_raw.isin(only_true)\nmask &= only_flag if ${q(cfg.only_mode)} == "sim" else ~only_flag` : "# sem filtro somente"}
out = out.loc[mask].reset_index(drop=True)

return out
`;
}

function normalizeVisualConfig(raw?: Partial<VisualProcessorConfig>): VisualProcessorConfig {
    return {
        ...DEFAULT_VISUAL_CONFIG,
        ...(raw || {}),
    };
}

function extractVisualConfigFromScript(script?: string): VisualProcessorConfig | null {
    if (!script) return null;
    const marker = '# VISUAL_CONFIG_JSON:';
    const line = script
        .split('\n')
        .map((x) => x.trim())
        .find((x) => x.startsWith(marker));
    if (!line) return null;
    const payload = line.slice(marker.length).trim();
    try {
        const parsed = JSON.parse(payload);
        if (parsed && typeof parsed === 'object') {
            return normalizeVisualConfig(parsed as Partial<VisualProcessorConfig>);
        }
    } catch (e) {
        console.warn('Failed to parse visual config marker', e);
    }
    return null;
}

function extractLegacyVisualConfigFromScript(script?: string): VisualProcessorConfig | null {
    if (!script || !script.includes('VISUAL_BUILDER_')) return null;

    const readArray = (prefixRegex: RegExp): string => {
        const match = script.match(prefixRegex);
        if (!match || !match[1]) return '';
        try {
            const arr = JSON.parse(match[1]);
            if (Array.isArray(arr)) return arr.join(', ');
        } catch (e) {
            console.warn('Failed to parse visual aliases', e);
        }
        return '';
    };
    const readQuoted = (regex: RegExp, fallback = ''): string => {
        const match = script.match(regex);
        return match?.[1] ?? fallback;
    };

    const cfg: VisualProcessorConfig = normalizeVisualConfig({
        ativo_direct_cols: readArray(/ativo_direct\s*=\s*txt\((\[[^\n]*\])\)/),
        ativo_comp_base_cols: readArray(/ativo_base\s*=\s*txt\((\[[^\n]*\])\)/),
        ativo_comp_part2_cols: readArray(/ativo_p2\s*=\s*txt\((\[[^\n]*\])\)/),
        ativo_comp_part3_cols: readArray(/ativo_p3\s*=\s*txt\((\[[^\n]*\])\)/),
        ativo_comp_part4_primary_cols: readArray(/ativo_p4_primary\s*=\s*txt\((\[[^\n]*\])\)/),
        ativo_comp_part4_fallback_cols: readArray(/ativo_p4_fallback\s*=\s*txt\((\[[^\n]*\])\)/),
        quant_cols: readArray(/qtd\s*=\s*num\((\[[^\n]*\]),\s*0\.0\)/),
        pu_cols: readArray(/pu\s*=\s*num\((\[[^\n]*\]),\s*0\.0\)/),
        saldo_bruto_cols: readArray(/sb\s*=\s*num\((\[[^\n]*\]),\s*0\.0\)/),
        caixa_cols: readArray(/caixa_raw\s*=\s*txt\((\[[^\n]*\])\)\.str\.lower\(\)/),
        moeda_fixa: readQuoted(/"Moeda":\s*"([^"]*)"/, 'BRL'),
        ativo_separator: readQuoted(/_join_non_empty\(\[r\["a"\],\s*r\["b"\],\s*r\["c"\],\s*r\["d"\]\],\s*"([^"]*)"\)/, ' - '),
        ativo_mode: /if\s+"compose"\s*==\s*"compose":/.test(script) ? 'compose' : 'direct',
        filter_zero_enabled: /fz\s*=\s*num\(/.test(script),
        filter_zero_cols: readArray(/fz\s*=\s*num\((\[[^\n]*\]),\s*0\.0\)/),
        filter_empty_enabled: /fe\s*=\s*txt\(/.test(script),
        filter_empty_cols: readArray(/fe\s*=\s*txt\((\[[^\n]*\])\)/),
        only_enabled: /only_raw\s*=\s*txt\(/.test(script),
        only_cols: readArray(/only_raw\s*=\s*txt\((\[[^\n]*\])\)\.str\.lower\(\)/),
        only_true_values: readArray(/only_true\s*=\s*\[x\.strip\(\)\.lower\(\)\s+for\s+x\s+in\s+(\[[^\n]*\])\]/),
        only_mode: /mask\s*&=\s*only_flag\s*if\s*"nao"\s*==\s*"sim"\s*else\s*~only_flag/.test(script) ? 'nao' : 'sim',
    });

    return cfg;
}

function scriptFromJobConfig(job: Job): string {
    const cfg = job.processing_config_json;
    if (cfg?.mode === 'visual') {
        return buildVisualProcessorScript(normalizeVisualConfig(cfg.visual_config));
    }
    if (cfg?.mode === 'advanced' && cfg.advanced_script) {
        return cfg.advanced_script;
    }
    return job.processing_script || DEFAULT_PROCESSING_SCRIPT;
}

export default function Jobs() {
    const [jobs, setJobs] = useState<Job[]>([]);
    const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
    const [credentials, setCredentials] = useState<Credential[]>([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [creating, setCreating] = useState(false);
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const [scheduleType, setScheduleType] = useState('');
    const [customCron, setCustomCron] = useState('');
    const [jsonMode, setJsonMode] = useState(false);
    const [jsonParams, setJsonParams] = useState('{}');
    
    // UI State for Delete Modal
    const [deleteModal, setDeleteModal] = useState<{ isOpen: boolean; id: string; name: string }>({ 
        isOpen: false, id: '', name: '' 
    });
    const [deleteAllModal, setDeleteAllModal] = useState(false);
    const [viewParamsModal, setViewParamsModal] = useState<{ isOpen: boolean; job: Job | null }>({ 
        isOpen: false, job: null 
    });
    const [scriptModal, setScriptModal] = useState<{
        isOpen: boolean;
        job: Job | null;
        tab: 'visual' | 'advanced';
        script: string;
    }>({
        isOpen: false,
        job: null,
        tab: 'visual',
        script: DEFAULT_PROCESSING_SCRIPT,
    });
    const [visualConfig, setVisualConfig] = useState<VisualProcessorConfig>(DEFAULT_VISUAL_CONFIG);
    const [savingScript, setSavingScript] = useState(false);
    const [mappingPreview, setMappingPreview] = useState<{
        loading: boolean;
        runId?: string;
        filename?: string;
        selectedSheet?: string;
        columns: string[];
        matches: Array<{ output: string; aliases: string[]; matched?: string }>;
    }>({
        loading: false,
        columns: [],
        matches: [],
    });

    const { showToast } = useToast();

    // Get workspace specific jobs if workspace_id is present
    const workspaceId = searchParams.get('workspace');
    
    const [formData, setFormData] = useState<{
        workspace_id: string;
        name: string;
        connector: string;
        credential_id?: string;
        params: { username?: string; password?: string; url?: string; selector?: string; [key: string]: any };
        schedule: string;
        export_holdings: boolean;
        export_history: boolean;
        date_mode: string;
        holdings_lag_days: number;
        history_lag_days: number;
        holdings_date: string;
        history_date: string;
    }>({
        workspace_id: workspaceId || '',
        name: '',
        connector: 'jpmorgan_login',
        credential_id: '',
        params: { username: '', password: '' },
        schedule: '',
        export_holdings: true,
        export_history: false,
        date_mode: 'lag',
        holdings_lag_days: 1,
        history_lag_days: 2,
        holdings_date: '',
        history_date: ''
    });

    const fetchJobs = async () => {
        try {
            const res = await axios.get(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/jobs`);
            setJobs(res.data);
        } catch (error) {
            console.error('Failed to fetch jobs:', error);
        } finally {
            setLoading(false);
        }
    };

    const fetchWorkspaces = async () => {
        try {
            const res = await axios.get(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/workspaces`);
            setWorkspaces(res.data);
        } catch (error) {
            console.error('Failed to fetch workspaces:', error);
        }
    };

    const fetchCredentials = async () => {
        try {
            const res = await axios.get(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/credentials`);
            setCredentials(res.data);
        } catch (error) {
            console.error('Failed to fetch credentials:', error);
        }
    };

    useEffect(() => {
        fetchJobs();
        fetchWorkspaces();
        fetchCredentials();
    }, []);

    // Update params when connector changes
    useEffect(() => {
        if (formData.connector === 'jpmorgan_login') {
            setFormData(prev => ({ ...prev, params: { username: '', password: '' } }));
        } else if (formData.connector === 'itau_onshore_login') {
            setFormData(prev => ({
                ...prev,
                params: {
                    username: '',
                    password: '',
                    agencia: '',
                    conta_corrente: '',
                    use_business_day: false,
                    business_day: ''
                }
            }));
        } else if (formData.connector === 'generic_scraper') {
            setFormData(prev => ({ ...prev, params: { url: '', selector: '' } }));
        }
    }, [formData.connector]);

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        setCreating(true);

        try {
            // Parse JSON params if in JSON mode
            let finalParams = formData.params;
            if (jsonMode) {
                try {
                    finalParams = JSON.parse(jsonParams);
                } catch (err) {
                    alert('Invalid JSON in params field');
                    setCreating(false);
                    return;
                }
            }

            if (formData.connector === 'itau_onshore_login' && !formData.credential_id) {
                const manualAgency = finalParams.agencia;
                const manualAccount = finalParams.conta_corrente || finalParams.conta;
                const manualUsername = finalParams.username || finalParams.user;
                const manualPassword = finalParams.password || finalParams.pass;

                if (!manualAgency || !manualAccount || !manualUsername || !manualPassword) {
                    showToast(
                        'Para Itaú manual, preencha usuário, senha, agência e conta.',
                        'error',
                    );
                    setCreating(false);
                    return;
                }
            }

            // Determine final schedule value and normalize (remove extra spaces)
        let finalSchedule = scheduleType === 'custom' ? customCron : scheduleType;
        if (finalSchedule) {
            // Normalize: remove extra spaces between cron parts
            finalSchedule = finalSchedule.split(/\s+/).filter(p => p).join(' ');
        }
            
            await axios.post(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/jobs`, {
                ...formData,
                credential_id: formData.credential_id || undefined,
                params: finalParams,
                schedule: finalSchedule || undefined
            });
            
            setShowModal(false);
            setFormData({
                workspace_id: '',
                name: '',
                connector: 'jpmorgan_login',
                params: { username: '', password: '' },
                schedule: '',
                export_holdings: true,
                export_history: false,
                date_mode: 'lag',
                holdings_lag_days: 1,
                history_lag_days: 2,
                holdings_date: '',
                history_date: ''
            });
            setScheduleType('');
            setCustomCron('');
            setJsonMode(false);
            setJsonParams('{}');
            fetchJobs();
        } catch (error) {
            alert('Error creating job');
            console.error(error);
        } finally {
            setCreating(false);
        }
    };

    const triggerJob = async (jobId: string) => {
        try {
            const res = await axios.post(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/jobs/${jobId}/run`);
            showToast(`Job triggered! Run ID: ${res.data.id}`, 'success');
            navigate(`/live/${res.data.id}`);
        } catch (error) {
            showToast('Error triggering job', 'error');
            console.error(error);
        }
    };

    const toggleJobProcessing = async (job: Job, checked: boolean) => {
        try {
            await axios.patch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/jobs/${job.id}`, {
                enable_processing: checked,
            });
            setJobs(prev =>
                prev.map(j =>
                    j.id === job.id
                        ? {
                            ...j,
                            enable_processing: checked,
                            processing_script: checked ? j.processing_script : undefined,
                            processing_config_json: checked ? j.processing_config_json : undefined,
                        }
                        : j
                )
            );
            showToast(`Processing ${checked ? 'enabled' : 'disabled'} for "${job.name}"`, 'success');
        } catch (error) {
            showToast('Error updating processing flag', 'error');
            console.error(error);
        }
    };

    const openScriptEditor = (job: Job) => {
        const extractedFromScript =
            extractVisualConfigFromScript(job.processing_script || '')
            || extractLegacyVisualConfigFromScript(job.processing_script || '');
        const visualFromConfig =
            job.processing_config_json?.mode === 'visual'
                ? normalizeVisualConfig(job.processing_config_json.visual_config)
                : extractedFromScript;
        setVisualConfig(visualFromConfig || DEFAULT_VISUAL_CONFIG);
        setMappingPreview({
            loading: false,
            columns: [],
            matches: [],
        });
        const initialScript = scriptFromJobConfig(job);
        const inferredMode = job.processing_config_json?.mode
            || (extractedFromScript ? 'visual' : (job.processing_script ? 'advanced' : 'visual'));
        const initialTab = inferredMode === 'advanced' ? 'advanced' : 'visual';
        setScriptModal({
            isOpen: true,
            job,
            tab: initialTab,
            script: initialScript,
        });
    };

    const saveJobScript = async () => {
        if (!scriptModal.job) return;
        const generatedScript = buildVisualProcessorScript(visualConfig);
        const advancedScript = (scriptModal.script || '').trim();
        const isAdvanced = scriptModal.tab === 'advanced';
        const scriptToPersist = isAdvanced ? advancedScript : generatedScript;
        if (!scriptToPersist.trim()) {
            showToast('Script vazio. Preencha antes de salvar.', 'error');
            return;
        }

        setSavingScript(true);
        try {
            const payloadConfig: JobProcessingConfig = isAdvanced
                ? {
                    mode: 'advanced',
                    advanced_script: scriptToPersist,
                }
                : {
                    mode: 'visual',
                    visual_config: visualConfig,
                };
            setScriptModal(prev => ({ ...prev, script: scriptToPersist }));
            const res = await axios.patch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/jobs/${scriptModal.job.id}`, {
                enable_processing: true,
                processing_config_json: payloadConfig,
            });
            const updated = res.data as Job;
            setJobs(prev => prev.map(j => (j.id === updated.id ? updated : j)));
            showToast('Script salvo no job', 'success');
            setScriptModal(prev => ({ ...prev, isOpen: false, job: null }));
        } catch (error) {
            showToast('Error saving script', 'error');
            console.error(error);
        } finally {
            setSavingScript(false);
        }
    };

    const splitAliases = (text: string): string[] =>
        text
            .split(',')
            .map((x) => x.trim())
            .filter(Boolean);

    const findMatchedColumn = (columns: string[], aliases: string[]): string | undefined => {
        const lowerMap = new Map(columns.map((c) => [c.toLowerCase(), c]));
        for (const alias of aliases) {
            const hit = lowerMap.get(alias.toLowerCase());
            if (hit) return hit;
        }
        return undefined;
    };

    const testMappingWithLatestDownload = async () => {
        if (!scriptModal.job) return;
        setMappingPreview({
            loading: true,
            columns: [],
            matches: [],
        });

        try {
            const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8000';
            const downloadsRes = await axios.get<DownloadRow[]>(`${apiBase}/downloads`, {
                params: { limit: 200 },
            });
            const latest = downloadsRes.data.find(
                (d) => d.job_id === scriptModal.job?.id && (d.files || []).some((f) => f.file_type === 'original'),
            );
            if (!latest) {
                showToast('Nao encontrei download bruto para este job.', 'error');
                setMappingPreview({ loading: false, columns: [], matches: [] });
                return;
            }

            const original = latest.files.find((f) => f.file_type === 'original');
            if (!original) {
                showToast('Run encontrado sem arquivo bruto.', 'error');
                setMappingPreview({ loading: false, columns: [], matches: [] });
                return;
            }

            let selectedSheet: string | undefined;
            if (/\.(xlsx|xlsm|xls)$/i.test(original.filename)) {
                const sheetsRes = await axios.get<string[]>(`${apiBase}/downloads/${latest.run_id}/processing/excel-options`, {
                    params: { filename: original.filename },
                });
                if (sheetsRes.data.length > 0) {
                    selectedSheet = sheetsRes.data[0];
                }
            }

            const colsRes = await axios.get<{ columns: string[] }>(
                `${apiBase}/downloads/${latest.run_id}/processing/columns`,
                {
                    params: {
                        filename: original.filename,
                        selected_sheet: selectedSheet,
                    },
                },
            );
            const cols = colsRes.data.columns || [];
            const ativoAliases =
                visualConfig.ativo_mode === 'compose'
                    ? [
                          ...splitAliases(visualConfig.ativo_comp_base_cols),
                          ...splitAliases(visualConfig.ativo_comp_part2_cols),
                          ...splitAliases(visualConfig.ativo_comp_part3_cols),
                          ...splitAliases(visualConfig.ativo_comp_part4_primary_cols),
                          ...splitAliases(visualConfig.ativo_comp_part4_fallback_cols),
                      ]
                    : splitAliases(visualConfig.ativo_direct_cols);
            const matches = [
                { output: 'Ativo', aliases: ativoAliases },
                { output: 'Quant', aliases: splitAliases(visualConfig.quant_cols) },
                { output: 'PU', aliases: splitAliases(visualConfig.pu_cols) },
                { output: 'SaldoBruto', aliases: splitAliases(visualConfig.saldo_bruto_cols) },
                { output: 'Caixa', aliases: splitAliases(visualConfig.caixa_cols) },
            ].map((row) => ({
                ...row,
                matched: findMatchedColumn(cols, row.aliases),
            }));

            setMappingPreview({
                loading: false,
                runId: latest.run_id,
                filename: original.filename,
                selectedSheet,
                columns: cols,
                matches,
            });
            showToast('Preview de mapeamento gerado.', 'success');
        } catch (error) {
            console.error(error);
            showToast('Falha ao testar mapeamento no ultimo download.', 'error');
            setMappingPreview({ loading: false, columns: [], matches: [] });
        }
    };

    const deleteJob = (jobId: string, jobName: string) => {
        setDeleteModal({ isOpen: true, id: jobId, name: jobName });
    };

    const handleConfirmDelete = async () => {
        try {
            await axios.delete(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/jobs/${deleteModal.id}`);
            showToast('Job deleted successfully', 'success');
            fetchJobs();
        } catch (error) {
            showToast('Error deleting job', 'error');
            console.error(error);
        } finally {
            setDeleteModal(prev => ({ ...prev, isOpen: false }));
        }
    };

    const getStatusBadge = (status: string) => {
        const badges = {
            active: 'bg-green-500/20 text-green-400 border-green-500/30',
            paused: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
            inactive: 'bg-slate-500/20 text-slate-400 border-slate-500/30'
        };
        return badges[status as keyof typeof badges] || badges.inactive;
    };

    const getScheduleLabel = (cronExpr?: string) => {
        if (!cronExpr) return null;
        const preset = SCHEDULE_PRESETS.find(p => p.value === cronExpr);
        return preset ? preset.label : cronExpr;
    };

    const getDateConfigLabel = (job: Job, type: 'relatorio' | 'extrato') => {
        if (job.date_mode === 'specific') {
            const date = type === 'relatorio' ? job.holdings_date : job.history_date;
            if (!date) return '-';
            
            // Convert YYYY-MM-DD to DD/MM/YYYY for display
            try {
                const [year, month, day] = date.split('-');
                return `${day}/${month}/${year}`;
            } catch {
                return date; // Fallback to original if parsing fails
            }
        } else {
            const lag = type === 'relatorio' ? (job.holdings_lag_days || 1) : (job.history_lag_days || 2);
            return `D-${lag}`;
        }
    };

    const deleteAllJobs = () => {
        setDeleteAllModal(true);
    };

    const handleConfirmDeleteAll = async () => {
        try {
            const res = await axios.delete(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/jobs`);
            showToast(res.data.message || 'All jobs deleted', 'success');
            fetchJobs();
        } catch (error) {
            showToast('Error deleting jobs', 'error');
            console.error(error);
        } finally {
            setDeleteAllModal(false);
        }
    };

    return (
        <Layout>
            <div className="p-8 max-w-7xl mx-auto space-y-8">
                <header className="flex justify-between items-center">
                    <div>
                        <h2 className="text-2xl font-bold text-white">Scrape Jobs</h2>
                        <p className="text-slate-400">Manage your automated scraping jobs</p>
                    </div>
                    <div className="flex gap-3">
                        <button 
                            onClick={deleteAllJobs}
                            className="bg-red-600/10 hover:bg-red-600/30 text-red-500 border border-red-500/30 px-6 py-2.5 rounded-lg font-medium transition-all flex items-center space-x-2"
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                            <span>Delete All</span>
                        </button>
                        <button 
                            onClick={() => setShowModal(true)}
                            className="bg-brand-600 hover:bg-brand-500 text-white px-6 py-2.5 rounded-lg font-medium shadow-lg shadow-brand-500/20 transition-all flex items-center space-x-2"
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path></svg>
                            <span>New Job</span>
                        </button>
                    </div>
                </header>

                {/* Jobs Table */}
                <div className="glass rounded-xl overflow-hidden border border-white/5">
                    <table className="w-full text-left">
                        <thead className="bg-white/5 text-slate-400 uppercase text-xs">
                            <tr>
                                <th className="px-6 py-4">Job Name</th>
                                <th className="px-6 py-4">View</th>
                                <th className="px-6 py-4">Connector</th>
                                <th className="px-6 py-4">Schedule</th>
                                <th className="px-6 py-4">Posição</th>
                                <th className="px-6 py-4">Histórico</th>
                                <th className="px-6 py-4">Processing</th>
                                <th className="px-6 py-4">Status</th>
                                <th className="px-6 py-4">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5 text-sm">
                            {loading ? (
                                <tr>
                                    <td colSpan={9} className="px-6 py-8 text-center text-slate-400">
                                        Loading jobs...
                                    </td>
                                </tr>
                            ) : jobs.length === 0 ? (
                                <tr>
                                    <td colSpan={9} className="px-6 py-8 text-center text-slate-500">
                                        No jobs yet. Create your first job!
                                    </td>
                                </tr>
                            ) : (
                                jobs.map((job) => (
                                    <tr key={job.id} className="hover:bg-white/5 transition-colors">
                                        <td className="px-6 py-4">
                                            <div>
                                                <p className="font-semibold text-white">{job.name}</p>
                                                <p className="text-xs text-slate-500 font-mono">#{job.id.slice(0, 8)}</p>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4">
                                            <button
                                                onClick={() => setViewParamsModal({ isOpen: true, job })}
                                                className="text-brand-400 hover:text-brand-300 transition-colors flex items-center space-x-1"
                                            >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                                                </svg>
                                            </button>
                                        </td>
                                        <td className="px-6 py-4 text-slate-300">{job.connector}</td>
                                        <td className="px-6 py-4">
                                            {job.schedule ? (
                                                <div>
                                                    <p className="text-sm text-slate-300">{getScheduleLabel(job.schedule)}</p>
                                                    <code className="text-xs text-slate-500 font-mono">{job.schedule}</code>
                                                </div>
                                            ) : (
                                                <span className="text-slate-500 text-xs">Manual only</span>
                                            )}
                                        </td>
                                        <td className="px-6 py-4">
                                            {job.export_holdings ? (
                                                <span className="text-sm text-slate-300">{getDateConfigLabel(job, 'relatorio')}</span>
                                            ) : (
                                                <span className="text-slate-500 text-xs">-</span>
                                            )}
                                        </td>
                                        <td className="px-6 py-4">
                                            {job.export_history ? (
                                                <span className="text-sm text-slate-300">{getDateConfigLabel(job, 'extrato')}</span>
                                            ) : (
                                                <span className="text-slate-500 text-xs">-</span>
                                            )}
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="flex items-center gap-3">
                                                <label className="inline-flex items-center gap-2 text-xs text-slate-300">
                                                    <input
                                                        type="checkbox"
                                                        checked={!!job.enable_processing}
                                                        onChange={(e) => toggleJobProcessing(job, e.target.checked)}
                                                        className="rounded border-white/20 bg-dark-surface"
                                                    />
                                                    <span>{job.enable_processing ? 'True' : 'False'}</span>
                                                </label>
                                                {job.enable_processing && (
                                                    <button
                                                        onClick={() => openScriptEditor(job)}
                                                        className="text-brand-400 hover:text-brand-300 text-xs font-medium"
                                                    >
                                                        Script
                                                    </button>
                                                )}
                                            </div>
                                        </td>
                                        <td className="px-6 py-4">
                                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${getStatusBadge(job.status)}`}>
                                                {job.status.charAt(0).toUpperCase() + job.status.slice(1)}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="flex items-center space-x-3">
                                                <button 
                                                    onClick={() => triggerJob(job.id)}
                                                    className="text-brand-400 hover:text-brand-300 font-medium flex items-center"
                                                >
                                                    <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"></path>
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                                                    </svg>
                                                    Run
                                                </button>
                                                <button 
                                                    onClick={() => deleteJob(job.id, job.name)}
                                                    className="text-red-400 hover:text-red-300 font-medium flex items-center"
                                                >
                                                    <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
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

                {/* Create Modal */}
                {showModal && (
                    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
                        <div className="glass p-8 rounded-xl border border-white/10 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
                            <h3 className="text-xl font-bold text-white mb-6">Create Job</h3>
                            <form onSubmit={handleCreate} className="space-y-5">
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-sm font-medium text-slate-400 mb-2">Workspace</label>
                                        <select
                                            value={formData.workspace_id}
                                            onChange={(e) => setFormData({...formData, workspace_id: e.target.value})}
                                            className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                                            required
                                        >
                                            <option value="" disabled>Select a workspace</option>
                                            {workspaces.map(ws => (
                                                <option key={ws.id} value={ws.id}>
                                                    {ws.name} ({ws.id.slice(0, 8)}...)
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-slate-400 mb-2">Job Name</label>
                                        <input
                                            type="text"
                                            value={formData.name}
                                            onChange={(e) => setFormData({...formData, name: e.target.value})}
                                            className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                                            placeholder="My Scraping Job"
                                            required
                                        />
                                    </div>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-slate-400 mb-2">Connector</label>
                                    <select
                                        value={formData.connector}
                                        onChange={(e) => setFormData({...formData, connector: e.target.value})}
                                        className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                                    >
                                        <option value="jpmorgan_login">JPMorgan Login</option>
                                        <option value="itau_onshore_login">Itau Onshore Login</option>
                                        <option value="itau_offshore_login">Itau Offshore Login</option>
                                        <option value="btg_onshore_login">BTG Onshore Login</option>
                                        <option value="btg_offshore_login">BTG Offshore Login</option>
                                        <option value="btg_mfo_login">BTG MFO Login</option>
                                        <option value="morgan_stanley_login">Morgan Stanley Login</option>
                                        <option value="jefferies_login">Jefferies Login</option>
                                        {/* <option value="generic_scraper">Generic Scraper</option> */}
                                    </select>
                                </div>

                                {/* Dynamic Params Section */}
                                <div className="border-t border-white/10 pt-4">
                                    <div className="flex items-center justify-between mb-3">
                                        <h4 className="text-sm font-semibold text-slate-300">Parameters</h4>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                if (!jsonMode) {
                                                    // Switching TO JSON mode: convert form to JSON
                                                    const allParams = {
                                                        ...formData.params,
                                                        export_holdings: formData.export_holdings,
                                                        export_history: formData.export_history,
                                                        date_mode: formData.date_mode,
                                                        ...(formData.date_mode === 'lag' ? {
                                                            holdings_lag_days: formData.holdings_lag_days,
                                                            history_lag_days: formData.history_lag_days,
                                                        } : {
                                                            holdings_date: formData.holdings_date,
                                                            history_date: formData.history_date,
                                                        })
                                                    };
                                                    setJsonParams(JSON.stringify(allParams, null, 2));
                                                }
                                                setJsonMode(!jsonMode);
                                            }}
                                            className="text-xs px-3 py-1 rounded-lg border border-white/10 hover:bg-white/5 transition-colors flex items-center space-x-1"
                                        >
                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path>
                                            </svg>
                                            <span className="text-slate-400">{jsonMode ? 'Form Mode' : 'JSON Mode'}</span>
                                        </button>
                                    </div>

                                    {jsonMode ? (
                                        <div>
                                            <textarea
                                                value={jsonParams}
                                                onChange={(e) => setJsonParams(e.target.value)}
                                                className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500 font-mono text-sm"
                                                rows={8}
                                                placeholder='{\n  "key": "value"\n}'
                                            />
                                            <p className="text-xs text-slate-500 mt-2">
                                                Enter JSON object with params for the connector
                                            </p>
                                        </div>
                                    ) : (
                                        <>
                                            {['jpmorgan_login', 'itau_onshore_login', 'itau_offshore_login', 'btg_onshore_login', 'btg_offshore_login', 'btg_mfo_login', 'morgan_stanley_login', 'jefferies_login'].includes(formData.connector) ? (
                                                <div className="space-y-4">
                                                    {/* Credential Selector */}
                                                    <div>
                                                        <label className="block text-sm text-slate-400 mb-2">
                                                            Authentication Method
                                                        </label>
                                                        <select
                                                            value={formData.credential_id || 'manual'}
                                                            onChange={(e) => {
                                                                const value = e.target.value;
                                                                if (value === 'manual') {
                                                                    setFormData({ ...formData, credential_id: '' });
                                                                } else {
                                                                    setFormData({ ...formData, credential_id: value, params: {} });
                                                                }
                                                            }}
                                                            className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                                                        >
                                                            <option value="manual">Manual (enter username/password)</option>
                                                            <optgroup label="Saved Credentials">
                                                                {credentials
                                                                    .filter(c => c.workspace_id === formData.workspace_id)
                                                                    .map(cred => (
                                                                        <option key={cred.id} value={cred.id}>
                                                                            🔐 {cred.label} ({cred.username})
                                                                        </option>
                                                                    ))}
                                                            </optgroup>
                                                        </select>
                                                        {credentials.filter(c => c.workspace_id === formData.workspace_id).length === 0 && formData.workspace_id && (
                                                            <p className="text-xs text-slate-500 mt-1">
                                                                No credentials found for this workspace. <a href="/credentials" className="text-brand-400 hover:underline">Create one</a>
                                                            </p>
                                                        )}
                                                    </div>

                                                    {/* Manual Entry Fields (only if no credential selected) */}
                                                    {!formData.credential_id && (
                                                        <div className="grid grid-cols-2 gap-4">
                                                            <div>
                                                                <label className="block text-sm text-slate-400 mb-2">Username</label>
                                                                <input
                                                                    type="text"
                                                                    value={(formData.params as any).username || ''}
                                                                    onChange={(e) => setFormData({
                                                                        ...formData,
                                                                        params: { ...formData.params, username: e.target.value }
                                                                    })}
                                                                    className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                                                                    placeholder="user@example.com"
                                                                />
                                                            </div>
                                                            <div>
                                                                <label className="block text-sm text-slate-400 mb-2">Password</label>
                                                                <input
                                                                    type="password"
                                                                    value={(formData.params as any).password || ''}
                                                                    onChange={(e) => setFormData({
                                                                        ...formData,
                                                                        params: { ...formData.params, password: e.target.value }
                                                                    })}
                                                                    className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                                                                    placeholder="••••••••"
                                                                />
                                                            </div>
                                                            {formData.connector === 'itau_onshore_login' && (
                                                                <>
                                                                    <div>
                                                                        <label className="block text-sm text-slate-400 mb-2">Agência</label>
                                                                        <input
                                                                            type="text"
                                                                            value={(formData.params as any).agencia || ''}
                                                                            onChange={(e) => setFormData({
                                                                                ...formData,
                                                                                params: { ...formData.params, agencia: e.target.value }
                                                                            })}
                                                                            className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                                                                            placeholder="0000"
                                                                        />
                                                                    </div>
                                                                    <div>
                                                                        <label className="block text-sm text-slate-400 mb-2">Conta</label>
                                                                        <input
                                                                            type="text"
                                                                            value={(formData.params as any).conta_corrente || ''}
                                                                            onChange={(e) => setFormData({
                                                                                ...formData,
                                                                                params: { ...formData.params, conta_corrente: e.target.value }
                                                                            })}
                                                                            className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                                                                            placeholder="12345-6"
                                                                        />
                                                                    </div>
                                                                </>
                                                            )}
                                                        </div>
                                                    )}

                                                    {/* Export Options and Date Configuration */}
                                                    <div className="border border-white/10 rounded-lg p-4 space-y-4">
                                                        <h5 className="text-sm font-semibold text-slate-300">Exportações</h5>
                                                        
                                                        {/* Export Checkboxes - Side by Side */}
                                                        <div className="grid grid-cols-2 gap-4">
                                                            <label className="flex items-center space-x-2 text-sm text-slate-400">
                                                                <input
                                                                    type="checkbox"
                                                                    checked={formData.export_holdings}
                                                                    onChange={(e) => setFormData({
                                                                        ...formData,
                                                                        export_holdings: e.target.checked
                                                                    })}
                                                                    className="rounded border-white/10 bg-dark-surface"
                                                                />
                                                                <span>Exportar Posição</span>
                                                            </label>
                                                            <label className="flex items-center space-x-2 text-sm text-slate-400">
                                                                <input
                                                                    type="checkbox"
                                                                    checked={formData.export_history}
                                                                    onChange={(e) => setFormData({
                                                                        ...formData,
                                                                        export_history: e.target.checked
                                                                    })}
                                                                    className="rounded border-white/10 bg-dark-surface"
                                                                />
                                                                <span>Exportar Histórico</span>
                                                            </label>
                                                        </div>

                                                        {/* Date Configuration Mode */}
                                                        <div className="space-y-3">
                                                            <p className="text-sm text-slate-400">Configuração de Datas:</p>
                                                            <div className="grid grid-cols-2 gap-4">
                                                                <label className="flex items-center space-x-2 text-sm text-slate-400">
                                                                    <input
                                                                        type="radio"
                                                                        name="date_mode"
                                                                        checked={formData.date_mode === 'lag'}
                                                                        onChange={() => setFormData({
                                                                            ...formData,
                                                                            date_mode: 'lag'
                                                                        })}
                                                                        className="border-white/10 bg-dark-surface"
                                                                    />
                                                                    <span>Usar defasagem (dias úteis)</span>
                                                                </label>
                                                                <label className="flex items-center space-x-2 text-sm text-slate-400">
                                                                    <input
                                                                        type="radio"
                                                                        name="date_mode"
                                                                        checked={formData.date_mode === 'specific'}
                                                                        onChange={() => setFormData({
                                                                            ...formData,
                                                                            date_mode: 'specific'
                                                                        })}
                                                                        className="border-white/10 bg-dark-surface"
                                                                    />
                                                                    <span>Usar datas específicas</span>
                                                                </label>
                                                            </div>
                                                        </div>

                                                        {/* Lag-based Configuration */}
                                                        {formData.date_mode === 'lag' && (
                                                            <div className="border border-white/5 rounded-lg p-3 bg-white/5">
                                                                <div className="grid grid-cols-2 gap-4">
                                                                    <div>
                                                                        <label className="block text-sm text-slate-400 mb-2">Posição:</label>
                                                                        <div className="flex items-center space-x-2">
                                                                            <span className="text-slate-400">D-</span>
                                                                            <input
                                                                                type="number"
                                                                                min="0"
                                                                                value={formData.holdings_lag_days}
                                                                                onChange={(e) => setFormData({
                                                                                    ...formData,
                                                                                    holdings_lag_days: parseInt(e.target.value) || 1
                                                                                })}
                                                                                disabled={!formData.export_holdings}
                                                                                className="w-20 bg-dark-surface border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-brand-500 disabled:opacity-50"
                                                                            />
                                                                            <span className="text-slate-400 text-sm">dias úteis</span>
                                                                        </div>
                                                                    </div>
                                                                    <div>
                                                                        <label className="block text-sm text-slate-400 mb-2">Histórico:</label>
                                                                        <div className="flex items-center space-x-2">
                                                                            <span className="text-slate-400">D-</span>
                                                                            <input
                                                                                type="number"
                                                                                min="0"
                                                                                value={formData.history_lag_days}
                                                                                onChange={(e) => setFormData({
                                                                                    ...formData,
                                                                                    history_lag_days: parseInt(e.target.value) || 2
                                                                                })}
                                                                                disabled={!formData.export_history}
                                                                                className="w-20 bg-dark-surface border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-brand-500 disabled:opacity-50"
                                                                            />
                                                                            <span className="text-slate-400 text-sm">dias úteis</span>
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        )}

                                                        {/* Specific Date Configuration */}
                                                        {formData.date_mode === 'specific' && (
                                                            <div className="border border-white/5 rounded-lg p-3 bg-white/5">
                                                                <div className="grid grid-cols-2 gap-4">
                                                                    <div>
                                                                        <label className="block text-sm text-slate-400 mb-2">Posição:</label>
                                                                        <input
                                                                            type="date"
                                                                            value={formData.holdings_date}
                                                                            onChange={(e) => setFormData({
                                                                                ...formData,
                                                                                holdings_date: e.target.value
                                                                            })}
                                                                            disabled={!formData.export_holdings}
                                                                            className="w-full bg-dark-surface border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-brand-500 disabled:opacity-50"
                                                                        />
                                                                    </div>
                                                                    <div>
                                                                        <label className="block text-sm text-slate-400 mb-2">Histórico:</label>
                                                                        <input
                                                                            type="date"
                                                                            value={formData.history_date}
                                                                            onChange={(e) => setFormData({
                                                                                ...formData,
                                                                                history_date: e.target.value
                                                                            })}
                                                                            disabled={!formData.export_history}
                                                                            className="w-full bg-dark-surface border border-white/10 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-brand-500 disabled:opacity-50"
                                                                        />
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                            ) : (
                                                <div className="space-y-3">
                                                    <div>
                                                        <label className="block text-sm text-slate-400 mb-2">Target URL</label>
                                                        <input
                                                            type="url"
                                                            value={(formData.params as any).url || ''}
                                                            onChange={(e) => setFormData({
                                                                ...formData,
                                                                params: { ...formData.params, url: e.target.value }
                                                            })}
                                                            className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                                                            placeholder="https://example.com"
                                                        />
                                                    </div>
                                                    <div>
                                                        <label className="block text-sm text-slate-400 mb-2">CSS Selector</label>
                                                        <input
                                                            type="text"
                                                            value={(formData.params as any).selector || ''}
                                                            onChange={(e) => setFormData({
                                                                ...formData,
                                                                params: { ...formData.params, selector: e.target.value }
                                                            })}
                                                            className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500 font-mono text-sm"
                                                            placeholder=".product-title"
                                                        />
                                                    </div>
                                                </div>
                                            )}

                                        </>
                                    )}
                                </div>

                                {/* Schedule Section */}
                                <div className="border-t border-white/10 pt-4">
                                    <h4 className="text-sm font-semibold text-slate-300 mb-3">Schedule (Optional)</h4>
                                    <select
                                        value={scheduleType}
                                        onChange={(e) => setScheduleType(e.target.value)}
                                        className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500 mb-3"
                                    >
                                        {SCHEDULE_PRESETS.map(preset => (
                                            <option key={preset.value} value={preset.value}>
                                                {preset.label}
                                            </option>
                                        ))}
                                    </select>

                                    {scheduleType === 'custom' && (
                                        <div>
                                            <input
                                                type="text"
                                                value={customCron}
                                                onChange={(e) => setCustomCron(e.target.value)}
                                                className="w-full bg-dark-surface border border-white/10 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500 font-mono text-sm"
                                                placeholder="*/5 * * * *"
                                            />
                                            <p className="text-xs text-slate-500 mt-2">
                                                Format: <code className="text-brand-400">minute hour day month day_of_week</code>
                                                <br />
                                                Use <a href="https://crontab.guru" target="_blank" rel="noopener" className="text-brand-400 hover:underline">crontab.guru</a> for help
                                            </p>
                                        </div>
                                    )}

                                    {scheduleType && scheduleType !== '' && scheduleType !== 'custom' && (
                                        <div className="bg-brand-500/10 border border-brand-500/20 rounded-lg p-3">
                                            <p className="text-xs text-brand-300">
                                                <span className="font-semibold">Cron expression:</span>{' '}
                                                <code className="bg-dark-surface px-2 py-0.5 rounded">{scheduleType}</code>
                                            </p>
                                        </div>
                                    )}
                                </div>

                                <div className="flex space-x-3 pt-4 border-t border-white/10">
                                    <button
                                        type="button"
                                        onClick={() => setShowModal(false)}
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

            {/* Single Delete Modal */}
            <ConfirmModal
                isOpen={deleteModal.isOpen}
                title="Delete Job?"
                message={`Are you sure you want to delete job "${deleteModal.name}"? This cannot be undone.`}
                confirmText="Delete Job"
                isDanger={true}
                onConfirm={handleConfirmDelete}
                onCancel={() => setDeleteModal(prev => ({ ...prev, isOpen: false }))}
            />

            {/* Delete All Modal */}
            <ConfirmModal
                isOpen={deleteAllModal}
                title="Delete ALL Jobs?"
                message="DANGER: This will delete ALL jobs in ALL workspaces. This action allows you to purge the entire database of scraping tasks. This cannot be undone."
                confirmText="DELETE EVERYTHING"
                isDanger={true}
                onConfirm={handleConfirmDeleteAll}
                onCancel={() => setDeleteAllModal(false)}
            />

            {/* View Parameters Modal */}
            {viewParamsModal.isOpen && viewParamsModal.job && (
                <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
                    <div className="bg-dark-card border border-white/10 rounded-xl max-w-2xl w-full max-h-[80vh] overflow-hidden flex flex-col">
                        <div className="p-6 border-b border-white/10 flex justify-between items-center">
                            <div>
                                <h3 className="text-lg font-semibold text-white">Job Parameters</h3>
                                <p className="text-sm text-slate-400 mt-1">{viewParamsModal.job.name}</p>
                            </div>
                            <button
                                onClick={() => setViewParamsModal({ isOpen: false, job: null })}
                                className="text-slate-400 hover:text-white transition-colors"
                            >
                                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path>
                                </svg>
                            </button>
                        </div>
                        <div className="p-6 overflow-auto">
                            <pre className="bg-dark-surface border border-white/10 rounded-lg p-4 text-sm text-slate-300 font-mono overflow-x-auto">
{JSON.stringify({
    ...viewParamsModal.job.params,
    export_holdings: viewParamsModal.job.export_holdings ?? true,
    export_history: viewParamsModal.job.export_history ?? false,
    enable_processing: viewParamsModal.job.enable_processing ?? false,
    processing_config_json: viewParamsModal.job.processing_config_json || null,
    processing_script_preview: (scriptFromJobConfig(viewParamsModal.job) || '').slice(0, 200),
    date_mode: viewParamsModal.job.date_mode ?? 'lag',
    ...((viewParamsModal.job.date_mode ?? 'lag') === 'lag' ? {
        holdings_lag_days: viewParamsModal.job.holdings_lag_days ?? 1,
        history_lag_days: viewParamsModal.job.history_lag_days ?? 2,
    } : {
        holdings_date: viewParamsModal.job.holdings_date ?? '',
        history_date: viewParamsModal.job.history_date ?? '',
    })
}, null, 2)}
                            </pre>
                        </div>
                    </div>
                </div>
            )}

            {scriptModal.isOpen && scriptModal.job && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
                    <div className="glass border border-white/10 rounded-xl w-full max-w-5xl max-h-[92vh] overflow-hidden flex flex-col">
                        <div className="p-4 border-b border-white/10 flex items-center justify-between">
                            <div>
                                <h3 className="text-lg font-semibold text-white">Script Editor</h3>
                                <p className="text-xs text-slate-400">{scriptModal.job.name}</p>
                            </div>
                            <button
                                onClick={() => setScriptModal(prev => ({ ...prev, isOpen: false, job: null }))}
                                className="text-slate-400 hover:text-white transition-colors"
                            >
                                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path>
                                </svg>
                            </button>
                        </div>

                        <div className="p-4 border-b border-white/10 flex items-center gap-2">
                            <button
                                onClick={() => {
                                    const parsed =
                                        extractVisualConfigFromScript(scriptModal.script)
                                        || extractLegacyVisualConfigFromScript(scriptModal.script);
                                    if (parsed) {
                                        setVisualConfig(parsed);
                                    } else if (scriptModal.tab === 'advanced') {
                                        showToast('Advanced atual nao pode ser convertido automaticamente para Visual.', 'error');
                                    }
                                    setScriptModal(prev => ({ ...prev, tab: 'visual' }));
                                }}
                                className={`px-3 py-1.5 rounded text-sm ${scriptModal.tab === 'visual' ? 'bg-brand-600 text-white' : 'bg-white/5 text-slate-300'}`}
                            >
                                Visual
                            </button>
                            <button
                                onClick={() => {
                                    const generated = buildVisualProcessorScript(visualConfig);
                                    setScriptModal(prev => ({ ...prev, tab: 'advanced', script: generated }));
                                }}
                                className={`px-3 py-1.5 rounded text-sm ${scriptModal.tab === 'advanced' ? 'bg-brand-600 text-white' : 'bg-white/5 text-slate-300'}`}
                            >
                                Advanced
                            </button>
                        </div>

                        <div className="p-4 overflow-auto space-y-4">
                            {scriptModal.tab === 'visual' && (
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 border border-white/10 rounded-lg p-4 bg-white/5">
                                    <p className="md:col-span-2 text-xs text-slate-400">
                                        Associe cada campo de <span className="text-slate-200 font-semibold">Saida</span> para uma lista de colunas de <span className="text-slate-200 font-semibold">Entrada</span> (separadas por virgula). O sistema usa a primeira coluna encontrada.
                                    </p>
                                    <div>
                                        <label className="block text-xs text-slate-400 mb-1">Saida: Ativo</label>
                                        <div className="space-y-2">
                                            <div className="flex items-center gap-3 text-xs text-slate-300">
                                                <label className="flex items-center gap-1">
                                                    <input type="radio" checked={visualConfig.ativo_mode === 'direct'} onChange={() => setVisualConfig({ ...visualConfig, ativo_mode: 'direct' })} />
                                                    Direto
                                                </label>
                                                <label className="flex items-center gap-1">
                                                    <input type="radio" checked={visualConfig.ativo_mode === 'compose'} onChange={() => setVisualConfig({ ...visualConfig, ativo_mode: 'compose' })} />
                                                    Compor
                                                </label>
                                            </div>
                                            {visualConfig.ativo_mode === 'direct' ? (
                                                <input className="w-full bg-dark-surface border border-white/10 rounded px-3 py-2 text-sm text-white" placeholder="Entrada(s): Ativo, Nome Ativo" value={visualConfig.ativo_direct_cols} onChange={(e) => setVisualConfig({ ...visualConfig, ativo_direct_cols: e.target.value })} />
                                            ) : (
                                                <div className="space-y-2">
                                                    <input className="w-full bg-dark-surface border border-white/10 rounded px-3 py-2 text-sm text-white" placeholder="Parte 1 (base): Ativo Base, Ativo" value={visualConfig.ativo_comp_base_cols} onChange={(e) => setVisualConfig({ ...visualConfig, ativo_comp_base_cols: e.target.value })} />
                                                    <input className="w-full bg-dark-surface border border-white/10 rounded px-3 py-2 text-sm text-white" placeholder="Parte 2 (opcional): Operacao, Operação" value={visualConfig.ativo_comp_part2_cols} onChange={(e) => setVisualConfig({ ...visualConfig, ativo_comp_part2_cols: e.target.value })} />
                                                    <input className="w-full bg-dark-surface border border-white/10 rounded px-3 py-2 text-sm text-white" placeholder="Parte 3 (opcional): Emissor" value={visualConfig.ativo_comp_part3_cols} onChange={(e) => setVisualConfig({ ...visualConfig, ativo_comp_part3_cols: e.target.value })} />
                                                    <input className="w-full bg-dark-surface border border-white/10 rounded px-3 py-2 text-sm text-white" placeholder="Parte 4 primaria: Vencimento" value={visualConfig.ativo_comp_part4_primary_cols} onChange={(e) => setVisualConfig({ ...visualConfig, ativo_comp_part4_primary_cols: e.target.value })} />
                                                    <input className="w-full bg-dark-surface border border-white/10 rounded px-3 py-2 text-sm text-white" placeholder="Parte 4 fallback: Codigo, Código" value={visualConfig.ativo_comp_part4_fallback_cols} onChange={(e) => setVisualConfig({ ...visualConfig, ativo_comp_part4_fallback_cols: e.target.value })} />
                                                    <input className="w-full bg-dark-surface border border-white/10 rounded px-3 py-2 text-sm text-white" placeholder="Separador (ex:  - )" value={visualConfig.ativo_separator} onChange={(e) => setVisualConfig({ ...visualConfig, ativo_separator: e.target.value })} />
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                    <div>
                                        <label className="block text-xs text-slate-400 mb-1">Saida: Quant</label>
                                        <input className="w-full bg-dark-surface border border-white/10 rounded px-3 py-2 text-sm text-white" placeholder="Entrada(s): q, Quant, Quantidade" value={visualConfig.quant_cols} onChange={(e) => setVisualConfig({ ...visualConfig, quant_cols: e.target.value })} />
                                    </div>
                                    <div>
                                        <label className="block text-xs text-slate-400 mb-1">Saida: PU</label>
                                        <input className="w-full bg-dark-surface border border-white/10 rounded px-3 py-2 text-sm text-white" placeholder="Entrada(s): pu, PU, Preco Unitario" value={visualConfig.pu_cols} onChange={(e) => setVisualConfig({ ...visualConfig, pu_cols: e.target.value })} />
                                    </div>
                                    <div>
                                        <label className="block text-xs text-slate-400 mb-1">Saida: SaldoBruto</label>
                                        <input className="w-full bg-dark-surface border border-white/10 rounded px-3 py-2 text-sm text-white" placeholder="Entrada(s): sb, SaldoBruto, Saldo Bruto" value={visualConfig.saldo_bruto_cols} onChange={(e) => setVisualConfig({ ...visualConfig, saldo_bruto_cols: e.target.value })} />
                                    </div>
                                    <div>
                                        <label className="block text-xs text-slate-400 mb-1">Saida: Caixa</label>
                                        <input className="w-full bg-dark-surface border border-white/10 rounded px-3 py-2 text-sm text-white" placeholder="Entrada(s): Caixa, Eh Caixa, e_caixa" value={visualConfig.caixa_cols} onChange={(e) => setVisualConfig({ ...visualConfig, caixa_cols: e.target.value })} />
                                    </div>
                                    <div>
                                        <label className="block text-xs text-slate-400 mb-1">Saida: Moeda</label>
                                        <input className="w-full bg-dark-surface border border-white/10 rounded px-3 py-2 text-sm text-white" placeholder="Valor fixo (ex: BRL)" value={visualConfig.moeda_fixa} onChange={(e) => setVisualConfig({ ...visualConfig, moeda_fixa: e.target.value })} />
                                    </div>
                                    <div className="md:col-span-2 border border-white/10 rounded p-3 bg-black/20 space-y-2">
                                        <p className="text-xs text-slate-300 font-semibold">Filtros de Linha</p>
                                        <label className="flex items-center gap-2 text-xs text-slate-300">
                                            <input type="checkbox" checked={visualConfig.filter_zero_enabled} onChange={(e) => setVisualConfig({ ...visualConfig, filter_zero_enabled: e.target.checked })} />
                                            Ignorar [campo] zero
                                        </label>
                                        {visualConfig.filter_zero_enabled && (
                                            <input className="w-full bg-dark-surface border border-white/10 rounded px-3 py-2 text-sm text-white" placeholder="Campos para zero: sb, SaldoBruto" value={visualConfig.filter_zero_cols} onChange={(e) => setVisualConfig({ ...visualConfig, filter_zero_cols: e.target.value })} />
                                        )}

                                        <label className="flex items-center gap-2 text-xs text-slate-300">
                                            <input type="checkbox" checked={visualConfig.filter_empty_enabled} onChange={(e) => setVisualConfig({ ...visualConfig, filter_empty_enabled: e.target.checked })} />
                                            Ignorar [campo] vazio
                                        </label>
                                        {visualConfig.filter_empty_enabled && (
                                            <input className="w-full bg-dark-surface border border-white/10 rounded px-3 py-2 text-sm text-white" placeholder="Campos para vazio: Ativo, Nome Ativo" value={visualConfig.filter_empty_cols} onChange={(e) => setVisualConfig({ ...visualConfig, filter_empty_cols: e.target.value })} />
                                        )}

                                        <label className="flex items-center gap-2 text-xs text-slate-300">
                                            <input type="checkbox" checked={visualConfig.only_enabled} onChange={(e) => setVisualConfig({ ...visualConfig, only_enabled: e.target.checked })} />
                                            Somente [campo]
                                        </label>
                                        {visualConfig.only_enabled && (
                                            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                                                <input className="bg-dark-surface border border-white/10 rounded px-3 py-2 text-sm text-white" placeholder="Campo(s): Caixa, Eh Caixa" value={visualConfig.only_cols} onChange={(e) => setVisualConfig({ ...visualConfig, only_cols: e.target.value })} />
                                                <select className="bg-dark-surface border border-white/10 rounded px-3 py-2 text-sm text-white" value={visualConfig.only_mode} onChange={(e) => setVisualConfig({ ...visualConfig, only_mode: e.target.value as 'sim' | 'nao' })}>
                                                    <option value="sim">permitir true/sim</option>
                                                    <option value="nao">permitir false/nao</option>
                                                </select>
                                                <input className="bg-dark-surface border border-white/10 rounded px-3 py-2 text-sm text-white" placeholder="Valores true: 1, true, sim, s" value={visualConfig.only_true_values} onChange={(e) => setVisualConfig({ ...visualConfig, only_true_values: e.target.value })} />
                                            </div>
                                        )}
                                    </div>
                                    <div className="md:col-span-2">
                                        <div className="flex items-center gap-2">
                                            <button
                                                onClick={() => {
                                                    const generated = buildVisualProcessorScript(visualConfig);
                                                    setScriptModal(prev => ({ ...prev, script: generated, tab: 'advanced' }));
                                                }}
                                                className="bg-brand-600 hover:bg-brand-500 text-white px-4 py-2 rounded text-sm"
                                            >
                                                Gerar Preview no Advanced
                                            </button>
                                            <button
                                                onClick={testMappingWithLatestDownload}
                                                disabled={mappingPreview.loading}
                                                className="bg-white/10 hover:bg-white/20 text-white px-4 py-2 rounded text-sm disabled:opacity-60"
                                            >
                                                {mappingPreview.loading ? 'Testando...' : 'Testar no ultimo download'}
                                            </button>
                                        </div>
                                    </div>
                                    {mappingPreview.columns.length > 0 && (
                                        <div className="md:col-span-2 border border-white/10 rounded-lg p-3 bg-black/20">
                                            <p className="text-xs text-slate-300 mb-2">
                                                Fonte: run <span className="font-mono">{mappingPreview.runId}</span> | arquivo <span className="font-mono">{mappingPreview.filename}</span>
                                                {mappingPreview.selectedSheet ? ` | aba ${mappingPreview.selectedSheet}` : ''}
                                            </p>
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                                                {mappingPreview.matches.map((m) => (
                                                    <div key={m.output} className="text-xs text-slate-300">
                                                        <span className="text-slate-400">Saida {m.output}:</span>{' '}
                                                        {m.matched ? (
                                                            <span className="text-emerald-300 font-mono">{m.matched}</span>
                                                        ) : (
                                                            <span className="text-amber-300">nao encontrou ({m.aliases.join(', ')})</span>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                            <p className="text-xs text-slate-500 mt-2">
                                                Colunas detectadas: {mappingPreview.columns.join(', ')}
                                            </p>
                                        </div>
                                    )}
                                </div>
                            )}

                            {scriptModal.tab === 'advanced' && (
                                <textarea
                                    value={scriptModal.script}
                                    onChange={(e) => setScriptModal(prev => ({ ...prev, script: e.target.value }))}
                                    className="w-full min-h-[360px] bg-dark-surface border border-white/10 rounded-lg px-4 py-3 text-white font-mono text-sm"
                                    placeholder="Cole ou edite o script advanced..."
                                />
                            )}
                        </div>

                        <div className="p-4 border-t border-white/10 flex items-center justify-end gap-3">
                            <button
                                onClick={() => setScriptModal(prev => ({ ...prev, isOpen: false, job: null }))}
                                className="bg-white/5 hover:bg-white/10 text-white px-4 py-2 rounded"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={saveJobScript}
                                disabled={savingScript}
                                className="bg-brand-600 hover:bg-brand-500 text-white px-4 py-2 rounded disabled:opacity-50"
                            >
                                {savingScript ? 'Saving...' : 'Save Script'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </Layout>
    );
}
