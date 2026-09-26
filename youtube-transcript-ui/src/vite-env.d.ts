/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Optional API address for split deployments. Empty or unset means same origin. */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
