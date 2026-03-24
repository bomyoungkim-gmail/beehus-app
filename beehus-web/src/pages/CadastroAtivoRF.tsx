import { useEffect, useMemo, useRef, useState } from 'react';
import type { ChangeEvent } from 'react';
import {
  flexRender,
  getCoreRowModel,
  getExpandedRowModel,
  getFilteredRowModel,
  getGroupedRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import type {
  ColumnDef,
  ColumnFiltersState,
  ColumnVisibilityState,
  ExpandedState,
  FilterFn,
  GroupingState,
  OnChangeFn,
  SortingState,
  Updater,
} from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';
import Layout from '../components/Layout';

type RFRow = {
  id: string;
  name: string;
  category: string;
  maturityDate: string;
  rate: string;
  indexer: string;
} & Record<string, string>;

type XPFixedIncomeRecord = Record<string, unknown>;
type DivergenceMode = 'or' | 'and';
type CategoryRule = {
  nameTerms: string;
  tickerTerms: string;
};

const GLOBAL_DEFAULT_DIVERGENCE_MODE: DivergenceMode = 'or';
const GLOBAL_DEFAULT_CATEGORY_RULES: Record<string, CategoryRule> = {
  'LF-SUB': { nameTerms: 'LFSN', tickerTerms: '' },
  OVER: { nameTerms: 'Compromissada', tickerTerms: '' },
};

function pickFirst(record: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    const value = record[key];
    if (value !== undefined && value !== null && value !== '') {
      return value;
    }
  }
  return undefined;
}

function normalizeDate(value: unknown): string {
  if (!value) {
    return '';
  }
  const text = String(value).trim();
  if (!text) {
    return '';
  }
  if (/^\d{4}-\d{2}-\d{2}/.test(text)) {
    return text.slice(0, 10);
  }
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) {
    return text;
  }
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, '0');
  const day = String(parsed.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function normalizeText(value: unknown): string {
  if (value === undefined || value === null) {
    return '';
  }
  return String(value).trim();
}

function normalizeCellValue(value: unknown): string {
  if (value === undefined || value === null) {
    return '';
  }
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value).trim();
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return '';
    }
    return JSON.stringify(value);
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  return String(value);
}

function normalizeForMatch(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '');
}

function parseMatchTerms(value: string): string[] {
  return value
    .split(',')
    .map((part) => normalizeForMatch(part))
    .filter((part) => part.length > 0);
}

function normalizeCategory(value: unknown): string {
  const text = normalizeText(value);
  return text ? text.toUpperCase() : 'SEM CATEGORIA';
}

function normalizeRate(value: unknown, percentValue?: unknown): string {
  if (typeof value === 'number') {
    return `${value.toFixed(2)}%`;
  }
  if (value) {
    return normalizeText(value);
  }
  if (typeof percentValue === 'number') {
    return `${percentValue.toFixed(2)}%`;
  }
  return '';
}

function extractExtraFields(
  record: Record<string, unknown>,
  excludedKeys: string[],
): Record<string, string> {
  const excluded = new Set(excludedKeys);
  const out: Record<string, string> = {};

  for (const [key, value] of Object.entries(record)) {
    if (excluded.has(key)) {
      continue;
    }
    const normalized = normalizeCellValue(value);
    if (normalized !== '') {
      out[key] = normalized;
    }
  }

  return out;
}

async function readJsonFile(file: File): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = () => {
      try {
        const text = String(reader.result ?? '');
        resolve(JSON.parse(text));
      } catch (error) {
        reject(new Error(`JSON invalido em ${file.name}`));
      }
    };

    reader.onerror = () => {
      reject(new Error(`Falha ao ler o arquivo ${file.name}`));
    };

    reader.readAsText(file);
  });
}

function mapBeehusData(payload: unknown): RFRow[] {
  if (!Array.isArray(payload)) {
    return [];
  }

  return payload
    .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
    .map((item, idx) => {
      const name = normalizeText(pickFirst(item, ['beehusName', 'name', 'asset', 'ticker', 'mainId']));
      const category = normalizeCategory(pickFirst(item, ['type', 'category', 'marketType']));
      const maturityDate = normalizeDate(
        pickFirst(item, ['maturityDate', 'dueDate', 'expirationDate', 'due_date']),
      );
      const indexer = normalizeText(pickFirst(item, ['indexer', 'indexDsc', 'strategy']));
      const rate = normalizeRate(item['yield'], item['indexerPercentual']);
      const ticker = normalizeText(pickFirst(item, ['ticker', 'mainId']));
      const extraFields = extractExtraFields(item, [
        '_id',
        'beehusName',
        'name',
        'asset',
        'ticker',
        'mainId',
        'type',
        'category',
        'marketType',
        'maturityDate',
        'dueDate',
        'expirationDate',
        'due_date',
        'indexer',
        'indexDsc',
        'strategy',
        'yield',
        'indexerPercentual',
      ]);

      return {
        id: `beehus-${idx}-${name || 'ativo'}`,
        name,
        category,
        maturityDate,
        rate,
        indexer,
        ticker,
        ...extraFields,
      };
    });
}

function flattenXPData(payload: unknown): XPFixedIncomeRecord[] {
  const maybeRecords = Array.isArray(payload)
    ? payload
    : (payload as { data?: unknown })?.data;

  if (!Array.isArray(maybeRecords)) {
    return [];
  }

  const flat: XPFixedIncomeRecord[] = [];
  for (const entry of maybeRecords) {
    if (!entry || typeof entry !== 'object') {
      continue;
    }

    const record = entry as Record<string, unknown>;
    const assets = record['assets'];
    if (!assets || typeof assets !== 'object') {
      continue;
    }

    const fixedIncome = (assets as Record<string, unknown>)['fixedIncome'];
    if (!Array.isArray(fixedIncome)) {
      continue;
    }

    for (const fi of fixedIncome) {
      if (!fi || typeof fi !== 'object') {
        continue;
      }

      flat.push({
        ...(fi as Record<string, unknown>),
        customerCode: record['customerCode'],
        clientId: record['clientId'],
      });
    }
  }

  return flat;
}

function mapXPData(payload: unknown): RFRow[] {
  const flat = flattenXPData(payload);

  return flat.map((item, idx) => {
    const name = normalizeText(pickFirst(item, ['asset', 'name', 'ticker', 'assetId', 'cetipSelicCode']));
    const category = normalizeCategory(pickFirst(item, ['marketType', 'type', 'category']));
    const maturityDate = normalizeDate(pickFirst(item, ['dueDate', 'maturityDate', 'expirationDate']));
    const indexer = normalizeText(pickFirst(item, ['indexDsc', 'indexer', 'strategy']));
    const rate = normalizeRate(item['rate'], item['percentage']);
    const ctipseliccode = normalizeText(pickFirst(item, ['cetipSelicCode', 'ctipseliccode']));
    const extraFields = extractExtraFields(item, [
      'asset',
      'name',
      'ticker',
      'assetId',
      'cetipSelicCode',
      'ctipseliccode',
      'marketType',
      'type',
      'category',
      'dueDate',
      'maturityDate',
      'expirationDate',
      'indexer',
      'strategy',
      'rate',
    ]);

    return {
      id: `xp-${idx}-${name || 'ativo'}`,
      name,
      category,
      maturityDate,
      rate,
      indexer,
      ctipseliccode,
      ...extraFields,
    };
  });
}

const globalContainsFilter: FilterFn<RFRow> = (row, _columnId, filterValue) => {
  const query = String(filterValue ?? '').trim().toLowerCase();
  if (!query) {
    return true;
  }

  const combined = Object.entries(row.original)
    .filter(([key]) => key !== 'id')
    .map(([, value]) => value)
    .join(' ')
    .toLowerCase();

  return combined.includes(query);
};

const baseColumns: ColumnDef<RFRow>[] = [
  {
    accessorKey: 'name',
    header: 'Nome',
    enableGrouping: false,
  },
  {
    accessorKey: 'category',
    header: 'Tipo/Categoria',
    enableGrouping: true,
  },
  {
    accessorKey: 'maturityDate',
    header: 'Vencimento',
    enableGrouping: false,
  },
  {
    accessorKey: 'rate',
    header: 'Taxa',
    enableGrouping: false,
  },
  {
    accessorKey: 'indexer',
    header: 'Indexador',
    enableGrouping: false,
  },
];

function collectDatasetKeys(rows: RFRow[]): string[] {
  const keySet = new Set<string>();
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (key !== 'id') {
        keySet.add(key);
      }
    }
  }
  return Array.from(keySet);
}

function buildColumns(keys: string[], leadingKeys: string[]): ColumnDef<RFRow>[] {
  const leading = leadingKeys.filter((key) => keys.includes(key));
  const remaining = keys
    .filter((key) => !leading.includes(key))
    .sort((a, b) => a.localeCompare(b));

  const ordered = [...leading, ...remaining];
  return ordered.map((key) => ({
    accessorKey: key,
    header: key === 'category'
      ? 'Tipo/Categoria'
      : key === 'name'
      ? 'Nome'
      : key === 'maturityDate'
      ? 'Vencimento'
      : key === 'rate'
      ? 'Taxa'
      : key === 'indexer'
      ? 'Indexador'
      : key,
    enableGrouping: key === 'category',
  }));
}

function buildDefaultVisibility(
  keys: string[],
  defaultVisibleKeys: string[],
): ColumnVisibilityState {
  const defaults = new Set(defaultVisibleKeys);
  const visibility: ColumnVisibilityState = {};
  for (const key of keys) {
    visibility[key] = defaults.has(key);
  }
  return visibility;
}

function downloadJsonFile(payload: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: 'application/json;charset=utf-8;',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

type RfTableProps = {
  title: string;
  data: RFRow[];
  columns: ColumnDef<RFRow>[];
  globalFilter: string;
  columnFilters: ColumnFiltersState;
  onColumnFiltersChange: OnChangeFn<ColumnFiltersState>;
  grouping: GroupingState;
  onGroupingChange: OnChangeFn<GroupingState>;
  expanded: ExpandedState;
  onExpandedChange: OnChangeFn<ExpandedState>;
  sorting: SortingState;
  onSortingChange: OnChangeFn<SortingState>;
  columnVisibility: ColumnVisibilityState;
  onColumnVisibilityChange: OnChangeFn<ColumnVisibilityState>;
  enableDivergenceTools?: boolean;
  enableCategoryExport?: boolean;
  onLeafRowClick?: (row: RFRow) => void;
};

function RfTable({
  title,
  data,
  columns,
  globalFilter,
  columnFilters,
  onColumnFiltersChange,
  grouping,
  onGroupingChange,
  expanded,
  onExpandedChange,
  sorting,
  onSortingChange,
  columnVisibility,
  onColumnVisibilityChange,
  enableDivergenceTools = true,
  enableCategoryExport = false,
  onLeafRowClick,
}: RfTableProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [showColumnEditor, setShowColumnEditor] = useState(false);
  const [columnSearch, setColumnSearch] = useState('');
  const [divergentIds, setDivergentIds] = useState<Set<string>>(new Set());
  const [divergenceActive, setDivergenceActive] = useState(false);
  const [showRuleEditor, setShowRuleEditor] = useState(false);
  const [ruleSearch, setRuleSearch] = useState('');
  const [divergenceMode, setDivergenceMode] = useState<DivergenceMode>(GLOBAL_DEFAULT_DIVERGENCE_MODE);
  const [categoryRules, setCategoryRules] = useState<Record<string, CategoryRule>>(
    GLOBAL_DEFAULT_CATEGORY_RULES,
  );
  const [hasHydratedRules, setHasHydratedRules] = useState(false);
  const [showCategorySelector, setShowCategorySelector] = useState(false);
  const [selectedCategories, setSelectedCategories] = useState<Set<string>>(new Set());

  const table = useReactTable({
    data,
    columns,
    state: {
      globalFilter,
      columnFilters,
      grouping,
      expanded,
      sorting,
      columnVisibility,
    },
    onColumnFiltersChange,
    onGroupingChange,
    onExpandedChange,
    onSortingChange,
    onColumnVisibilityChange,
    globalFilterFn: globalContainsFilter,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getGroupedRowModel: getGroupedRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
  });

  const rows = table.getRowModel().rows;
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => 44,
    overscan: 14,
  });

  const items = virtualizer.getVirtualItems();
  const editableColumns = table
    .getAllLeafColumns()
    .filter((column) =>
      column.id.toLowerCase().includes(columnSearch.trim().toLowerCase()),
    );
  const categories = useMemo(
    () =>
      Array.from(
        new Set(
          data
            .map((row) => row.category)
            .filter((value) => typeof value === 'string' && value.trim() !== ''),
        ),
      ).sort((a, b) => a.localeCompare(b)),
    [data],
  );
  const ruleStorageKey = useMemo(
    () => `cadastro_ativo_rf_rules_${title.toLowerCase().replace(/[^a-z0-9]+/g, '_')}`,
    [title],
  );

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(ruleStorageKey);
      if (raw) {
        const parsed = JSON.parse(raw) as {
          divergenceMode?: DivergenceMode;
          categoryRules?: Record<string, CategoryRule>;
        };
        if (parsed.divergenceMode === 'or' || parsed.divergenceMode === 'and') {
          setDivergenceMode(parsed.divergenceMode);
        }
        if (parsed.categoryRules && typeof parsed.categoryRules === 'object') {
          setCategoryRules((current) => ({ ...current, ...parsed.categoryRules }));
        }
      }
    } catch {
      // Ignore localStorage read/parse errors and keep global defaults.
    } finally {
      setHasHydratedRules(true);
    }
  }, [ruleStorageKey]);

  useEffect(() => {
    setCategoryRules((current) => {
      const next: Record<string, CategoryRule> = { ...current };
      for (const category of categories) {
        if (!next[category]) {
          next[category] = {
            nameTerms: category,
            tickerTerms: category,
          };
        }
      }
      return next;
    });
  }, [categories]);

  useEffect(() => {
    if (!hasHydratedRules) {
      return;
    }
    window.localStorage.setItem(
      ruleStorageKey,
      JSON.stringify({
        divergenceMode,
        categoryRules,
      }),
    );
  }, [hasHydratedRules, divergenceMode, categoryRules, ruleStorageKey]);

  const filteredCategories = categories.filter((category) =>
    category.toLowerCase().includes(ruleSearch.trim().toLowerCase()),
  );
  const hasOpenOverlay = showColumnEditor || showRuleEditor;
  const selectedRowsForExport = useMemo(
    () => data.filter((row) => selectedCategories.has(row.category)),
    [data, selectedCategories],
  );

  const updateCategoryRule = (
    category: string,
    key: keyof CategoryRule,
    value: string,
  ) => {
    setCategoryRules((current) => ({
      ...current,
      [category]: {
        nameTerms: current[category]?.nameTerms ?? category,
        tickerTerms: current[category]?.tickerTerms ?? category,
        [key]: value,
      },
    }));
  };

  const toggleCategorySelection = (category: string) => {
    setSelectedCategories((current) => {
      const next = new Set(current);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      return next;
    });
  };

  const formatDateDdMmYyyy = (value: string): string => {
    if (!value) {
      return '';
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      const isoLike = value.match(/^(\d{4})-(\d{2})-(\d{2})/);
      if (isoLike) {
        return `${isoLike[3]}/${isoLike[2]}/${isoLike[1]}`;
      }
      return value;
    }
    const dd = String(parsed.getDate()).padStart(2, '0');
    const mm = String(parsed.getMonth() + 1).padStart(2, '0');
    const yyyy = parsed.getFullYear();
    return `${dd}/${mm}/${yyyy}`;
  };

  const escapeCsv = (value: string) => {
    const text = value ?? '';
    if (text.includes(',') || text.includes('"') || text.includes('\n')) {
      return `"${text.replace(/"/g, '""')}"`;
    }
    return text;
  };

  const toNumberOrZero = (value: string): number => {
    const normalized = String(value ?? '')
      .replace('%', '')
      .replace(',', '.')
      .trim();
    const num = Number(normalized);
    return Number.isFinite(num) ? num : 0;
  };

  const formatRatePercent = (value: string): string => {
    const raw = String(value ?? '').trim().replace(/^\+\s*/, '');
    if (!raw) {
      return '';
    }
    if (raw.includes('%')) {
      return raw;
    }
    const numeric = Number(raw.replace(',', '.'));
    if (!Number.isFinite(numeric)) {
      return raw;
    }
    return `${raw}%`;
  };

  const buildBeehusNameForXpRow = (row: RFRow): string => {
    const marketType = String(row.marketType ?? row.category ?? '').trim();
    const issuer = String(row.issuer ?? '').trim();
    const indexDsc = String(row.indexDsc ?? row.indexer ?? '').trim();
    const percentage = String(row.percentage ?? '').trim();
    const rateRaw = String(row.rate ?? '').trim();
    const rateNum = toNumberOrZero(rateRaw);
    const ratePart = rateNum !== 0 ? `+ ${rateRaw}` : '';
    const normalizedIndexer = normalizeForMatch(indexDsc);
    const dueDate = formatDateDdMmYyyy(String(row.dueDate ?? row.maturityDate ?? ''));

    if (normalizedIndexer === 'fixedrate') {
      const fixedRate = formatRatePercent(rateRaw);
      return [marketType, issuer, fixedRate, dueDate]
        .map((part) => part.trim())
        .filter((part) => part !== '')
        .join(' ');
    }

    const percentageAndIndexer = percentage
      ? `${percentage}% ${indexDsc}`.trim()
      : indexDsc;
    const indexComposite = [percentageAndIndexer, ratePart]
      .filter((part) => part !== '')
      .join(' ');

    return [marketType, issuer, indexComposite, dueDate]
      .map((part) => part.trim())
      .filter((part) => part !== '')
      .join(' ');
  };

  const exportSelectedCategoriesToCsv = () => {
    if (selectedRowsForExport.length === 0) {
      return;
    }
    const headers = [
      'BeehusName',
      'Emissor',
      'Type',
      'Vencimento',
      'Ticker',
      'Yield',
      'Indexer',
      'Indexer Percentual',
    ];
    const lines = selectedRowsForExport.map((row) => {
      const issuer = String(row.issuer ?? '').trim();
      const marketType = String(row.marketType ?? row.category ?? '').trim();
      const vencimento = formatDateDdMmYyyy(String(row.dueDate ?? row.maturityDate ?? ''));
      const ticker = String(row.cetipSelicCode ?? row.ctipseliccode ?? '').trim();
      const yieldValue = String(row.rate ?? '').trim();
      const indexer = String(row.indexDsc ?? row.indexer ?? '').trim();
      const indexerPercentual = String(row.percentage ?? '').trim();

      const cols = [
        buildBeehusNameForXpRow(row),
        issuer,
        marketType,
        vencimento,
        ticker,
        yieldValue,
        indexer,
        indexerPercentual,
      ];
      return cols.map(escapeCsv).join(',');
    });
    const csv = [headers.join(','), ...lines].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    const filenameBase = title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_|_$/g, '');
    link.href = url;
    link.setAttribute('download', `${filenameBase}_selecionados.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const runDivergenceCheck = () => {
    const divergentRows = data.filter((row) => {
      const category = normalizeForMatch(row.category || '');
      const rawCategory = row.category || '';
      const ticker = normalizeForMatch(row.ticker || '');
      const name = normalizeForMatch(row.name || '');
      if (!category) {
        return false;
      }

      const rule = categoryRules[rawCategory] ?? {
        nameTerms: rawCategory,
        tickerTerms: rawCategory,
      };

      const nameTerms = parseMatchTerms(rule.nameTerms);
      const tickerTerms = parseMatchTerms(rule.tickerTerms);

      const hasNameRule = nameTerms.length > 0;
      const hasTickerRule = tickerTerms.length > 0;

      // Sem termos configurados para a categoria => nao aplicar divergencia.
      if (!hasNameRule && !hasTickerRule) {
        return false;
      }

      const nameMatch = hasNameRule
        ? nameTerms.some((term) => name.includes(term))
        : true;
      const tickerMatch = hasTickerRule
        ? tickerTerms.some((term) => ticker.includes(term))
        : true;

      const isMatch = divergenceMode === 'and'
        ? nameMatch && tickerMatch
        : (hasNameRule && nameMatch) || (hasTickerRule && tickerMatch);

      return !isMatch;
    });

    setDivergentIds(new Set(divergentRows.map((row) => row.id)));
    setDivergenceActive(true);

    const filenameBase = title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_|_$/g, '');

    downloadJsonFile(
      divergentRows.map((row) => ({
        ...row,
        divergenceReason:
          divergenceMode === 'and'
            ? 'regra nao satisfeita: nome E ticker'
            : 'regra nao satisfeita: nome OU ticker',
        divergenceMode,
        divergenceRule: categoryRules[row.category] ?? {
          nameTerms: row.category || '',
          tickerTerms: row.category || '',
        },
      })),
      `${filenameBase}_divergencias.json`,
    );
  };

  const clearDivergence = () => {
    setDivergenceActive(false);
    setDivergentIds(new Set());
  };

  return (
    <section
      className={`glass relative rounded-xl border border-white/10 p-4 ${
        hasOpenOverlay ? 'z-[70]' : 'z-0'
      }`}
    >
      <header className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-semibold text-white">{title}</h3>
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowColumnEditor((current) => !current)}
              className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800"
            >
              Editar colunas
            </button>
            {showColumnEditor && (
              <div className="absolute left-0 top-9 z-[80] w-72 rounded-lg border border-slate-700 bg-slate-900 p-3 shadow-xl">
                <div className="mb-2 text-xs font-semibold text-slate-300">
                  Colunas detectadas ({table.getAllLeafColumns().length})
                </div>
                <input
                  value={columnSearch}
                  onChange={(event) => setColumnSearch(event.target.value)}
                  placeholder="Buscar campo..."
                  className="mb-2 block w-full rounded border border-slate-700 bg-slate-950/80 px-2 py-1 text-xs text-slate-200 outline-none focus:border-brand-500"
                />
                <div className="mb-2 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => table.getAllLeafColumns().forEach((column) => column.toggleVisibility(true))}
                    className="rounded border border-slate-600 px-2 py-1 text-[11px] text-slate-200 hover:bg-slate-800"
                  >
                    Selecionar todos
                  </button>
                  <button
                    type="button"
                    onClick={() => table.getAllLeafColumns().forEach((column) => column.toggleVisibility(false))}
                    className="rounded border border-slate-600 px-2 py-1 text-[11px] text-slate-200 hover:bg-slate-800"
                  >
                    Limpar
                  </button>
                </div>
                <div className="max-h-72 space-y-2 overflow-auto pr-1">
                  {editableColumns.map((column) => (
                    <label key={column.id} className="flex items-center gap-2 text-xs text-slate-200">
                      <input
                        type="checkbox"
                        checked={column.getIsVisible()}
                        onChange={column.getToggleVisibilityHandler()}
                        className="rounded border-slate-600 bg-slate-950"
                      />
                      <span>
                        {typeof column.columnDef.header === 'string'
                          ? column.columnDef.header
                          : column.id}
                      </span>
                    </label>
                  ))}
                  {editableColumns.length === 0 && (
                    <div className="text-xs text-slate-400">Nenhuma coluna encontrada.</div>
                  )}
                </div>
              </div>
            )}
          </div>
          {enableDivergenceTools && (
            <>
              <button
                type="button"
                onClick={divergenceActive ? clearDivergence : runDivergenceCheck}
                className={`rounded-md border px-2 py-1 text-xs ${
                  divergenceActive
                    ? 'border-red-500/60 bg-red-500/15 text-red-200'
                    : 'border-slate-600 text-slate-200 hover:bg-slate-800'
                }`}
              >
                {divergenceActive ? 'Limpar divergencia' : 'Divergencia'}
              </button>
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setShowRuleEditor((current) => !current)}
                  className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800"
                >
                  Regras divergencia
                </button>
                {showRuleEditor && (
                  <div className="absolute left-0 top-9 z-[80] w-[520px] rounded-lg border border-slate-700 bg-slate-900 p-3 shadow-xl">
                    <div className="mb-2 text-xs font-semibold text-slate-300">
                      Configuracao de regra
                    </div>
                    <div className="mb-3 flex items-center gap-4 text-xs text-slate-200">
                      <label className="flex items-center gap-2">
                        <input
                          type="radio"
                          name={`divergence-mode-${title}`}
                          checked={divergenceMode === 'or'}
                          onChange={() => setDivergenceMode('or')}
                        />
                        Nome OU Ticker
                      </label>
                      <label className="flex items-center gap-2">
                        <input
                          type="radio"
                          name={`divergence-mode-${title}`}
                          checked={divergenceMode === 'and'}
                          onChange={() => setDivergenceMode('and')}
                        />
                        Nome E Ticker
                      </label>
                    </div>
                    <input
                      value={ruleSearch}
                      onChange={(event) => setRuleSearch(event.target.value)}
                      placeholder="Buscar tipo/categoria..."
                      className="mb-2 block w-full rounded border border-slate-700 bg-slate-950/80 px-2 py-1 text-xs text-slate-200 outline-none focus:border-brand-500"
                    />
                    <div className="mb-2 text-[11px] text-slate-400">
                      Termos separados por virgula. Exemplo: `cri, certrecebiveis`
                    </div>
                    <div className="max-h-72 overflow-auto rounded border border-slate-800">
                      <table className="w-full text-xs">
                        <thead className="sticky top-0 bg-slate-950">
                          <tr>
                            <th className="px-2 py-1 text-left text-slate-300">Tipo/Categoria</th>
                            <th className="px-2 py-1 text-left text-slate-300">Buscar em Nome</th>
                            <th className="px-2 py-1 text-left text-slate-300">Buscar em Ticker</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredCategories.map((category) => (
                            <tr key={category} className="border-t border-slate-800">
                              <td className="px-2 py-1 text-slate-200">{category}</td>
                              <td className="px-2 py-1">
                                <input
                                  value={categoryRules[category]?.nameTerms ?? category}
                                  onChange={(event) =>
                                    updateCategoryRule(category, 'nameTerms', event.target.value)
                                  }
                                  className="block w-full rounded border border-slate-700 bg-slate-950/80 px-2 py-1 text-xs text-slate-200 outline-none focus:border-brand-500"
                                />
                              </td>
                              <td className="px-2 py-1">
                                <input
                                  value={categoryRules[category]?.tickerTerms ?? category}
                                  onChange={(event) =>
                                    updateCategoryRule(category, 'tickerTerms', event.target.value)
                                  }
                                  className="block w-full rounded border border-slate-700 bg-slate-950/80 px-2 py-1 text-xs text-slate-200 outline-none focus:border-brand-500"
                                />
                              </td>
                            </tr>
                          ))}
                          {filteredCategories.length === 0 && (
                            <tr>
                              <td colSpan={3} className="px-2 py-2 text-slate-400">
                                Nenhuma categoria encontrada.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
              {divergenceActive && (
                <span className="text-xs text-red-300">
                  {divergentIds.size} linha(s) divergente(s)
                </span>
              )}
            </>
          )}
          {enableCategoryExport && (
            <>
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setShowCategorySelector((current) => !current)}
                  className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800"
                >
                  Selecionar categoria
                </button>
                {showCategorySelector && (
                  <div className="absolute left-0 top-9 z-[80] w-64 rounded-lg border border-slate-700 bg-slate-900 p-3 shadow-xl">
                    <div className="mb-2 text-xs font-semibold text-slate-300">
                      Tipo/Categoria ({categories.length})
                    </div>
                    <div className="mb-2 flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setSelectedCategories(new Set(categories))}
                        className="rounded border border-slate-600 px-2 py-1 text-[11px] text-slate-200 hover:bg-slate-800"
                      >
                        Todos
                      </button>
                      <button
                        type="button"
                        onClick={() => setSelectedCategories(new Set())}
                        className="rounded border border-slate-600 px-2 py-1 text-[11px] text-slate-200 hover:bg-slate-800"
                      >
                        Limpar
                      </button>
                    </div>
                    <div className="max-h-72 space-y-2 overflow-auto pr-1">
                      {categories.map((category) => (
                        <label key={category} className="flex items-center gap-2 text-xs text-slate-200">
                          <input
                            type="checkbox"
                            checked={selectedCategories.has(category)}
                            onChange={() => toggleCategorySelection(category)}
                            className="rounded border-slate-600 bg-slate-950"
                          />
                          <span>{category}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={exportSelectedCategoriesToCsv}
                disabled={selectedRowsForExport.length === 0}
                className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Exportar selecionados
              </button>
              <span className="text-xs text-slate-300">
                {selectedRowsForExport.length} linha(s) para exportacao
              </span>
            </>
          )}
        </div>
        <span className="text-xs text-slate-400">{rows.length} linhas visiveis</span>
      </header>

      <div ref={containerRef} className="h-[68vh] overflow-auto rounded-lg border border-white/10">
        <table className="min-w-[1100px] w-full text-sm text-slate-200">
          <thead className="sticky top-0 z-10 bg-slate-900/95">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-white/10">
                {headerGroup.headers.map((header) => {
                  const filterValue = header.column.getFilterValue();
                  return (
                    <th key={header.id} className="px-3 py-2 text-left align-top">
                      <div className="mb-2">
                        <button
                          type="button"
                          onClick={header.column.getToggleSortingHandler()}
                          disabled={!header.column.getCanSort()}
                          className="inline-flex items-center gap-1 font-semibold text-slate-100 disabled:cursor-default"
                        >
                          {header.isPlaceholder
                            ? null
                            : flexRender(header.column.columnDef.header, header.getContext())}
                          {{
                            asc: '↑',
                            desc: '↓',
                          }[header.column.getIsSorted() as 'asc' | 'desc'] ?? null}
                        </button>
                      </div>
                      {header.column.getCanFilter() && (
                        <input
                          value={String(filterValue ?? '')}
                          onChange={(event) => header.column.setFilterValue(event.target.value)}
                          placeholder="Filtrar"
                          className="block w-full rounded border border-slate-700 bg-slate-950/80 px-2 py-1 text-xs text-slate-200 outline-none focus:border-brand-500"
                        />
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>

          <tbody style={{ height: `${virtualizer.getTotalSize()}px`, position: 'relative' }}>
            {items.map((virtualRow) => {
              const row = rows[virtualRow.index];
              if (!row) {
                return null;
              }

              const isLeaf = !row.getCanExpand();

              return (
                <tr
                  key={row.id}
                  className={`absolute left-0 top-0 w-full border-b border-white/5 ${
                    isLeaf && divergenceActive && divergentIds.has(row.original.id)
                      ? 'bg-red-500/20 hover:bg-red-500/25'
                      : isLeaf && onLeafRowClick
                      ? 'cursor-pointer hover:bg-brand-500/10'
                      : 'bg-slate-900/20 hover:bg-slate-800/30'
                  }`}
                  style={{ transform: `translateY(${virtualRow.start}px)` }}
                  onClick={() => {
                    if (isLeaf && onLeafRowClick) {
                      onLeafRowClick(row.original);
                    }
                  }}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-2 align-top">
                      {cell.getIsGrouped() ? (
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            row.toggleExpanded();
                          }}
                          className="inline-flex items-center gap-2 text-slate-100"
                        >
                          <span>{row.getIsExpanded() ? '▾' : '▸'}</span>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          <span className="text-xs text-slate-400">({row.subRows.length})</span>
                        </button>
                      ) : cell.getIsPlaceholder() ? null : (
                        flexRender(cell.column.columnDef.cell, cell.getContext())
                      )}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function applyPrefilter(
  filters: ColumnFiltersState,
  indexer: string,
  maturityDate: string,
): ColumnFiltersState {
  const remaining = filters.filter(
    (entry) => entry.id !== 'indexer' && entry.id !== 'maturityDate',
  );

  if (indexer) {
    remaining.push({ id: 'indexer', value: indexer });
  }
  if (maturityDate) {
    remaining.push({ id: 'maturityDate', value: maturityDate });
  }

  return remaining;
}

export default function CadastroAtivoRF() {
  const [beehusFile, setBeehusFile] = useState<File | null>(null);
  const [xpFile, setXpFile] = useState<File | null>(null);

  const [beehusRows, setBeehusRows] = useState<RFRow[] | null>(null);
  const [xpRows, setXpRows] = useState<RFRow[] | null>(null);

  const [loadingBeehus, setLoadingBeehus] = useState(false);
  const [loadingXP, setLoadingXP] = useState(false);
  const [errorBeehus, setErrorBeehus] = useState<string | null>(null);
  const [errorXP, setErrorXP] = useState<string | null>(null);

  const [globalFilter, setGlobalFilter] = useState('');
  const [leftColumnFilters, setLeftColumnFilters] = useState<ColumnFiltersState>([]);
  const [rightColumnFilters, setRightColumnFilters] = useState<ColumnFiltersState>([]);

  const [leftGrouping, setLeftGrouping] = useState<GroupingState>(['category']);
  const [rightGrouping, setRightGrouping] = useState<GroupingState>(['category']);

  const [leftExpanded, setLeftExpanded] = useState<ExpandedState>(true);
  const [rightExpanded, setRightExpanded] = useState<ExpandedState>(true);
  const [leftSorting, setLeftSorting] = useState<SortingState>([]);
  const [rightSorting, setRightSorting] = useState<SortingState>([]);
  const [leftColumnVisibility, setLeftColumnVisibility] = useState<ColumnVisibilityState>({});
  const [rightColumnVisibility, setRightColumnVisibility] = useState<ColumnVisibilityState>({});

  const [xpPrefilter, setXpPrefilter] = useState<{ indexer: string; maturityDate: string } | null>(null);

  const applyUpdater = <T,>(updater: Updater<T>, current: T): T =>
    typeof updater === 'function' ? (updater as (old: T) => T)(current) : updater;

  const onLeftColumnFiltersChange: OnChangeFn<ColumnFiltersState> = (updater) => {
    setLeftColumnFilters((current) => applyUpdater(updater, current));
  };

  const onRightColumnFiltersChange: OnChangeFn<ColumnFiltersState> = (updater) => {
    setRightColumnFilters((current) => applyUpdater(updater, current));
  };

  const onLeftGroupingChange: OnChangeFn<GroupingState> = (updater) => {
    setLeftGrouping((current) => applyUpdater(updater, current));
  };

  const onRightGroupingChange: OnChangeFn<GroupingState> = (updater) => {
    setRightGrouping((current) => applyUpdater(updater, current));
  };

  const onLeftExpandedChange: OnChangeFn<ExpandedState> = (updater) => {
    setLeftExpanded((current) => applyUpdater(updater, current));
  };

  const onRightExpandedChange: OnChangeFn<ExpandedState> = (updater) => {
    setRightExpanded((current) => applyUpdater(updater, current));
  };

  const onLeftSortingChange: OnChangeFn<SortingState> = (updater) => {
    setLeftSorting((current) => applyUpdater(updater, current));
  };

  const onRightSortingChange: OnChangeFn<SortingState> = (updater) => {
    setRightSorting((current) => applyUpdater(updater, current));
  };

  const onLeftColumnVisibilityChange: OnChangeFn<ColumnVisibilityState> = (updater) => {
    setLeftColumnVisibility((current) => applyUpdater(updater, current));
  };

  const onRightColumnVisibilityChange: OnChangeFn<ColumnVisibilityState> = (updater) => {
    setRightColumnVisibility((current) => applyUpdater(updater, current));
  };

  const hasBothDatasets = useMemo(
    () => Array.isArray(beehusRows) && Array.isArray(xpRows),
    [beehusRows, xpRows],
  );

  const parseBeehusFile = async (file: File) => {
    setLoadingBeehus(true);
    setErrorBeehus(null);
    try {
      const json = await readJsonFile(file);
      const mapped = mapBeehusData(json);
      const keys = collectDatasetKeys(mapped);
      setBeehusRows(mapped);
      setLeftColumnVisibility(
        buildDefaultVisibility(keys, ['category', 'ticker', 'name', 'maturityDate', 'rate', 'indexer']),
      );
    } catch (error) {
      setBeehusRows(null);
      setErrorBeehus(error instanceof Error ? error.message : 'Falha ao processar Beehus');
    } finally {
      setLoadingBeehus(false);
    }
  };

  const parseXPFile = async (file: File) => {
    setLoadingXP(true);
    setErrorXP(null);
    try {
      const json = await readJsonFile(file);
      const mapped = mapXPData(json);
      const keys = collectDatasetKeys(mapped);
      setXpRows(mapped);
      setRightColumnVisibility(
        buildDefaultVisibility(keys, ['category', 'ctipseliccode', 'name', 'maturityDate', 'rate', 'indexer']),
      );
    } catch (error) {
      setXpRows(null);
      setErrorXP(error instanceof Error ? error.message : 'Falha ao processar XP');
    } finally {
      setLoadingXP(false);
    }
  };

  const onBeehusUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    setBeehusFile(file);
    if (file) {
      await parseBeehusFile(file);
    } else {
      setBeehusRows(null);
    }
  };

  const onXPUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    setXpFile(file);
    if (file) {
      await parseXPFile(file);
    } else {
      setXpRows(null);
    }
  };

  const handleBeehusRowClick = (row: RFRow) => {
    const indexer = row.indexer;
    const maturityDate = row.maturityDate;

    setXpPrefilter({ indexer, maturityDate });
    setRightColumnFilters((current) => applyPrefilter(current, indexer, maturityDate));
  };

  const clearXpPrefilter = () => {
    setXpPrefilter(null);
    setRightColumnFilters((current) => applyPrefilter(current, '', ''));
  };

  const beehusColumns = useMemo(
    () =>
      buildColumns(
        collectDatasetKeys(beehusRows ?? []),
        ['category', 'ticker', 'name', 'maturityDate', 'rate', 'indexer'],
      ),
    [beehusRows],
  );

  const xpColumns = useMemo(
    () =>
      buildColumns(
        collectDatasetKeys(xpRows ?? []),
        ['category', 'ctipseliccode', 'name', 'maturityDate', 'rate', 'indexer'],
      ),
    [xpRows],
  );

  return (
    <Layout>
      <div className="mx-auto max-w-[1800px] space-y-6 p-8">
        <header className="space-y-2">
          <h2 className="text-2xl font-bold text-white">Cadastro Ativo RF</h2>
          <p className="text-slate-400">
            Compare os ativos de Renda Fixa entre a base Beehus e a base XP com upload local de JSON.
          </p>
        </header>

        <section className="glass rounded-xl border border-white/10 p-6">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="space-y-2">
              <label className="block text-sm font-medium text-slate-300">
                Upload Base Beehus (Bonds)
              </label>
              <input
                type="file"
                accept=".json,application/json"
                onChange={onBeehusUpload}
                className="block w-full text-sm text-slate-300 file:mr-4 file:rounded-md file:border-0 file:bg-brand-500/20 file:px-4 file:py-2 file:font-semibold file:text-brand-200 hover:file:bg-brand-500/30"
              />
              <div className="text-xs text-slate-400">
                {loadingBeehus
                  ? 'Processando arquivo Beehus...'
                  : beehusFile?.name || 'Nenhum arquivo selecionado'}
              </div>
              {errorBeehus && <div className="text-xs text-red-300">{errorBeehus}</div>}
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-slate-300">Upload Base Nova XP</label>
              <input
                type="file"
                accept=".json,application/json"
                onChange={onXPUpload}
                className="block w-full text-sm text-slate-300 file:mr-4 file:rounded-md file:border-0 file:bg-brand-500/20 file:px-4 file:py-2 file:font-semibold file:text-brand-200 hover:file:bg-brand-500/30"
              />
              <div className="text-xs text-slate-400">
                {loadingXP ? 'Processando arquivo XP...' : xpFile?.name || 'Nenhum arquivo selecionado'}
              </div>
              {errorXP && <div className="text-xs text-red-300">{errorXP}</div>}
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
            <input
              value={globalFilter}
              onChange={(event) => setGlobalFilter(event.target.value)}
              placeholder="Busca global sincronizada (nome, taxa, indexador, vencimento...)"
              className="w-full rounded-lg border border-slate-700 bg-slate-950/80 px-3 py-2 text-sm text-slate-200 outline-none focus:border-brand-500"
            />
            {xpPrefilter && (
              <div className="inline-flex items-center gap-2">
                <span className="inline-flex items-center rounded-full border border-brand-500/40 bg-brand-500/10 px-3 py-2 text-xs text-brand-200">
                  Prefiltro XP: {xpPrefilter.indexer || 'Sem indexador'} +{' '}
                  {xpPrefilter.maturityDate || 'Sem vencimento'}
                </span>
                <button
                  type="button"
                  onClick={clearXpPrefilter}
                  className="rounded-full border border-slate-600 px-3 py-2 text-xs text-slate-200 hover:bg-slate-800"
                >
                  Limpar prefiltro
                </button>
              </div>
            )}
          </div>
        </section>

        {hasBothDatasets ? (
          <section className="grid grid-cols-2 gap-6 max-xl:grid-cols-1">
            <RfTable
              title="Base Beehus (Bonds)"
              data={beehusRows ?? []}
              columns={beehusColumns}
              globalFilter={globalFilter}
              columnFilters={leftColumnFilters}
              onColumnFiltersChange={onLeftColumnFiltersChange}
              grouping={leftGrouping}
              onGroupingChange={onLeftGroupingChange}
              expanded={leftExpanded}
              onExpandedChange={onLeftExpandedChange}
              sorting={leftSorting}
              onSortingChange={onLeftSortingChange}
              columnVisibility={leftColumnVisibility}
              onColumnVisibilityChange={onLeftColumnVisibilityChange}
              enableDivergenceTools
              onLeafRowClick={handleBeehusRowClick}
            />

            <RfTable
              title="Base Nova XP"
              data={xpRows ?? []}
              columns={xpColumns}
              globalFilter={globalFilter}
              columnFilters={rightColumnFilters}
              onColumnFiltersChange={onRightColumnFiltersChange}
              grouping={rightGrouping}
              onGroupingChange={onRightGroupingChange}
              expanded={rightExpanded}
              onExpandedChange={onRightExpandedChange}
              sorting={rightSorting}
              onSortingChange={onRightSortingChange}
              columnVisibility={rightColumnVisibility}
              onColumnVisibilityChange={onRightColumnVisibilityChange}
              enableDivergenceTools={false}
              enableCategoryExport
            />
          </section>
        ) : (
          <section className="glass rounded-xl border border-white/10 p-6 text-sm text-slate-400">
            Faça upload dos dois arquivos JSON e aguarde o parsing para visualizar as tabelas comparativas.
          </section>
        )}
      </div>
    </Layout>
  );
}
