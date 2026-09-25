/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />
/// <reference types="react" />
/// <reference types="react-dom" />
/// <reference types="react/jsx-runtime" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_DEV_API_PROXY?: string;
  readonly MODE?: string;
  readonly BASE_URL?: string;
  readonly PROD?: boolean;
  readonly DEV?: boolean;
  readonly SSR?: boolean;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
