import { useEffect, useMemo, useRef, useState } from "react";
import axios, { AxiosError } from "axios";
import JSZip from "jszip";
import Layout from "../components/Layout";
import { useToast } from "../context/ToastContext";

const apiBase = import.meta.env.VITE_API_URL || "http://localhost:8000";
const SANDBOX_MODE = "docker";
const PROCESS_TIMEOUT_SECONDS = 300;
const PERSISTED_FOLDERS_DB_NAME = "beehus_processamento_automatizado";
const PERSISTED_FOLDERS_STORE_NAME = "settings";
const PERSISTED_FOLDERS_KEY = "selected_folders_v1";

type FolderEntry = {
  file: File;
  relativePath: string;
};

type FolderUpload = {
  id: string;
  displayName: string;
  displayPath: string;
  directoryHandle: FileSystemDirectoryHandle;
};

type PersistedFolderEntry = {
  id: string;
  displayName: string;
  displayPath: string;
  directoryHandle: FileSystemDirectoryHandle;
};

type FolderExecutionStatus = {
  folder: string;
  status: "running" | "success" | "failed";
  error?: string;
};

type FolderPreparedMetrics = {
  fileCount: number;
  inputCount: number;
  scriptCount: number;
  totalBytes: number;
};

type ProcessedFileRecord = {
  folder: string;
  path: string;
  filename: string;
  url: string;
  blob: Blob;
};

type WindowWithDirectoryPicker = Window & {
  showDirectoryPicker?: (options?: {
    mode?: "read" | "readwrite";
  }) => Promise<FileSystemDirectoryHandle>;
};

type DirectoryHandleWithPermission = FileSystemDirectoryHandle & {
  queryPermission?: (descriptor: {
    mode: "read" | "readwrite";
  }) => Promise<PermissionState>;
  requestPermission?: (descriptor: {
    mode: "read" | "readwrite";
  }) => Promise<PermissionState>;
};

type ParsedBackendError = {
  message: string;
  errors: FolderExecutionStatus[];
};

type SandboxHealthResponse = {
  ready: boolean;
  sandbox_mode: string;
  docker_available: boolean;
  image: string;
  image_pull_ok: boolean;
  docker_version?: string | null;
  message: string;
};

function timestamped(message: string): string {
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  return `[${hh}:${mm}:${ss}] ${message}`;
}

function slugifyFolderName(value: string): string {
  const normalized = value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9._-]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
  return normalized || "pasta";
}

function bytesLabel(value: number): string {
  const sizes = ["B", "KB", "MB", "GB"];
  if (value <= 0) {
    return "0 B";
  }
  const index = Math.min(
    Math.floor(Math.log(value) / Math.log(1024)),
    sizes.length - 1,
  );
  const amount = value / 1024 ** index;
  return `${amount.toFixed(index === 0 ? 0 : 1)} ${sizes[index]}`;
}

async function collectEntriesFromDirectoryHandle(
  directoryHandle: FileSystemDirectoryHandle,
  prefix = "",
): Promise<FolderEntry[]> {
  const out: FolderEntry[] = [];
  const directoryHandleWithEntries = directoryHandle as unknown as {
    entries: () => AsyncIterableIterator<[string, FileSystemHandle]>;
  };

  for await (const [, entry] of directoryHandleWithEntries.entries()) {
    if (entry.kind === "file") {
      const fileHandle = entry as FileSystemFileHandle;
      const file = await fileHandle.getFile();
      const relativePath = prefix ? `${prefix}/${file.name}` : file.name;
      out.push({ file, relativePath });
    }
  }

  return out;
}

async function parseFolderHandleSelection(
  directoryHandle: FileSystemDirectoryHandle,
  sequence: number,
): Promise<FolderUpload> {
  const displayName = directoryHandle.name || `Pasta ${sequence}`;
  const id = `${slugifyFolderName(displayName)}_${sequence}`;

  return {
    id,
    displayName,
    displayPath: displayName,
    directoryHandle,
  };
}

function extractDownloadFilename(
  disposition: string | undefined,
): string | null {
  if (!disposition) {
    return null;
  }
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1]);
  }
  const plainMatch = disposition.match(/filename="?([^";]+)"?/i);
  return plainMatch?.[1] ?? null;
}

function isDirectoryHandle(value: unknown): value is FileSystemDirectoryHandle {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as { kind?: unknown }).kind === "directory"
  );
}

function openPersistedFoldersDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (!window.indexedDB) {
      reject(new Error("IndexedDB indisponivel"));
      return;
    }

    const request = window.indexedDB.open(PERSISTED_FOLDERS_DB_NAME, 1);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(PERSISTED_FOLDERS_STORE_NAME)) {
        db.createObjectStore(PERSISTED_FOLDERS_STORE_NAME);
      }
    };

    request.onsuccess = () => {
      resolve(request.result);
    };

    request.onerror = () => {
      reject(request.error ?? new Error("Falha ao abrir IndexedDB"));
    };
  });
}

function normalizePersistedFolders(raw: unknown): FolderUpload[] {
  if (!Array.isArray(raw)) {
    return [];
  }

  const usedIds = new Set<string>();
  const restored: FolderUpload[] = [];

  for (const item of raw) {
    if (typeof item !== "object" || item === null) {
      continue;
    }

    const candidate = item as {
      id?: unknown;
      displayName?: unknown;
      displayPath?: unknown;
      directoryHandle?: unknown;
    };

    const displayName =
      typeof candidate.displayName === "string"
        ? candidate.displayName.trim()
        : "";
    const displayPath =
      typeof candidate.displayPath === "string"
        ? candidate.displayPath.trim()
        : "";
    const handle = candidate.directoryHandle;

    if (!displayName || !displayPath || !isDirectoryHandle(handle)) {
      continue;
    }

    const baseId =
      typeof candidate.id === "string" && candidate.id.trim()
        ? candidate.id.trim()
        : `${slugifyFolderName(displayName)}_${restored.length + 1}`;

    let id = baseId;
    let suffix = 2;
    while (usedIds.has(id)) {
      id = `${baseId}_${suffix}`;
      suffix += 1;
    }
    usedIds.add(id);

    restored.push({
      id,
      displayName,
      displayPath,
      directoryHandle: handle,
    });
  }

  return restored;
}

async function loadPersistedFolders(): Promise<FolderUpload[]> {
  try {
    const db = await openPersistedFoldersDb();
    return await new Promise<FolderUpload[]>((resolve) => {
      const tx = db.transaction(PERSISTED_FOLDERS_STORE_NAME, "readonly");
      const store = tx.objectStore(PERSISTED_FOLDERS_STORE_NAME);
      const request = store.get(PERSISTED_FOLDERS_KEY);

      request.onsuccess = () => {
        resolve(normalizePersistedFolders(request.result));
      };

      request.onerror = () => {
        resolve([]);
      };

      tx.oncomplete = () => {
        db.close();
      };

      tx.onabort = () => {
        db.close();
        resolve([]);
      };

      tx.onerror = () => {
        db.close();
        resolve([]);
      };
    });
  } catch {
    return [];
  }
}

async function savePersistedFolders(folders: FolderUpload[]): Promise<void> {
  const payload: PersistedFolderEntry[] = folders.map((folder) => ({
    id: folder.id,
    displayName: folder.displayName,
    displayPath: folder.displayPath,
    directoryHandle: folder.directoryHandle,
  }));

  try {
    const db = await openPersistedFoldersDb();
    await new Promise<void>((resolve) => {
      const tx = db.transaction(PERSISTED_FOLDERS_STORE_NAME, "readwrite");
      const store = tx.objectStore(PERSISTED_FOLDERS_STORE_NAME);
      const request = store.put(payload, PERSISTED_FOLDERS_KEY);

      request.onerror = () => {
        resolve();
      };

      tx.oncomplete = () => {
        db.close();
        resolve();
      };

      tx.onabort = () => {
        db.close();
        resolve();
      };

      tx.onerror = () => {
        db.close();
        resolve();
      };
    });
  } catch {
    // Ignora falha de persistencia local.
  }
}

function isZipPayload(
  contentType: string | undefined,
  filename: string,
): boolean {
  const normalizedType = (contentType || "").split(";")[0].trim().toLowerCase();
  return (
    normalizedType === "application/zip" ||
    filename.toLowerCase().endsWith(".zip")
  );
}

function createSingleProcessedFileRecord(
  blob: Blob,
  filename: string,
  folder: string,
): ProcessedFileRecord {
  return {
    folder,
    path: filename,
    filename,
    url: URL.createObjectURL(blob),
    blob,
  };
}

async function buildProcessedFileRecords(
  blob: Blob,
  filename: string,
  contentType: string | undefined,
  fallbackFolder: string,
): Promise<ProcessedFileRecord[]> {
  if (!isZipPayload(contentType, filename)) {
    return [createSingleProcessedFileRecord(blob, filename, fallbackFolder)];
  }

  try {
    const zip = await JSZip.loadAsync(blob);
    const files: ProcessedFileRecord[] = [];
    const sortedPaths = Object.keys(zip.files).sort();

    for (const zipPath of sortedPaths) {
      const entry = zip.files[zipPath];
      if (!entry || entry.dir || zipPath === "processing_report.json") {
        continue;
      }

      const parts = zipPath.split("/").filter(Boolean);
      const folder = parts.length > 1 ? parts[0] : fallbackFolder;
      const shortName = parts[parts.length - 1] || zipPath;
      const entryBlob = await entry.async("blob");

      files.push({
        folder,
        path: zipPath,
        filename: shortName,
        url: URL.createObjectURL(entryBlob),
        blob: entryBlob,
      });
    }

    if (files.length > 0) {
      return files;
    }
  } catch {
    // Fallback para download unico quando o ZIP nao puder ser lido no cliente.
  }

  return [createSingleProcessedFileRecord(blob, filename, fallbackFolder)];
}

function fallbackFilenameFromContentType(
  contentType: string | undefined,
): string {
  const normalized = (contentType || "").split(";")[0].trim().toLowerCase();

  const extensionByType: Record<string, string> = {
    "application/zip": "zip",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xls",
    "text/csv": "csv",
    "application/json": "json",
    "text/plain": "txt",
  };

  const extension = extensionByType[normalized] || "bin";
  return `processamento_automatizado_${Date.now()}.${extension}`;
}

function normalizeFolderStatus(
  raw: string | undefined,
): FolderExecutionStatus["status"] {
  if (raw === "success") {
    return "success";
  }
  if (raw === "running") {
    return "running";
  }
  return "failed";
}

async function parseError(error: unknown): Promise<ParsedBackendError> {
  if (!(error instanceof AxiosError)) {
    return {
      message:
        error instanceof Error
          ? error.message
          : "Falha inesperada durante o processamento.",
      errors: [],
    };
  }

  const normalizeDetail = (detail: unknown): ParsedBackendError | null => {
    if (typeof detail === "string") {
      return {
        message: detail,
        errors: [],
      };
    }

    if (
      detail &&
      typeof detail === "object" &&
      "message" in detail &&
      "errors" in detail &&
      Array.isArray((detail as { errors: unknown }).errors)
    ) {
      const detailObj = detail as {
        message?: unknown;
        errors: Array<{ folder?: string; status?: string; error?: string }>;
      };
      const normalizedErrors: FolderExecutionStatus[] = detailObj.errors.map(
        (entry) => {
          const folder = entry.folder || "pasta";
          return {
            folder,
            status: normalizeFolderStatus(entry.status),
            error: entry.error || "",
          } satisfies FolderExecutionStatus;
        },
      );
      return {
        message:
          typeof detailObj.message === "string"
            ? detailObj.message
            : "Falha ao processar pastas.",
        errors: normalizedErrors,
      };
    }

    return null;
  };

  const payload = error.response?.data;
  if (payload && typeof payload === "object" && !(payload instanceof Blob)) {
    const detail = (payload as { detail?: unknown }).detail;
    const normalized = normalizeDetail(detail);
    if (normalized) {
      return normalized;
    }

    const message = (payload as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) {
      return {
        message,
        errors: [],
      };
    }

    return {
      message: error.message || "Falha ao processar pastas.",
      errors: [],
    };
  }

  if (typeof payload === "string") {
    try {
      const parsed = JSON.parse(payload);
      const normalized = normalizeDetail(
        (parsed as { detail?: unknown }).detail,
      );
      if (normalized) {
        return normalized;
      }
    } catch {
      if (payload.trim()) {
        return {
          message: payload,
          errors: [],
        };
      }
    }

    return {
      message: error.message || "Falha ao processar pastas.",
      errors: [],
    };
  }

  try {
    const raw = await payload.text();
    const parsed = JSON.parse(raw) as { detail?: unknown };
    const normalized = normalizeDetail(parsed.detail);
    if (normalized) {
      return normalized;
    }
    return {
      message: raw || "Falha ao processar pastas.",
      errors: [],
    };
  } catch {
    return {
      message: "Falha ao processar pastas.",
      errors: [],
    };
  }
}

async function ensureDirectoryWritePermission(
  directoryHandle: FileSystemDirectoryHandle,
): Promise<boolean> {
  const handleWithPermission =
    directoryHandle as DirectoryHandleWithPermission;

  if (handleWithPermission.queryPermission) {
    const permission = await handleWithPermission.queryPermission({
      mode: "readwrite",
    });
    if (permission === "granted") {
      return true;
    }
  }

  if (handleWithPermission.requestPermission) {
    const permission = await handleWithPermission.requestPermission({
      mode: "readwrite",
    });
    return permission === "granted";
  }

  return false;
}

export default function ProcessamentoAutomatizado() {
  const [folders, setFolders] = useState<FolderUpload[]>([]);
  const [foldersLoadedFromStorage, setFoldersLoadedFromStorage] =
    useState(false);
  const [processing, setProcessing] = useState(false);
  const [sandboxHealthMessage, setSandboxHealthMessage] = useState("");
  const [folderExecutionStatuses, setFolderExecutionStatuses] = useState<
    FolderExecutionStatus[]
  >([]);
  const [preparedMetrics, setPreparedMetrics] = useState<
    Record<string, FolderPreparedMetrics>
  >({});
  const [processedFiles, setProcessedFiles] = useState<ProcessedFileRecord[]>(
    [],
  );
  const [logs, setLogs] = useState<string[]>([]);
  const selectionTargetFolderIdRef = useRef<string | null>(null);
  const { showToast } = useToast();

  useEffect(() => {
    let active = true;

    void (async () => {
      const restored = await loadPersistedFolders();
      if (!active) {
        return;
      }
      setFolders(restored);
      setFoldersLoadedFromStorage(true);
    })();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!foldersLoadedFromStorage) {
      return;
    }
    void savePersistedFolders(folders);
  }, [folders, foldersLoadedFromStorage]);

  useEffect(() => {
    return () => {
      for (const file of processedFiles) {
        URL.revokeObjectURL(file.url);
      }
    };
  }, [processedFiles]);

  const summary = useMemo(() => {
    const metrics = Object.values(preparedMetrics);
    const totalFiles = metrics.reduce(
      (sum, folder) => sum + folder.fileCount,
      0,
    );
    const totalInputs = metrics.reduce(
      (sum, folder) => sum + folder.inputCount,
      0,
    );
    const totalScripts = metrics.reduce(
      (sum, folder) => sum + folder.scriptCount,
      0,
    );
    const totalBytes = metrics.reduce(
      (sum, folder) => sum + folder.totalBytes,
      0,
    );
    return {
      totalFiles,
      totalInputs,
      totalScripts,
      totalBytes,
    };
  }, [preparedMetrics]);

  const pushLog = (message: string) => {
    setLogs((prev) => [...prev, timestamped(message)]);
  };

  const resolveSelectionSequence = (targetFolderId: string | null): number => {
    if (!targetFolderId) {
      return folders.length + 1;
    }
    const currentEditingIndex = folders.findIndex(
      (folder) => folder.id === targetFolderId,
    );
    return currentEditingIndex >= 0
      ? currentEditingIndex + 1
      : folders.length + 1;
  };

  const clearExecutionFeedback = () => {
    setFolderExecutionStatuses([]);
    setLogs([]);
    setSandboxHealthMessage("");
    setProcessedFiles([]);
    setPreparedMetrics({});
  };

  const triggerBrowserDownload = (file: ProcessedFileRecord) => {
    const link = document.createElement("a");
    link.href = file.url;
    link.download = file.filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleDownloadFile = async (file: ProcessedFileRecord) => {
    const folderHandle = folders.find(
      (folder) => folder.id === file.folder,
    )?.directoryHandle;

    if (!folderHandle) {
      triggerBrowserDownload(file);
      return;
    }

    try {
      const canWrite = await ensureDirectoryWritePermission(folderHandle);
      if (!canWrite) {
        triggerBrowserDownload(file);
        showToast(
          "Sem permissao de escrita na pasta original. Usando download do navegador.",
          "error",
        );
        return;
      }

      const target = await folderHandle.getFileHandle(file.filename, {
        create: true,
      });
      const writable = await target.createWritable();
      await writable.write(file.blob);
      await writable.close();
      showToast(`Arquivo salvo na pasta original: ${file.filename}`, "success");
    } catch {
      triggerBrowserDownload(file);
      showToast(
        "Nao foi possivel salvar direto na pasta original. Usando download do navegador.",
        "error",
      );
    }
  };

  const applySelectedFolder = (
    folder: FolderUpload,
    targetFolderId: string | null,
  ) => {
    if (targetFolderId) {
      setFolders((prev) =>
        prev.map((current) =>
          current.id === targetFolderId
            ? {
                ...folder,
                id: current.id,
              }
            : current,
        ),
      );
      return;
    }

    setFolders((prev) => [...prev, folder]);
  };

  const trySelectFolderWithDirectoryPicker = async (
    targetFolderId: string | null,
  ): Promise<boolean> => {
    const windowWithPicker = window as WindowWithDirectoryPicker;
    if (!windowWithPicker.showDirectoryPicker) {
      showToast(
        "Navegador sem suporte ao seletor de pasta. Use Chrome/Edge em contexto seguro (localhost ou HTTPS).",
        "error",
      );
      return true;
    }

    try {
      const directoryHandle = await windowWithPicker.showDirectoryPicker({
        mode: "read",
      });
      const folder = await parseFolderHandleSelection(
        directoryHandle,
        resolveSelectionSequence(targetFolderId),
      );
      applySelectedFolder(folder, targetFolderId);
      return true;
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return true;
      }

      showToast(
        "Nao foi possivel abrir o seletor de pasta sem confirmacao de upload. Verifique se o navegador e compativel (Chrome/Edge) e se o site esta em contexto seguro.",
        "error",
      );
      return true;
    }
  };

  const beginFolderSelection = (targetFolderId: string | null) => {
    selectionTargetFolderIdRef.current = targetFolderId;

    void (async () => {
      const selectedWithPicker =
        await trySelectFolderWithDirectoryPicker(targetFolderId);
      if (selectedWithPicker) {
        selectionTargetFolderIdRef.current = null;
      }
    })();
  };

  const startEditFolder = (id: string) => {
    beginFolderSelection(id);
  };

  const removeFolder = (id: string) => {
    setFolders((prev) => prev.filter((folder) => folder.id !== id));
  };

  const validateFolders = (): string | null => {
    if (folders.length === 0) {
      return "Adicione pelo menos uma pasta antes de processar.";
    }

    return null;
  };

  const ensureDirectoryReadPermission = async (
    directoryHandle: FileSystemDirectoryHandle,
  ): Promise<boolean> => {
    const handleWithPermission =
      directoryHandle as DirectoryHandleWithPermission;

    if (handleWithPermission.queryPermission) {
      const permission = await handleWithPermission.queryPermission({
        mode: "read",
      });
      if (permission === "granted") {
        return true;
      }
    }

    if (handleWithPermission.requestPermission) {
      const permission = await handleWithPermission.requestPermission({
        mode: "read",
      });
      return permission === "granted";
    }

    return true;
  };

  const runSandboxHealthCheck = async (): Promise<boolean> => {
    pushLog(
      `Executando health-check sandbox (mode=${SANDBOX_MODE}, pull_image=false, run_probe=true, timeout=${PROCESS_TIMEOUT_SECONDS}s)...`,
    );
    try {
      const response = await axios.get<SandboxHealthResponse>(
        `${apiBase}/processamento-automatizado/sandbox-health`,
        {
          params: {
            sandbox_mode: SANDBOX_MODE,
            pull_image: false,
            run_probe: true,
            timeout_seconds: PROCESS_TIMEOUT_SECONDS,
          },
          timeout: 0,
        },
      );
      const payload = response.data;
      const message = `${payload.message} Imagem: ${payload.image}${payload.docker_version ? ` (Docker ${payload.docker_version})` : ""}.`;
      setSandboxHealthMessage(message);
      pushLog(`Health-check sandbox: ${message}`);
      return true;
    } catch (error) {
      const parsed = await parseError(error);
      const message = `Health-check sandbox falhou: ${parsed.message}`;
      setSandboxHealthMessage(message);
      pushLog(message);
      showToast(parsed.message, "error");
      return false;
    }
  };

  const processFolders = async () => {
    const validationError = validateFolders();
    if (validationError) {
      showToast(validationError, "error");
      return;
    }

    setProcessing(true);
    setLogs([]);
    setProcessedFiles([]);
    const initialStatuses: FolderExecutionStatus[] = folders.map((folder) => ({
      folder: folder.id,
      status: "running",
      error: "",
    }));
    setFolderExecutionStatuses(initialStatuses);
    pushLog(
      `Iniciando processamento de ${folders.length} pasta(s) por upload...`,
    );
    pushLog("Sandbox Docker ativado para execucao dos scripts.");

    try {
      const sandboxOk = await runSandboxHealthCheck();
      if (!sandboxOk) {
        setFolderExecutionStatuses((prev) =>
          prev.map((item) => ({
            ...item,
            status: "failed",
            error: "Health-check de sandbox falhou.",
          })),
        );
        return;
      }

      pushLog("Lendo arquivos atuais das pastas selecionadas...");

      const preparedByFolder: Record<string, FolderPreparedMetrics> = {};
      const preparedUploads: Array<{
        folderId: string;
        entries: FolderEntry[];
      }> = [];

      for (const folder of folders) {
        const hasPermission = await ensureDirectoryReadPermission(
          folder.directoryHandle,
        );
        if (!hasPermission) {
          throw new Error(
            `Permissao de leitura negada para a pasta ${folder.displayName}.`,
          );
        }

        const entries = await collectEntriesFromDirectoryHandle(
          folder.directoryHandle,
        );
        if (entries.length === 0) {
          throw new Error(`A pasta ${folder.displayName} esta vazia.`);
        }

        const scriptCount = entries.filter((entry) =>
          entry.file.name.toLowerCase().endsWith(".py"),
        ).length;
        const inputCount = entries.length - scriptCount;
        if (scriptCount !== 1) {
          throw new Error(
            `A pasta ${folder.displayName} precisa ter exatamente 1 arquivo .py na raiz da pasta (subpastas sao ignoradas).`,
          );
        }
        if (inputCount < 1) {
          throw new Error(
            `A pasta ${folder.displayName} precisa ter pelo menos 1 arquivo de input.`,
          );
        }

        const totalBytes = entries.reduce(
          (total, entry) => total + entry.file.size,
          0,
        );

        preparedByFolder[folder.id] = {
          fileCount: entries.length,
          inputCount,
          scriptCount,
          totalBytes,
        };
        preparedUploads.push({ folderId: folder.id, entries });
      }

      setPreparedMetrics(preparedByFolder);

      const formData = new FormData();
      for (const prepared of preparedUploads) {
        for (const entry of prepared.entries) {
          const uploadName = `${prepared.folderId}/${entry.relativePath}`;
          formData.append("files", entry.file, uploadName);
        }
      }
      pushLog("Upload automatico iniciado...");

      const response = await axios.post(
        `${apiBase}/processamento-automatizado/process`,
        formData,
        {
          params: {
            timeout_seconds: PROCESS_TIMEOUT_SECONDS,
            sandbox_mode: SANDBOX_MODE,
            download_mode: "auto",
          },
          responseType: "blob",
          timeout: 0,
        },
      );

      const blob =
        response.data instanceof Blob
          ? response.data
          : new Blob([response.data]);
      const filename =
        extractDownloadFilename(
          response.headers["content-disposition"] as string | undefined,
        ) ||
        fallbackFilenameFromContentType(
          (response.headers["content-type"] as string | undefined) || blob.type,
        );

      const fallbackFolder = folders[0]?.id || "saida";
      const fileRecords = await buildProcessedFileRecords(
        blob,
        filename,
        (response.headers["content-type"] as string | undefined) || blob.type,
        fallbackFolder,
      );
      setProcessedFiles(fileRecords);

      setFolderExecutionStatuses((prev) =>
        prev.map((item) => ({
          ...item,
          status: "success",
          error: "",
        })),
      );
      pushLog(
        `Processamento concluido. Arquivos disponiveis para download no status por pasta (${fileRecords.length}).`,
      );
      showToast(
        "Processamento concluido com sucesso. Use os links no status por pasta para baixar.",
        "success",
      );
    } catch (error) {
      const parsed = await parseError(error);
      pushLog(`Erro: ${parsed.message}`);
      if (parsed.errors.length > 0) {
        setFolderExecutionStatuses(
          parsed.errors.map((entry) => ({
            folder: entry.folder,
            status: normalizeFolderStatus(entry.status),
            error: entry.error || "",
          })),
        );
        for (const entry of parsed.errors) {
          const suffix = entry.error ? ` - ${entry.error}` : "";
          pushLog(`Pasta ${entry.folder}: ${entry.status}${suffix}`);
        }
      } else {
        setFolderExecutionStatuses((prev) =>
          prev.map((item) => ({
            ...item,
            status: "failed",
            error: parsed.message,
          })),
        );
      }
      setProcessedFiles([]);
      showToast(parsed.message, "error");
    } finally {
      setProcessing(false);
      pushLog("Fluxo finalizado.");
    }
  };

  return (
    <Layout>
      <div className="p-8 max-w-5xl mx-auto space-y-8">
        <header className="space-y-2">
          <h2 className="text-2xl font-bold text-white">
            Processamento Automatizado
          </h2>
          <p className="text-slate-400">
            Cadastre uma ou mais pastas. Cada pasta precisa conter arquivos de
            input e exatamente um script Python de processamento.
          </p>
        </header>

        <section className="glass rounded-xl border border-white/10 p-6 space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="rounded-md border border-teal-500/30 bg-teal-500/10 px-3 py-2 text-sm text-teal-100">
              Execucao: Sandbox Docker
            </div>

            <button
              type="button"
              onClick={() => beginFolderSelection(null)}
              disabled={processing}
              className="px-4 py-2 rounded-lg border border-brand-500/40 bg-brand-500/10 text-brand-200 hover:bg-brand-500/20 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              + Pasta
            </button>
          </div>

          <div
            className="grid gap-3"
            style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}
          >
            <div className="rounded-lg border border-white/10 bg-slate-900/60 px-4 py-3">
              <p className="text-xs uppercase text-slate-500">Pastas</p>
              <p className="text-lg font-semibold text-white">
                {folders.length}
              </p>
            </div>
            <div className="rounded-lg border border-white/10 bg-slate-900/60 px-4 py-3">
              <p className="text-xs uppercase text-slate-500">Inputs</p>
              <p className="text-lg font-semibold text-white">
                {summary.totalInputs}
              </p>
            </div>
            <div className="rounded-lg border border-white/10 bg-slate-900/60 px-4 py-3">
              <p className="text-xs uppercase text-slate-500">Scripts Python</p>
              <p className="text-lg font-semibold text-white">
                {summary.totalScripts}
              </p>
            </div>
            <div className="rounded-lg border border-white/10 bg-slate-900/60 px-4 py-3">
              <p className="text-xs uppercase text-slate-500">Tamanho total</p>
              <p className="text-lg font-semibold text-white">
                {bytesLabel(summary.totalBytes)}
              </p>
            </div>
          </div>

          {folders.length === 0 ? (
            <div className="rounded-lg border border-dashed border-white/20 p-6 text-sm text-slate-400">
              Nenhuma pasta cadastrada.
            </div>
          ) : (
            <div className="space-y-3">
              {folders.map((folder) => {
                const metrics = preparedMetrics[folder.id];

                return (
                  <div
                    key={folder.id}
                    className="rounded-lg border border-white/10 bg-slate-950/60 px-4 py-3 flex flex-wrap items-center justify-between gap-3"
                  >
                    <div>
                      <p className="text-sm font-semibold text-white">
                        {folder.displayName}
                      </p>
                      {metrics ? (
                        <p className="text-xs text-slate-400">
                          {metrics.fileCount} arquivos | {metrics.inputCount}{" "}
                          inputs | {metrics.scriptCount} script(s) .py
                        </p>
                      ) : (
                        <p className="text-xs text-slate-400">
                          Arquivos lidos apenas no processamento.
                        </p>
                      )}
                      <p className="text-xs text-slate-500 break-all">
                        Caminho: {folder.displayPath}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => startEditFolder(folder.id)}
                        disabled={processing}
                        className="px-3 py-1.5 rounded-md border border-blue-500/40 bg-blue-500/10 text-blue-200 hover:bg-blue-500/20 disabled:opacity-50"
                      >
                        Editar
                      </button>
                      <button
                        type="button"
                        onClick={() => removeFolder(folder.id)}
                        disabled={processing}
                        className="px-3 py-1.5 rounded-md border border-red-500/40 bg-red-500/10 text-red-200 hover:bg-red-500/20 disabled:opacity-50"
                      >
                        Excluir
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {sandboxHealthMessage && (
            <div className="rounded-lg border border-teal-500/30 bg-teal-500/10 p-3 text-xs text-teal-100">
              {sandboxHealthMessage}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={processFolders}
              disabled={processing || folders.length === 0}
              className="px-5 py-2 rounded-lg bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-60 disabled:cursor-not-allowed whitespace-nowrap"
            >
              {processing ? "Processando..." : "Processar Pastas"}
            </button>
            <button
              type="button"
              onClick={clearExecutionFeedback}
              disabled={processing}
              className="px-5 py-2 rounded-lg border border-slate-600 text-slate-200 hover:bg-slate-800 disabled:opacity-60 disabled:cursor-not-allowed whitespace-nowrap"
            >
              Limpar status e logs
            </button>
            <span className="text-xs text-slate-500 flex-1 min-w-[260px]">
              As pastas selecionadas ficam salvas neste navegador, inclusive
              apos refresh/logout; os arquivos sao lidos e enviados apenas ao
              clicar em Processar Pastas.
            </span>
          </div>

          {folderExecutionStatuses.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs uppercase text-slate-400">
                Status por pasta
              </p>
              <div className="space-y-2">
                {folderExecutionStatuses.map((entry, idx) => {
                  const filesForFolder = processedFiles.filter(
                    (file) => file.folder === entry.folder,
                  );
                  const statusClass =
                    entry.status === "success"
                      ? "border-green-500/40 bg-green-500/10 text-green-200"
                      : entry.status === "failed"
                        ? "border-red-500/40 bg-red-500/10 text-red-200"
                        : "border-amber-500/40 bg-amber-500/10 text-amber-200";
                  return (
                    <div
                      key={`${entry.folder}-${idx}`}
                      className="rounded-md border border-white/10 bg-slate-950/60 px-3 py-2"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs text-slate-300">
                          {entry.folder}
                        </span>
                        <span
                          className={`text-[11px] px-2 py-0.5 rounded-full border ${statusClass}`}
                        >
                          {entry.status}
                        </span>
                      </div>
                      {entry.error && (
                        <p className="text-xs text-slate-400 mt-1">
                          {entry.error}
                        </p>
                      )}
                      {filesForFolder.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {filesForFolder.map((file) => (
                            <button
                              key={`${entry.folder}-${file.path}`}
                              type="button"
                              onClick={() => {
                                void handleDownloadFile(file);
                              }}
                              className="text-[11px] px-2 py-1 rounded border border-blue-500/40 bg-blue-500/10 text-blue-200 hover:bg-blue-500/20"
                            >
                              Baixar {file.filename}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </section>

        <section className="glass rounded-xl border border-white/10 p-6 space-y-3">
          <h3 className="text-lg font-semibold text-white">Logs</h3>
          <div className="bg-slate-900/80 border border-white/10 rounded-lg p-3 h-52 overflow-y-auto font-mono text-xs text-slate-300 space-y-1">
            {logs.length === 0 ? (
              <div className="text-slate-500">Aguardando acao...</div>
            ) : (
              logs.map((line, index) => (
                <div key={`${line}-${index}`}>{line}</div>
              ))
            )}
          </div>
        </section>
      </div>
    </Layout>
  );
}
