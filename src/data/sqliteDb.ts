/**
 * Owns browser initialization and query execution for the chunked static SQLite database via sql.js-httpvfs.
 * Does not construct domain answer queries or UI state.
 */
import { createDbWorker, type WorkerHttpvfs } from 'sql.js-httpvfs';
import type { SplitFileConfigInner } from 'sql.js-httpvfs/dist/sqlite.worker';

export type SqlParam = string | number | null;
export type SqlRow = Record<string, SqlParam | undefined>;

export interface QueryExecutor {
  query<T extends SqlRow = SqlRow>(sql: string, params?: SqlParam[]): Promise<T[]>;
}

let customExecutor: QueryExecutor | null = null;
let workerPromise: Promise<WorkerHttpvfs> | null = null;

export function setQueryExecutorForTests(executor: QueryExecutor | null): void {
  customExecutor = executor;
}

async function getWorker(): Promise<WorkerHttpvfs> {
  if (!workerPromise) {
    workerPromise = (async () => {
      const baseUri = document.baseURI;
      const cfgUrl = new URL('./data/db/config.json', baseUri).toString();
      const workerUrl = new URL('./data/db/sqlite.worker.js', baseUri).toString();
      const wasmUrl = new URL('./data/db/sql-wasm.wasm', baseUri).toString();

      const resp = await fetch(cfgUrl);
      if (!resp.ok) {
        throw new Error(`Failed to load SQLite config: HTTP ${resp.status}`);
      }
      const rawCfg = (await resp.json()) as SplitFileConfigInner & {
        serverMode: 'chunked';
        urlPrefix: string;
      };
      const resolvedUrlPrefix = new URL(
        `./data/db/${rawCfg.urlPrefix}`,
        baseUri
      ).toString();

      return createDbWorker(
        [
          {
            from: 'inline',
            config: {
              ...rawCfg,
              urlPrefix: resolvedUrlPrefix,
            },
          },
        ],
        workerUrl,
        wasmUrl
      );
    })().catch((err) => {
      workerPromise = null;
      throw err;
    });
  }
  return workerPromise;
}

export async function warmupDatabase(): Promise<void> {
  if (customExecutor) return;
  await getWorker();
}

export async function runQuery<T extends SqlRow = SqlRow>(
  sql: string,
  params: SqlParam[] = []
): Promise<T[]> {
  if (customExecutor) {
    return customExecutor.query<T>(sql, params);
  }
  const worker = await getWorker();
  return ((await worker.db.query(sql, params)) ?? []) as T[];
}
